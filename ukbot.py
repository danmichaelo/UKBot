#encoding=utf-8
from __future__ import unicode_literals

import numpy as np
import time, datetime
import re
import sqlite3
from odict import odict
import mwclient
import urllib

from danmicholoparser import DanmicholoParser, DanmicholoParseError
from ukrules import *
from ukfilters import *

import locale
locale.setlocale(locale.LC_TIME, 'no_NO.utf-8'.encode('utf-8'))

#CREATE TABLE contribs (
#  revid INTEGER NOT NULL,
#  site TEXT NOT NULL,
#  parentid INTEGER NOT NULL,
#  user TEXT NOT NULL, 
#  page TEXT NOT NULL, 
#  timestamp DATETIME NOT NULL, 
#  size  INTEGER NOT NULL,
#  parentsize  INTEGER NOT NULL,
#  PRIMARY KEY(revid, site)
#);
#CREATE TABLE fulltexts (
#  revid INTEGER NOT NULL,
#  site TEXT NOT NULL,
#  revtxt TEXT NOT NULL,
#  PRIMARY KEY(revid, site)  
#);

#from ete2 import Tree

#from progressbar import ProgressBar, Counter, Timer, SimpleProgress
#pbar = ProgressBar(widgets = ['Processed: ', Counter(), ' revisions (', Timer(), ')']).start()
#pbar.maxval = pbar.currval + 1
#pbar.update(pbar.currval+1)
#pbar.finish()


class CategoryLoopError(Exception):
    """Raised when a category loop is found. 

    Attributes:
        catpath -- category path followed while getting lost in the loop
    """
    def __init__(self, catpath):
        self.catpath = catpath
        self.msg = 'Entered a category loop'


class ParseError(Exception):
    """Raised when wikitext input is not on the expected form, so we don't find what we're looking for"""
    
    def __init__(self, msg):
        self.msg = msg


class Article(object):
    
    def __init__(self, site, name):
        """
        An article is uniquely identified by its name and its site
        """
        self.site = site
        self.site_key = site.host.split('.')[0]
        self.name = name
        
        self.revisions = odict()
        self.redirect = False
    
    def __repr__(self):
        return ("<Article %s:%s>" % (self.site_key, self.name)).encode('utf-8')

    @property
    def new(self):
        return self.revisions[self.revisions.firstkey()].new

    def add_revision(self, revid, **kwargs):
        self.revisions[revid] = Revision(self.site_key, self, revid, **kwargs)
        return self.revisions[revid]
    
    @property
    def bytes(self):
        return np.sum([rev.bytes for rev in self.revisions.itervalues()])

    @property
    def points(self):
        return np.sum([rev.get_points() for rev in self.revisions.values()])

    def get_points(self, ptype = ''):
        return np.sum([rev.get_points(ptype) for rev in self.revisions.values()])


class Revision(object):
    
    def __init__(self, site_key, article, revid, **kwargs):
        """
        A revision is uniquely identified by its revision id and its site

        Arguments:
          - site_key: (str) short site name
          - article: (Article) article object reference
          - revid: (int) revision id
        """
        self.site_key = site_key
        self.article = article

        self.revid = revid
        self.size = -1
        self.text = ''

        self.parentid = 0
        self.parentsize = 0
        self.parenttext = ''

        self.points = []
        
        for k, v in kwargs.iteritems():
            if k == 'timestamp':
                self.timestamp = int(v)
            elif k == 'parentid':
                self.parentid = int(v)
            elif k == 'size':
                self.size = int(v)
            elif k == 'parentsize':
                self.parentsize = int(v)
            else:
                raise StandardError('add_revision got unknown argument %s' % k)
    
    def __repr__(self):
        return ("<Revision %d for %s:%s>" % (self.revid, self.site_key, self.article.name)).encode('utf-8')

    @property
    def bytes(self):
        return self.size - self.parentsize

    @property
    def new(self):
        return (self.parentid == 0)
    
    def get_link(self):
        """ returns a link to revision """
        q = { 'title': self.article.name.encode('utf-8'), 'oldid': self.revid }
        if not self.new:
            q['diff'] = 'prev'
        return 'http://' + self.article.site.host + self.article.site.site['script'] + '?' + urllib.urlencode(q)
    
    def get_points(self, ptype = ''):
        p = 0.0
        for pnt in self.points:
            if ptype == '' or pnt[1] == ptype:
                p += pnt[0]
        return p

