#encoding=utf-8
from __future__ import unicode_literals
import re
import urllib

class Rule(object):
    def __init__(self):
        pass

class NewPageRule(Rule):
    
    def __init__(self, points):
        self.points = float(points)

    def test(self, article):
        if article.new and not article.redirect:
            return self.points, '%.f p (N)' % self.points
        else:
            return 0, ''

class QualiRule(Rule):

    def __init__(self, points):
        self.points = float(points)

    def test(self, article):
        return self.points, '<abbr title="Kvalifisering">%.f p</abbr>' % self.points


class ByteRule(Rule):

    def __init__(self, points, maxpoints = -1):
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

        return p, '%.1f p (<span class="uk-b">%s = </span><span class="uk-bt">%.f bytes</span>)' % (p, ' '.join(nb), article.bytes)

class WordRule(Rule):

    def __init__(self, points, maxpoints = -1):
        self.points = float(points)
        self.maxpoints = float(maxpoints)

    def get_wordcount(self, txt):
        dp = DanmicholoParser(txt)
        return len(dp.maintext.split())

    def test(self, article):
        nbw = []
        article_words = 0
        for revid, rev in article.revisions.iteritems():
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
        
        return p, '%.1f p (<span class="uk-w">%s = </span><span class="uk-wt">%.f ord</span>)' % (p, ' '.join(nbw), article_words)

class ImageRule(Rule):
    
    def __init__(self, points, maxpoints = -1):
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

class ByteBonusRule(Rule):
    
    def __init__(self, points, limit):
        self.points = float(points)
        self.limit = float(limit)

    def test(self, article):
        if article.bytes > self.limit:
            return self.points, '%.f p (&gt; %.f bytes)' % (self.points, self.limit)
