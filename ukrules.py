#encoding=utf-8
from __future__ import unicode_literals
import re
import urllib
from danmicholoparser import DanmicholoParser, DanmicholoParseError


class Rule(object):

    def __init__(self):
        self.errors = []

    def iszero(self, f):
        f = float(f)
        return (f > -0.1 and f < 0.1)


class NewPageRule(Rule):
    
    def __init__(self, points):
        Rule.__init__(self)
        self.points = float(points)

    def test(self, rev):
        if rev.new and not rev.article.redirect:
            rev.points.append([self.points, 'newpage', 'ny side'])


class QualiRule(Rule):

    def __init__(self, points):
        Rule.__init__(self)
        self.points = float(points)
    
    def test(self, rev):
        if self.iszero(rev.article.get_points('quali')):
            rev.points.append([self.points, 'quali', 'kvalifisert'])


class ByteRule(Rule):

    def __init__(self, points, maxpoints = -1):
        Rule.__init__(self)
        self.points = float(points)
        self.maxpoints = float(maxpoints)

    def test(self, rev):
        revpoints = rev.bytes * self.points
        ab = rev.article.get_points('byte')
        if self.maxpoints > 0.0 and ab + revpoints > self.maxpoints:
            revpoints = self.maxpoints - ab
    
        if not self.iszero(revpoints):
            rev.points.append([revpoints, 'byte', '%.f bytes' % rev.bytes])


class WordRule(Rule):

    def __init__(self, points, maxpoints = -1):
        Rule.__init__(self)
        self.points = float(points)
        self.maxpoints = float(maxpoints)

    def get_wordcount(self, txt):
        dp = DanmicholoParser(txt)
        return len(dp.maintext.split())

    def test(self, rev):
        nwords = self.get_wordcount(rev.text)
        nwords_p = self.get_wordcount(rev.parenttext)
        words = nwords - nwords_p
        
        revpoints = words * self.points
        ab = rev.article.get_points('word')
        if self.maxpoints > 0.0 and ab + revpoints > self.maxpoints:
            revpoints = self.maxpoints - ab
        
        if not self.iszero(revpoints):
            rev.points.append([revpoints, 'word', '%.f ord' % words])


class ImageRule(Rule):
    
    def __init__(self, points, maxpoints = -1):
        Rule.__init__(self)
        self.points = float(points)
        self.maxpoints = float(maxpoints)

    def get_imagecount(self, txt):
        return len(re.findall(r'(?:\.svg|\.png|\.jpg)', txt, flags = re.IGNORECASE))

    def test(self, rev):
       
        nimages = self.get_imagecount(rev.text)
        nimages_p = self.get_imagecount(rev.parenttext)
        imgs = nimages - nimages_p

        revpoints = imgs * self.points
        ab = rev.article.get_points('image')
        if self.maxpoints > 0.0 and ab + revpoints > self.maxpoints:
            revpoints = self.maxpoints - ab
        
        if not self.iszero(revpoints):
            rev.points.append([revpoints, 'image', '%d bilde%s' % (imgs, 'r' if imgs > 1 else '')])
 

class RefRule(Rule):
    
    def __init__(self, sourcepoints, refpoints):
        """
        sourcepoints: points for adding new sources
        refpoints: points for referring to existing sources
        """
        Rule.__init__(self)
        self.sourcepoints = float(sourcepoints)
        self.refpoints = float(refpoints)
            
    def test(self, rev):
        dp1 = DanmicholoParser(rev.parenttext)
        s1 = 0
        r1 = 0
        s2 = 0
        r2 = 0
        if 'ref' in dp1.tags:
            s1 = len([r for r in dp1.tags['ref'] if 'content' in r])
            r1 = len([r for r in dp1.tags['ref'] if not 'content' in r])
        dp2 = DanmicholoParser(rev.text)
        if 'ref' in dp2.tags:
            s2 = len([r for r in dp2.tags['ref'] if 'content' in r])
            r2 = len([r for r in dp2.tags['ref'] if not 'content' in r])
        sources_added = s2 - s1
        refs_added = r2 - r1

        errors = dp1.errors + dp2.errors
        self.errors.extend([{
            'title': 'Problem ved parsing av [http://%s%s?olid=%d rev. %d]' % (rev.article.site.host, rev.article.site.site['script'], rev.revid, rev.revid), 
            'text': e} for e in errors])
        
        #p = sources_added * self.sourcepoints + refs_added * self.refpoints
        if sources_added != 0 or refs_added != 0:
            p = 0.
            s = []
            if sources_added > 0:
                p += sources_added * self.sourcepoints
                s.append('%d kilde%s' % (sources_added, 'r' if sources_added > 1 else ''))
            if refs_added > 0:
                p += refs_added * self.refpoints
                s.append('%d kildehenvisning%s' % (refs_added, 'er' if refs_added > 1 else ''))
            txt = ', '.join(s)
        
            rev.points.append([p, 'ref', txt])


class ByteBonusRule(Rule):
    
    def __init__(self, points, limit):
        Rule.__init__(self)
        self.points = float(points)
        self.limit = float(limit)

    def test(self, rev):
        abytes = 0.
        for rev in rev.article.revs:
            abytes += rev.bytes
            if rev == rev and abytes >= self.limit:
                rev.points.append([self.points, 'bytebonus', '&gt; %.f bytes' % self.limit ])
            elif abytes >= self.limit:
                break