class User(object):

    def __init__(self, username, verbose = True):
        self.name = username
        self.articles = odict()
        self.verbose = verbose

    def __repr__(self):
        return ("<User %s>" % self.name).encode('utf-8')
    
    @property
    def revisions(self):
        # oh my, funny (and fast) one-liner for making a flat list of revisions
        return [rev for article in self.articles.values() for rev in article.revisions.values()]

    def sort_contribs(self):

        # sort revisions by revision id
        for article in self.articles.itervalues():
            article.revisions.sort( key = lambda x: x[0] ) # sort by key (revision id)

        # sort articles by first revision id
        self.articles.sort( key = lambda x: x[1].revisions.firstkey() )
    
    def add_contribs_from_wiki(self, site, start, end, fulltext = False, namespace = 0):
        """
        Populates self.articles with entries from the API.

            site      : mwclient.client.Site object
            start     : datetime.datetime object
            end       : datetime.datetime object
            fulltext  : get revision fulltexts
            namespace : namespace ID
        """
        apilim = 50
        if 'bot' in site.rights:
            apilim = site.api_limit         # API limit, should be 500

        site_key = site.host.split('.')[0]
        
        ts_start = start.isoformat()+'Z'
        ts_end = end.isoformat()+'Z'

        # 1) Fetch user contributions

        new_articles = []
        new_revisions = []
        for c in site.usercontributions(self.name, ts_start, ts_end, 'newer', prop = 'ids|title|timestamp', namespace = namespace ):
            #pageid = c['pageid']
            rev_id = c['revid']
            article_title = c['title']
            article_key = site_key + ':' + article_title
            
            if not article_key in self.articles:
                self.articles[article_key] = Article(site, article_title) 
                new_articles.append(self.articles[article_key])
            
            article = self.articles[article_key]
            
            if not rev_id in article.revisions:
                rev = article.add_revision(rev_id, timestamp = time.mktime(c['timestamp']) )
                new_revisions.append(rev)
            
        # Always sort after we've added contribs
        self.sort_contribs()
        if self.verbose and (len(new_revisions) > 0 or len(new_articles) > 0):
            print " -> [%s] Added %d new revisions, %d new articles from API" % (site_key, len(new_revisions), len(new_articles))

        # 2) Check if pages are redirects (this information can not be cached, because other users may make the page a redirect)
        #    If we fail to notice a redirect, the contributions to the page will be double-counted, so lets check

        titles = [a.name for a in self.articles.values() if a.site_key == site_key]
        for s0 in range(0, len(titles), apilim):
            ids = '|'.join(titles[s0:s0+apilim])
            for page in site.api('query', prop = 'info', titles = ids)['query']['pages'].itervalues():
                article_key = site_key + ':' + page['title']
                self.articles[article_key].redirect = ('redirect' in page.keys())

        # 3) Fetch info about the new revisions: diff size, possibly content

        props = 'ids|size'
        if fulltext:
            props += '|content'
        revids = [str(r.revid) for r in new_revisions]
        parentids = []
        nr = 0
        for s0 in range(0, len(new_revisions), apilim):
            print "API limit is ",apilim," getting ",s0
            ids = '|'.join(revids[s0:s0+apilim])
            for page in site.api('query', prop = 'revisions', rvprop = props, revids = ids)['query']['pages'].itervalues():
                article_key = site_key + ':' + page['title']
                for apirev in page['revisions']:
                    nr +=1
                    rev = self.articles[article_key].revisions[apirev['revid']]
                    rev.parentid = apirev['parentid']
                    rev.size = apirev['size']
                    if '*' in apirev.keys():
                        rev.text = apirev['*']
                    if not rev.new:
                        parentids.append(rev.parentid)
        if self.verbose and nr > 0:
            print " -> [%s] Checked %d of %d revisions, found %d parent revisions" % (site_key, nr, len(new_revisions), len(parentids))

        if nr != len(new_revisions):
            raise StandardError("Did not get all revisions")
        
        # 4) Fetch info about the parent revisions: diff size, possibly content
        
        props = 'ids|size'
        if fulltext:
            props += '|content'
        nr = 0
        parentids = [str(i) for i in parentids]
        for s0 in range(0, len(parentids), apilim):
            ids = '|'.join(parentids[s0:s0+apilim])
            for page in site.api('query', prop = 'revisions', rvprop = props, revids = ids)['query']['pages'].itervalues():
                article_key = site_key + ':' + page['title']
                article = self.articles[article_key]
                for apirev in page['revisions']:
                    nr +=1
                    parentid = apirev['revid']
                    found = False
                    for revid, rev in article.revisions.iteritems():
                        if rev.parentid == parentid:
                            found = True
                            break
                    if not found:
                        raise StandardError("No revision found matching title=%s, parentid=%d" % (page['title'], parentid))

                    rev.parentsize = apirev['size']
                    if '*' in apirev.keys():
                        rev.parenttext = apirev['*']
        if self.verbose and nr > 0:
            print " -> [%s] Checked %d parent revisions" % (site_key, nr)

    
    def save_contribs_to_db(self, sql):
        """ Save self.articles to DB so it can be read by add_contribs_from_db """

        cur = sql.cursor()
        nrevs = 0
        ntexts = 0

        for article_key, article in self.articles.iteritems():
            site_key = article.site_key

            for revid, rev in article.revisions.iteritems():
                ts = datetime.datetime.fromtimestamp(rev.timestamp).strftime('%F %T')
                
                # Save revision if not already saved
                if len( cur.execute(u'SELECT revid FROM contribs WHERE revid=? AND site=?', [revid, site_key]).fetchall() ) == 0:
                    cur.execute(u'INSERT INTO contribs (revid, site, parentid, user, page, timestamp, size, parentsize) VALUES (?,?,?,?,?,?,?,?)', 
                        (revid, site_key, rev.parentid, self.name, article.name, ts, rev.size, rev.parentsize))
                    nrevs += 1

                # Save revision text if we have it and if not already saved
                if len(rev.text) > 0 and len( cur.execute(u'SELECT revid FROM fulltexts WHERE revid=? AND site=?', [revid, site_key]).fetchall() ) == 0:
                    cur.execute(u'INSERT INTO fulltexts (revid, site, revtxt) VALUES (?,?,?)', (revid, site_key, rev.text) )
                    ntexts += 1

                # Save parent revision text if we have it and if not already saved
                if len(rev.parenttext) > 0 and len( cur.execute(u'SELECT revid FROM fulltexts WHERE revid=? AND site=?', [rev.parentid, site_key]).fetchall() ) == 0:
                    cur.execute(u'INSERT INTO fulltexts (revid, site, revtxt) VALUES (?,?,?)', (rev.parentid, site_key, rev.parenttext) )
                    ntexts += 1

        sql.commit()
        cur.close()
        if self.verbose and (nrevs > 0 or ntexts > 0):
            print " -> Wrote %d revisions and %d fulltexts to DB" % (nrevs, ntexts)
    
    def add_contribs_from_db(self, sql, start, end, sites):
        """
        Populates self.articles with entries from SQLite DB

            sql   : sqlite3.Connection object
            start : datetime.datetime object
            end   : datetime.datetime object
        """
        cur = sql.cursor()
        cur2 = sql.cursor()
        ts_start = start.strftime('%F %T')
        ts_end = end.strftime('%F %T')
        nrevs = 0
        narts = 0
        for row in cur.execute(u"""SELECT revid, site, parentid, page, timestamp, size, parentsize FROM contribs 
                WHERE user=? AND timestamp >= ? AND timestamp <= ?""", (self.name, ts_start, ts_end)):

            rev_id, site_key, parent_id, article_title, ts, size, parentsize = row
            article_key = site_key + ':' + article_title
            ts = datetime.datetime.strptime(ts, '%Y-%m-%d %H:%M:%S').strftime('%s')

            # Add article if not present
            if not article_key in self.articles:
                narts +=1
                self.articles[article_key] = Article(sites[site_key], article_title) 
            article = self.articles[article_key]
            
            # Add revision if not present
            if not rev_id in article.revisions:
                nrevs += 1
                article.add_revision(rev_id, timestamp = ts, parentid = parent_id, size = size, parentsize = parentsize)
            rev = article.revisions[rev_id]

            # Add revision text
            for row2 in cur2.execute(u"""SELECT revtxt FROM fulltexts WHERE revid=? AND site=?""", [rev_id, site_key]):
                rev.text = row2[0]
            
            # Add parent revision text
            if not rev.new:
                for row2 in cur2.execute(u"""SELECT revtxt FROM fulltexts WHERE revid=? AND site=?""", [parent_id, site_key]):
                    rev.parenttext = row2[0]

        cur.close()
        cur2.close()

        # Always sort after we've added contribs
        self.sort_contribs()

        if self.verbose and (nrevs > 0 or narts > 0):
            print " -> Added %d revisions, %d articles from DB" % (nrevs, narts)

    def filter(self, filters, debug = False):

        for filter in filters:
            self.articles = filter.filter(self.articles)

        # We should re-sort afterwards since not all filters preserve the order (notably the CatFilter)
        self.sort_contribs()

        if self.verbose:
            print " -> %d articles remain after filtering" % len(self.articles)
        if debug:
            print '----'
            for a in self.articles.iterkeys():
                print a
            print '----'

    @property
    def bytes(self):
        return np.sum([a.bytes for a in self.articles.itervalues()])
    
    @property
    def points(self):
        return np.sum([a.points for a in self.articles.values()])

    def analyze(self, rules):

        self.plotdata = { 'x': [], 'y': [] }
        
        # loop over articles
        for article_key, article in self.articles.iteritems():
            
            # loop over revisions
            for revid, rev in article.revisions.iteritems():

                rev.points = []

                # loop over rules
                for rule in rules:
                    rule.test(rev)

            # Cumulative points
            #self.plotdata['x'].append(article.revisions[article.revisions.firstkey()].timestamp)
            #self.plotdata['y'].append(self.points)
        
    def format_result(self):
        
        entries = []

        # loop over articles
        for article_key, article in self.articles.iteritems():
            
            if article.points != 0.0:
                

                # loop over revisions
                revs = []
                for revid, rev in article.revisions.iteritems():

                    if len(rev.points) > 0:
                        descr = ' + '.join(['%.1f p (%s)' % (p[0], p[2]) for p in rev.points])
                        revs.append('[%s %d]: %s' % (rev.get_link(), revid, descr))
                
                titletxt = '<br />'.join(revs)
                try:
                    titletxt += '<br />Kategoritreff: ' + ' &gt; '.join(article.cat_path)
                except AttributeError:
                    pass
                
                out = '# [[%s|%s]] (<abbr class="uk-ap">%.1f p</abbr>)' % (article_key, article.name, article.points)
                out += '<div class="uk-ap-title" style="font-size: smaller; color:#888; line-height:100%;">' + titletxt + '</div>'
                
                entries.append(out)

        out = '=== [[Bruker:%s|%s]] (%.f p) ===\n' % (self.name, self.name, self.points)
        if len(entries) == 0:
            out += "''Ingen kvalifiserte bidrag registrert enda''"
        else:
            out += '%d artikler, {{formatnum:%.2f}} kB\n' % (len(entries), self.bytes/1000.)
        if len(entries) > 10:
            out += '{{Kolonner}}\n'
        out += '\n'.join(entries)
        out += '\n\n'

        return out


