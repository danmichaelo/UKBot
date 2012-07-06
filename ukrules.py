#encoding=utf-8
from __future__ import unicode_literals
import re
import urllib
from bs4 import BeautifulSoup
from danmicholoparser import DanmicholoParser, DanmicholoParseError


class Rule(object):

    def __init__(self):
        pass

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


class StubRule(Rule):

    def __init__(self, points):
        Rule.__init__(self)
        self.points = float(points)

    def is_stub(self, text):
        """ Checks if a given text is a stub """

        dp = DanmicholoParser(text, debug = False)
        for tname, templ in dp.templates.iteritems():
            if tname.find('stubb') != -1 or tname.find('spire') != -1:
                return True
        return False

    def test(self, rev):
        try:
            if self.is_stub(rev.parenttext) and not self.is_stub(rev.text):
                rev.points.append([self.points, 'stub', 'avstubbing'])
        except DanmicholoParseError as e:
            rev.article.errors.append('Problem ved parsing av [%s rev. %d] : %s' % (rev.get_link(), rev.revid, e.msg))
    

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
        ab_raw = rev.article.get_points('byte', ignore_max = True)
        
        if self.maxpoints > 0.0 and self.iszero(ab - self.maxpoints) :
            # we have reached max
            if revpoints < 0.0 and  ab_raw + revpoints < self.maxpoints:
                rev.points.append([self.maxpoints - ab_raw - revpoints, 'byte', '%.f bytes' % rev.bytes, revpoints])
            else:
                rev.points.append([0.0, 'byte', '%.f bytes' % rev.bytes, revpoints])

        elif self.maxpoints > 0.0 and ab + revpoints > self.maxpoints:
            # reaching max
            rev.points.append([self.maxpoints - ab, 'byte', '&gt; %.f bytes (&gt; maks)' % rev.bytes, revpoints ])

        #elif not self.iszero(revpoints):
        else:
            rev.points.append([revpoints, 'byte', '%.f bytes' % rev.bytes, revpoints])


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
        """
        While BeautifulSoup and its parsers are robust, (unknown) tags with unquoted arguments seems to be an issue.

        Let's first define a function to make things clearer:
        >>> def f(str):
        >>>     return ''.join([unicode(tag) for tag in BeautifulSoup(str, 'lxml').findAll('body')[0].contents])

        Now, here is an unexpected result: the ref-tag is not read as closed and continue to eat the remaining text!
        >>> f('<ref name=XYZ/>Mer tekst her')
        <<< u'<ref name="XYZ/">Mer tekst her</ref>'

        Add a space before / and we get the expected result:
        >>> f('<ref name=XYZ />Mer tekst her')
        <<< u'<ref name="XYZ"></ref>Mer tekst her'

        Therefore we try to fix this before sending the text to BS
        """

        ptext = re.sub(r'name\s?=\s?([^"\s]+)/>', 'name=\1 />', rev.parenttext)
        text = re.sub(r'name\s?=\s?([^"\s]+)/>', 'name=\1 />', rev.text)

        parentsoup = BeautifulSoup(ptext, 'lxml')
        soup = BeautifulSoup(text, 'lxml')

        allref1 = parentsoup.findAll('ref')
        s1 = len([r for r in allref1 if len(r.contents) > 0])
        r1 = len([r for r in allref1 if len(r.contents) == 0])

        allref2 = soup.findAll('ref')
        s2 = len([r for r in allref2 if len(r.contents) > 0])
        r2 = len([r for r in allref2 if len(r.contents) == 0])

        #print rev.article.name,len(allref1), len(allref2)

        sources_added = s2 - s1
        refs_added = r2 - r1
        
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

