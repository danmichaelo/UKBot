#encoding=utf-8
from __future__ import unicode_literals
import re
import urllib
from danmicholoparser import DanmicholoParser

class Rule(object):
    def __init__(self):
        self.errors = []

class NewPageRule(Rule):
    
    def __init__(self, points):
        Rule.__init__(self)
        self.points = float(points)

    def test(self, article):
        if article.new and not article.redirect:
            return self.points, '%.f p (N)' % self.points
        else:
            return 0, ''

class QualiRule(Rule):

    def __init__(self, points):
        Rule.__init__(self)
        self.points = float(points)

    def test(self, article):
        return self.points, '<abbr title="Kvalifisering">%.f p</abbr>' % self.points


class ByteRule(Rule):

    def __init__(self, points, maxpoints = -1):
        Rule.__init__(self)
        self.points = float(points)
        self.maxpoints = float(maxpoints)

    def test(self, article):
        p = article.bytes * self.points
        if self.maxpoints != -1 and p > self.maxpoints:
            p = self.maxpoints

        nb = []
        for revid, rev in article.revisions.iteritems():
            
            # make a link to the revision
            q = { 'title': article.name.encode('utf-8'), 'oldid': revid }
            if not rev.new:
                q['diff'] = 'prev'
            link = 'http://' + article.site.host + article.site.site['script'] + '?' + urllib.urlencode(q)

            revsize = rev.size - rev.parentsize
            if revsize != 0:
                if len(nb) == 0:
                    fortegn = '%s ' % ('' if revsize > 0 else '-')
                else:
                    fortegn = '%s ' % ('+' if revsize > 0 else '-')
                nb.append('[%s %s%d]' % (link, fortegn, abs(revsize)))

        if len(nb) > 1:
            label = '%.1f p (<span class="uk-b">%s = </span><span class="uk-bt">%.f bytes</span>)' % (p, ' '.join(nb), article.bytes)
        else:
            label = '%.1f p (<span class="uk-be">%s bytes</span>)' % (p, nb[0])
        return p, label

class WordRule(Rule):

    def __init__(self, points, maxpoints = -1):
        Rule.__init__(self)
        self.points = float(points)
        self.maxpoints = float(maxpoints)

    def get_wordcount(self, txt):
        dp = DanmicholoParser(txt)
        return len(dp.maintext.split())

    def test(self, article):
        nbw = []
        article_words = 0
        for revid, rev in article.revisions.iteritems():

            # make a link to the revision
            q = { 'title': article.name.encode('utf-8'), 'oldid': revid }
            if not rev.new:
                q['diff'] = 'prev'
            link = 'http://' + article.site.host + article.site.site['script'] + '?' + urllib.urlencode(q)
            
            nwords = self.get_wordcount(rev.text)
            nwords_p = self.get_wordcount(rev.parenttext)
            rev_words = nwords - nwords_p
            article_words += rev_words
            if rev_words != 0:
                if len(nbw) == 0:
                    fortegn = '%s ' % ('' if rev_words > 0 else '-')
                else:
                    fortegn = '%s ' % ('+' if rev_words > 0 else '-')
                nbw.append('[%s %s%d] ' % (link, fortegn, abs(rev_words)))
        
        p = article_words * self.points
        if self.maxpoints != -1 and p > self.maxpoints:
            p = self.maxpoints
        
        if len(nbw) > 1:
            label = '%.1f p (<span class="uk-w">%s = </span><span class="uk-wt">%.f ord</span>)' % (p, ' '.join(nbw), article_words)
        else:
            label = '%.1f p (<span class="uk-we">%s ord</span>)' % (p, nbw[0])
        
        return p, label

class ImageRule(Rule):
    
    def __init__(self, points, maxpoints = -1):
        Rule.__init__(self)
        self.points = float(points)
        self.maxpoints = float(maxpoints)

    def get_imagecount(self, txt):
        return len(re.findall(r'(?:\.svg|\.png|\.jpg)', txt, flags = re.IGNORECASE))

    def test(self, article):
       
        article_imgs = 0
        for revid, rev in article.revisions.iteritems():
            nimages = self.get_imagecount(rev.text)
            nimages_p = self.get_imagecount(rev.parenttext)
            rev_imgs = nimages - nimages_p
            article_imgs += rev_imgs

        p = article_imgs * self.points
        if self.maxpoints != -1 and p > self.maxpoints:
            p = self.maxpoints

        return p, '%.f p (%d bilde%s)' % (p, article_imgs, 'r' if article_imgs > 1 else '')

class RefRule(Rule):
    
    def __init__(self, sourcepoints, refpoints):
        """
        sourcepoints: points for adding new sources
        refpoints: points for referring to existing sources
        """
        Rule.__init__(self)
        self.sourcepoints = float(sourcepoints)
        self.refpoints = float(refpoints)
            
    def testrev(self, rev):
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
        return s2-s1, r2-r1, dp1.errors + dp2.errors

    def test(self, article):
        sources_added = 0
        refs_added = 0
        p = 0
        for revid, rev in article.revisions.iteritems():
            s, r, errors = self.testrev(rev)
            self.errors.extend([{
                'title': 'Problem ved parsing av [http://%s%s?olid=%d rev. %d]' % (article.site.host, article.site.site['script'], rev.revid, rev.revid), 
                'text': e} for e in errors])
            sources_added += s
            refs_added += r
        txt = ''
        p = sources_added * self.sourcepoints + refs_added * self.refpoints
        if p > 0.0:
            s = []
            if sources_added > 0:
                s.append('%d kilde%s' % (sources_added, 'r' if sources_added > 1 else ''))
            if refs_added > 0:
                s.append('%d kildehenvisninge%s' % (refs_added, 'r' if refs_added > 1 else ''))
            txt = '%.f p (%s)' % (p, ', '.join(s))
        return p, txt

class ByteBonusRule(Rule):
    
    def __init__(self, points, limit):
        Rule.__init__(self)
        self.points = float(points)
        self.limit = float(limit)

    def test(self, article):
        if article.bytes > self.limit:
            return self.points, '%.f p (&gt; %.f bytes)' % (self.points, self.limit)