class UK(object):

    def __init__(self, txt, catignore, sites):

        sections = [s.strip() for s in re.findall('^[\s]*==([^=]+)==', txt, flags = re.M)]
        self.results_section = sections.index('Resultater') + 1

        self.sites = sites
        self.users = [User(n) for n in self.extract_userlist(txt)]
        self.rules, self.filters = self.extract_rules(txt, catignore)
        
        print '== Uke %d == ' % self.week

    def extract_userlist(self, txt):
        lst = []
        m = re.search('==\s*Delta[kg]ere\s*==',txt)
        if not m:
            raise ParseError('Fant ikke deltakerlisten!')
        deltakerliste = txt[m.end():]
        m = re.search('==[^=]+==',deltakerliste)
        if not m:
            raise ParseError('Fant ingen overskrift etter deltakerlisten!')
        deltakerliste = deltakerliste[:m.start()]
        for d in deltakerliste.split('\n'):
            q = re.search(r'\[\[([^:]+):([^|\]]+)', d)
            if q:
                lst.append(q.group(2))
        print " -> Fant %d deltakere" % (len(lst))
        return lst


    def extract_rules(self, txt, catignore_txt):
        rules = []
        filters = []

        dp = DanmicholoParser(txt)
        dp2 = DanmicholoParser(catignore_txt)
        
        if not 'ukens konkurranse poeng' in dp.templates.keys():
            raise ParseError('Denne konkurransen har ingen poengregler. Poengregler defineres med {{tl|ukens konkurranse poeng}}.')
        
        if not 'ukens konkurranse kriterium' in dp.templates.keys():
            raise ParseError('Denne konkurransen har ingen bidragskriterier. Kriterier defineres med {{tl|ukens konkurranse kriterium}}.')
        
        if not 'infoboks ukens konkurranse' in dp.templates.keys():
            raise ParseError('Denne konkurransen mangler en {{tl|infoboks ukens konkurranse}}-mal.')

        try:
            catignore = dp2.tags['pre'][0]['content'].split()
        except (IndexError, KeyError):
            raise ParseError('Klarte ikke tolke catignore-siden')

        # Read filters
        for templ in dp.templates['ukens konkurranse kriterium']:
            p = templ.parameters
            anon = [[k,p[k]] for k in p.keys() if type(k) == int]
            anon = sorted(anon, key = lambda x: x[0])
            anon = [a[1] for a in anon]
            named = [[k,p[k]] for k in p.keys() if type(k) != int]

            named = odict(named)
            key = anon[0].lower()

            if key == 'ny':
                filters.append(NewPageFilter())

            elif key == 'eksisterende':
                filters.append(ExistingPageFilter())

            elif key == 'stubb':
                filters.append(StubFilter())
            
            elif key == 'bytes':
                if len(anon) < 2:
                    raise ParseError('Ingen bytesgrense (andre argument) ble gitt til {{mlp|ukens konkurranse kriterium|bytes}}')
                params = { 'bytelimit': anon[1] }
                filters.append(ByteFilter(**params))

            elif key == 'kategori':
                if len(anon) < 2:
                    raise ParseError('Ingen kategori(er) ble gitt til {{mlp|ukens konkurranse kriterium|kategori}}')
                params = { 'sites': self.sites, 'catnames': anon[1:], 'ignore': catignore }
                if 'maksdybde' in named:
                    params['maxdepth'] = int(named['maksdybde'])
                filters.append(CatFilter(**params))

            #elif key == 'tilbakelenke':
            #    params = { 'title': anon[1] }
            #    filters.append(BackLinkFilter(**params)

            else: 
                raise ParseError('Ukjent argument gitt til {{ml|ukens konkurranse kriterium}}: '+key)
        
        # Read rules
        for templ in dp.templates['ukens konkurranse poeng']:
            p = templ.parameters
            anon = [[k,p[k]] for k in p.keys() if type(k) == int]
            anon = sorted(anon, key = lambda x: x[0])
            anon = [a[1] for a in anon]
            named = [[k,p[k]] for k in p.keys() if type(k) != int]

            named = odict(named)
            key = anon[0].lower()

            if key == 'ny':
                rules.append(NewPageRule(anon[1]))

            elif key == 'kvalifisert':
                rules.append(QualiRule(anon[1]))

            elif key == 'byte':
                params = { 'points': anon[1] }
                if 'makspoeng' in named:
                    params['maxpoints'] = named['makspoeng']
                rules.append(ByteRule(**params))

            elif key == 'ord':
                params = { 'points': anon[1] }
                if 'makspoeng' in named:
                    params['maxpoints'] = named['makspoeng']
                rules.append(WordRule(**params))

            elif key == 'bilde':
                params = { 'points': anon[1] }
                if 'makspoeng' in named:
                    params['maxpoints'] = named['makspoeng']
                rules.append(ImageRule(**params))
            
            elif key == 'ref':
                params = { 'sourcepoints': anon[1], 'refpoints': anon[2] }
                rules.append(RefRule(**params))

            elif key == 'bytebonus':
                rules.append(ByteBonusRule(anon[1], anon[2]))

            else:
                raise ParseError('Ukjent argument gitt til {{ml|ukens konkurranse poeng}}: '+key)
        
        
        # Read status

        try:
            infoboks = dp.templates['infoboks ukens konkurranse'][0]
        except:
            raise ParseError('Klarte ikke å tolke innholdet i {{tl|infoboks ukens konkurranse}}-malen.')

        if 'år' in infoboks.parameters and 'uke' in infoboks.parameters:
            year = infoboks.parameters['år']
            week = infoboks.parameters['uke']
            self.start = datetime.datetime.strptime(year+' '+week+' 1 00 00', '%Y %W %w %H %M')
            self.end = datetime.datetime.strptime(year+' '+week+' 0 23 59', '%Y %W %w %H %M')
        elif 'start' in infoboks.parameters and 'slutt' in infoboks.parameters:
            startdt = infoboks.parameters['start']
            enddt = infoboks.parameters['slutt']
            self.start = datetime.datetime.strptime(startdt + ' 00 00', '%Y-%m-%d %H %M')
            self.end = datetime.datetime.strptime(enddt +' 23 59', '%Y-%m-%d %H %M')
        else:
            raise ParseError('Fant ikke uke/år eller start/slutt i {{tl|infoboks ukens konkurranse}}.')
        
        self.year= self.start.isocalendar()[0]
        self.week = self.start.isocalendar()[1]

        return rules, filters

    def plot(self):
        import matplotlib.pyplot as plt

        w = 14/2.54
        goldenratio = 1.61803399
        h = w/goldenratio
        fig = plt.figure( figsize=(w,h) )

        ax = fig.add_subplot(1,1,1, frame_on = False)
        ax.grid(True, which = 'major', color = 'gray', alpha = 0.5)
        fig.subplots_adjust(left=0.11, bottom=0.10, right=0.65, top=0.94)

        t0 = float(self.start.strftime('%s'))

        xt = t0 + np.arange(8) * 86400
        xt_mid = t0 + 43200 + np.arange(7) * 86400

        now = float(datetime.datetime.now().strftime('%s'))

        yall = []
        cnt = 0
        for u in self.users:
            if len(u.plotdata['x']) > 0:
                cnt += 1
                x = u.plotdata['x']
                y = u.plotdata['y']
                yall.extend(y)
                x.insert(0,xt[0])
                y.insert(0,0)
                if now < xt[-1]:
                    x.append(now)
                    y.append(y[-1])
                else:
                    x.append(xt[-1])
                    y.append(y[-1])
                l = ax.plot(x, y, linewidth=2., alpha = 0.5, label = u.name) #, markerfacecolor='#FF8C00', markeredgecolor='#888888', label = u.name)
                c = l[0].get_color()
                ax.plot(x[1:-1], y[1:-1], marker='.', markersize = 4, markerfacecolor=c, markeredgecolor=c, linewidth=0., alpha = 0.5) #, markerfacecolor='#FF8C00', markeredgecolor='#888888', label = u.name)
                if cnt >= 10:
                    break

        if now < xt[-1]:
            ax.axvline(now, color='red')

        ax.set_xticks(xt, minor = False)
        ax.set_xticklabels([], minor = False)
        
        ax.set_xticks(xt_mid, minor = True)
        ax.set_xticklabels(['Man','Tir','Ons','Tors','Fre','Lør','Søn'], minor = True)

        for i in range(1,7,2):
            ax.axvspan(xt[i], xt[i+1], facecolor='#000099', linewidth=0., alpha=0.03)

        for i in range(0,7,2):
            ax.axvspan(xt[i], xt[i+1], facecolor='#000099', linewidth=0., alpha=0.07)

        for line in ax.xaxis.get_ticklines(minor = False):
            line.set_markersize(0)

        for line in ax.xaxis.get_ticklines(minor = True):
            line.set_markersize(0)
        
        for line in ax.yaxis.get_ticklines(minor = False):
            line.set_markersize(0)

        ax.set_xlim(t0, xt[-1])
        ax.set_ylim(0, 1.05*np.max(yall))

        plt.legend()
        ax = plt.gca()
        ax.legend( 
            # ncol = 4, loc = 3, bbox_to_anchor = (0., 1.02, 1., .102), mode = "expand", borderaxespad = 0.
            loc = 2, bbox_to_anchor = (1.0, 1.0), borderaxespad = 0., frameon = 0.
        )
        plt.savefig('Nowp Ukens_konkurranse_%d-%d.png' % (self.year, self.week), dpi = 200)


############################################################################################################################
# Main 
############################################################################################################################

from wp_private import ukbotlogin
sites = {
    'no': mwclient.Site('no.wikipedia.org'),
    'nn': mwclient.Site('nn.wikipedia.org')
}
for site in sites.values():
    # login increases api limit from 50 to 500 
    site.login(*ukbotlogin)

#konkurranseside = 'Wikipedia:Ukens konkurranse/Ukens konkurranse ' + year + '-' + week
#konkurranseside = 'Wikipedia:Ukens konkurranse/Ukens konkurranse 2012-27'
konkurranseside = 'Bruker:UKBot/Sandkasse1'
kategoriside = 'Bruker:UKBot/cat-ignore'

try:
    uk = UK(sites['no'].pages[konkurranseside].edit(), sites['no'].pages[kategoriside].edit(), sites)
except ParseError as e:
    err = "\n* '''%s'''" % e.msg
    page = sites['no'].pages[konkurranseside]
    out = '\n{{Ukens konkurranse robotinfo | error | %s }}' % err
    page.save('dummy', summary = 'Resultatboten støtte på et problem', appendtext = out)
    raise

sql = sqlite3.connect('uk.db')


if __name__ == '__main__':

    # Loop over users
    for u in uk.users:
        print "=== %s ===" % u.name
        
        # First read contributions from db
        u.add_contribs_from_db(sql, uk.start, uk.end, sites)

        # Then fill in new contributions from wiki
        for site in sites.itervalues():
            u.add_contribs_from_wiki(site, uk.start, uk.end, fulltext = True)

        # And update db
        u.save_contribs_to_db(sql)

        try:

            # Filter out relevant articles
            u.filter(uk.filters)

            # And calculate points
            u.analyze(uk.rules)

        except ParseError as e:
            err = "\n* '''%s'''" % e.msg
            page = sites['no'].pages[konkurranseside]
            out = '\n{{Ukens konkurranse robotinfo | error | %s }}' % err
            page.save('dummy', summary = 'Resultatboten støtte på et problem', appendtext = out)
            raise

    # Sort users by points
    uk.users.sort( key = lambda x: x.points, reverse = True )

    # Plot
    #uk.plot()

    # Make outpage
    out = '== Resultater ==\n\n'
    out += "''Konkurransen er åpen fra %s til %s.''\n\n" % (uk.start.strftime('%e. %B %Y, %H:%M'), uk.end.strftime('%e. %B %Y, %H:%M'))
    for u in uk.users:
        out += u.format_result()

    now = datetime.datetime.now()
    errors = []
    for f in uk.filters:
        errors.extend(f.errors)
    for r in uk.rules:
        errors.extend(r.errors)
    if len(errors) == 0:
        out += '{{Ukens konkurranse robotinfo | ok | %s }}' % now.strftime('%F %T')
    else:
        err = ''.join("\n* %s:<br />%s" % (e['title'], e['text']) for e in errors)
        out += '{{Ukens konkurranse robotinfo | 1=note | 2=%s | 3=%s }}' % ( now.strftime('%F %T'), err )

    print " -> Updating wiki, section = %d " % (uk.results_section)
    page = sites['no'].pages[konkurranseside]
    page.save(out, summary = 'Oppdaterer resultater', section = uk.results_section)
    #print out

