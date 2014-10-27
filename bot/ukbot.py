#encoding=utf-8
from __future__ import unicode_literals
import matplotlib
matplotlib.use('svg')

import numpy as np
import time
import calendar
from datetime import datetime, timedelta
from datetime import time as dt_time
import gettext
import pytz
from isoweek import Week  # Sort-of necessary until datetime supports %V, see http://bugs.python.org/issue12006
                          # and See http://stackoverflow.com/questions/5882405/get-date-from-iso-week-number-in-python
import re
import json
import sqlite3
import yaml
from odict import odict
import urllib
import argparse
import codecs

import mwclient
from mwtemplates import TemplateEditor
from mwtextextractor import get_body_text
import ukcommon
from ukcommon import log, init_localization

import locale

import logging
logger = logging.getLogger()
logger.setLevel(logging.WARN)

#locale.setlocale(locale.LC_TIME, 'no_NO'.encode('utf-8'))

# Read args

parser = argparse.ArgumentParser(description='The UKBot')
parser.add_argument('--page', required=False, help='Name of the contest page to work with')
parser.add_argument('--simulate', action='store_true', default=False, help='Do not write results to wiki')
parser.add_argument('--output', nargs='?', default='', help='Write results to file')
parser.add_argument('--log', nargs='?', default='', help='Log file')
parser.add_argument('--verbose', action='store_true', default=False, help='More verbose logging')
parser.add_argument('--close', action='store_true', help='Close contest')
parser.add_argument('--config', nargs='?', default='config.yml', help='Config file')
args = parser.parse_args()

if args.log != '':
    ukcommon.logfile = open(args.log, 'a')

config = yaml.load(open(args.config, 'r'))
wiki_tz = pytz.timezone(config['wiki_timezone'])
server_tz = pytz.timezone(config['server_timezone'])

t, _ = init_localization(config['locale'])

runstart = server_tz.localize(datetime.now())
log('-----------------------------------------------------------------')
log('UKBot starting at %s (server time), %s (wiki time)' % (runstart.strftime('%F %T'), runstart.astimezone(wiki_tz).strftime('%F %T')))

from ukrules import *
from ukfilters import *

    # Settings
# Suggested crontab:
## Oppdater resultater annenhver time mellom kl 8 og 22 samt kl 23 og 01...
#0 8-22/2,23,1 * * * nice -n 11 /uio/arkimedes/s01/dmheggo/wikipedia/UKBot/bot.sh
## ... og ved midnatt tirsdag til søndag (2-6,0)
#0 0 * * 2-6,0 nice -n 11 /uio/arkimedes/s01/dmheggo/wikipedia/UKBot/bot.sh
## Midnatt natt til mandag avslutter vi konkurransen
#0 0 * * 1 nice -n 11 /uio/arkimedes/s01/dmheggo/wikipedia/UKBot/ended.sh
## og så sjekker vi om det er klart for å sende ut resultater
#20 8-23/1 * * 1-2 nice -n 11 /uio/arkimedes/s01/dmheggo/wikipedia/UKBot/close.sh
#20 */12 * * 3-6 nice -n 11 /uio/arkimedes/s01/dmheggo/wikipedia/UKBot/close.sh
## Hver natt kl 00.30 laster vi opp ny figur
#30 0 * * * nice -n 11 /uio/arkimedes/s01/dmheggo/wikipedia/UKBot/uploadbot.sh

#from ete2 import Tree

#from progressbar import ProgressBar, Counter, Timer, SimpleProgress
#pbar = ProgressBar(widgets = ['Processed: ', Counter(), ' revisions (', Timer(), ')']).start()
#pbar.maxval = pbar.currval + 1
#pbar.update(pbar.currval+1)
#pbar.finish()


def unix_time(dt):
    """ OS-independent method to get unix time from a datetime object (strftime('%s') does not work on solaris) """
    epoch = pytz.utc.localize(datetime.utcfromtimestamp(0))
    delta = dt - epoch
    return delta.total_seconds()


class ParseError(Exception):
    """Raised when wikitext input is not on the expected form, so we don't find what we're looking for"""

    def __init__(self, msg):
        self.msg = msg


class Site(mwclient.Site):

    def __init__(self, host, username, password):

        self.errors = []
        self.name = host
        self.key = host.split('.')[0]
        log('@ Initializing site: %s' % host)
        mwclient.Site.__init__(self, host, clients_useragent='UKBot [[:no:Bruker:UKBot]]')
        # Login to increase api limit from 50 to 500
        self.login(username, password)


class Article(object):

    def __init__(self, site, user, name):
        """
        An article is uniquely identified by its name and its site
        """
        self.site = site
        self.user = user
        #self.site_key = site.host.split('.')[0]
        self.name = name
        self.disqualified = False

        self.revisions = odict()
        #self.redirect = False
        self.errors = []

    def __eq__(other):
        if self.site == other.site and self.name == other.name:
            return True
        else:
            return False

    def __repr__(self):
        return ("<Article %s:%s for user %s>" % (self.site.key, self.name, self.user.name)).encode('utf-8')

    @property
    def new(self):
        return self.revisions[self.revisions.firstkey()].new

    @property
    def new_non_redirect(self):
        firstrev = self.revisions[self.revisions.firstkey()]
        return firstrev.new and not firstrev.redirect

    def add_revision(self, revid, **kwargs):
        self.revisions[revid] = Revision(self, revid, **kwargs)
        return self.revisions[revid]

    @property
    def bytes(self):
        return np.sum([rev.bytes for rev in self.revisions.itervalues()])

    @property
    def words(self):
        return np.sum([rev.words for rev in self.revisions.itervalues()])

    @property
    def points(self):
        """ The article score is the sum of the score for its revisions, independent of whether the article is disqualified or not """
        return self.get_points()
        #return np.sum([rev.get_points() for rev in self.revisions.values()])

    def get_points(self, ptype='', ignore_max=False, ignore_suspension_period=False,
                   ignore_disqualification=False, ignore_point_deductions=False):
        p = 0.
        article_key = self.site.key + ':' + self.name
        if ignore_disqualification or not article_key in self.user.disqualified_articles:
            for revid, rev in self.revisions.iteritems():
                dt = pytz.utc.localize(datetime.fromtimestamp(rev.timestamp))
                if ignore_suspension_period is True or self.user.suspended_since is None or dt < self.user.suspended_since:
                    p += rev.get_points(ptype, ignore_max, ignore_point_deductions)
                else:
                    if self.user.contest.verbose:
                        log('!! Skipping revision %d in suspension period' % revid)

        return p
        #return np.sum([a.points for a in self.articles.values()])


class Revision(object):

    def __init__(self, article, revid, **kwargs):
        """
        A revision is uniquely identified by its revision id and its site

        Arguments:
          - article: (Article) article object reference
          - revid: (int) revision id
        """
        self.article = article
        self.errors = []

        self.revid = revid
        self.size = -1
        self.text = ''
        self.point_deductions = []

        self.parentid = 0
        self.parentsize = 0
        self.parenttext = ''
        self.username = ''

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
            elif k == 'username':
                self.username = v[0].upper() + v[1:]
            else:
                raise StandardError('add_revision got unknown argument %s' % k)

        for pd in self.article.user.point_deductions:
            if pd[0] == self.revid:
                self.add_point_deduction(pd[1], pd[2])


    def __repr__(self):
        return ("<Revision %d for %s:%s>" % (self.revid, self.site.key, self.article.name)).encode('utf-8')

    @property
    def bytes(self):
        return self.size - self.parentsize

    @property
    def words(self):
        try:
            return self._wordcount
        except:
            mt1 = get_body_text(self.text)
            mt2 = get_body_text(self.parenttext)
            log("Wordcount: %d -> %d" % ( len(mt2.split()), len(mt1.split()) ))
            self._wordcount = len(mt1.split()) - len(mt2.split())
            if not self.new and len(mt2.split()) == 0 and self._wordcount > 1:
                w = _('Revision [//%(host)s/w/index.php?diff=prev&oldid=%(revid)s %(revid)s]: The word count difference might be wrong, because no words were found in the parent revision (%(parentid)s) of size %(size)d, possibly due to unclosed tags or templates in that revision.') % { 'host': self.article.site.host, 'revid': self.revid, 'parentid': self.parentid, 'size': len(self.parenttext) }
                log('-------------------------------------------------------------------')
                log('[WARN] ' + w)
                #log(self.parenttext)
                log('-------------------------------------------------------------------')
                self.errors.append(w)
            elif self._wordcount > 10 and self._wordcount > self.bytes:
                w = _('Revision [//%(host)s/w/index.php?diff=prev&oldid=%(revid)s %(revid)s]: The word count difference might be wrong, because the word count increase (%(words)d) is larger than the byte increase (%(bytes)d). Wrong word counts may occur for invalid wiki text.') % { 'host': self.article.site.host, 'revid': self.revid, 'words': self._wordcount, 'bytes': self.bytes }
                log('-------------------------------------------------------------------')
                log('[WARN] ' + w)
                #log(self.parenttext)
                log('-------------------------------------------------------------------')
                self.errors.append(w)

            #s = _('A problem encountered with revision %(revid)d may have influenced the word count for this revision: <nowiki>%(problems)s</nowiki> ')
            #s = _('Et problem med revisjon %d kan ha påvirket ordtellingen for denne: <nowiki>%s</nowiki> ')
            del mt1
            del mt2
            # except DanmicholoParseError as e:
            #     log("!!!>> FAIL: %s @ %d" % (self.article.name, self.revid))
            #     self._wordcount = 0
            #     #raise
            return self._wordcount

    @property
    def new(self):
        return (self.parentid == 0)

    @property
    def redirect(self):
        return bool(re.match(r'#(OMDIRIGER|OMDIRIGERING|REDIRECT|OHJAUS|UUDELLEENOHJAUS|STIVREN)', self.text, re.IGNORECASE))

    @property
    def parentredirect(self):
        return bool(re.match(r'#(OMDIRIGER|OMDIRIGERING|REDIRECT|OHJAUS|UUDELLEENOHJAUS|STIVREN)', self.parenttext, re.IGNORECASE))

    def get_link(self):
        """ returns a link to revision """
        q = {'title': self.article.name.encode('utf-8'), 'oldid': self.revid}
        if not self.new:
            q['diff'] = 'prev'
        return '//' + self.article.site.host + self.article.site.site['script'] + '?' + urllib.urlencode(q)

    def get_parent_link(self):
        """ returns a link to parent revision """
        q = {'title': self.article.name.encode('utf-8'), 'oldid': self.parentid}
        return '//' + self.article.site.host + self.article.site.site['script'] + '?' + urllib.urlencode(q)

    def get_points(self, ptype='', ignore_max=False, ignore_point_deductions=False):
        p = 0.0
        for pnt in self.points:
            if ptype == '' or pnt[1] == ptype:
                if ignore_max and len(pnt) > 3:
                    p += pnt[3]
                else:
                    p += pnt[0]

        if not ignore_point_deductions and (ptype == '' or ptype == 'trekk'):
            for points, reason in self.point_deductions:
                p -= points

        return p

    def add_point_deduction(self, points, reason):
        log('Revision %s: Removing %d points for reason: %s' % (self.revid, points, reason))
        self.point_deductions.append([points, reason])


class User(object):

    def __init__(self, username, contest):
        self.name = username
        self.articles = odict()
        self.contest = contest
        self.suspended_since = None
        self.disqualified_articles = []
        self.point_deductions = []

    def __repr__(self):
        return ("<User %s>" % self.name).encode('utf-8')

    @property
    def revisions(self):
        # oh my, funny (and fast) one-liner for making a flat list of revisions
        return {rev.revid: rev for article in self.articles.values() for rev in article.revisions.values()}

    def sort_contribs(self):

        # sort revisions by revision id
        for article in self.articles.itervalues():
            article.revisions.sort(key=lambda x: x[0])   # sort by key (revision id)

        # sort articles by first revision id
        self.articles.sort(key=lambda x: x[1].revisions.firstkey())

    def add_article_if_necessary(self, site_key, article_title):
        article_key = site_key + ':' + article_title

        if not article_key in self.articles:
            self.articles[article_key] = Article(site, self, article_title)
            if article_key in self.disqualified_articles:
                self.articles[article_key].disqualified = True

        return self.articles[article_key]

    def add_contribs_from_wiki(self, site, start, end, fulltext=False, **kwargs):
        """
        Populates self.articles with entries from the API.

            site      : mwclient.client.Site object
            start     : datetime object with timezone Europe/Oslo
            end       : datetime object with timezone Europe/Oslo
            fulltext  : get revision fulltexts
        """
        apilim = 50
        if 'bot' in site.rights:
            apilim = site.api_limit         # API limit, should be 500

        site_key = site.host.split('.')[0]

        ts_start = start.astimezone(pytz.utc).strftime('%FT%TZ')
        ts_end = end.astimezone(pytz.utc).strftime('%FT%TZ')

        # 1) Fetch user contributions

        args = {}
        if 'namespace' in kwargs:
            args['namespace'] = kwargs['namespace']
            log(' -> Limiting to namespace: %d' % args['namespace'])

        #new_articles = []
        new_revisions = []
        n_articles = len(self.articles)
        for c in site.usercontributions(self.name, ts_start, ts_end, 'newer', prop='ids|title|timestamp|comment', **args):
            #pageid = c['pageid']
            if 'comment' in c:
                article_comment = c['comment']

                ignore = False
                if 'ignore' in self.contest.config:
                    for ign in self.contest.config['ignore']:
                        if re.search(ign, article_comment):
                            ignore = True

                if ignore:
                    log(' Revision %d of %s ignored as rollback' % (c['revid'], c['title']))
                else:
                    rev_id = c['revid']
                    article_title = c['title']
                    article_key = site_key + ':' + article_title

                    if rev_id in self.revisions:
                        # We check self.revisions instead of article.revisions, because the revision may
                        # already belong to "another article" (another title) if the article has been moved

                        if self.revisions[rev_id].article.name != article_title:
                            rev = self.revisions[rev_id]
                            log(' -> Moving revision %d from "%s" to "%s"' % (rev_id, rev.article.name, article_title))
                            article = self.add_article_if_necessary(site_key, article_title)
                            rev.article.revisions.pop(rev_id)  # remove from old article
                            article.revisions[rev_id] = rev    # add to new article
                            rev.article = article              # and update reference

                    else:

                        article = self.add_article_if_necessary(site_key, article_title)
                        rev = article.add_revision(rev_id, timestamp=time.mktime(c['timestamp']), username=self.name)
                        new_revisions.append(rev)

        # If revisions were moved from one article to another, and the redirect was not created by the same user,
        # some articles may now have zero revisions. We should drop them
        for article_key, article in self.articles.iteritems():
            if len(article.revisions) == 0:
                log('--> Dropping article "%s" due to zero remaining revisions' % (article.name))
                del self.articles[article_key]

        # Always sort after we've added contribs
        new_articles = len(self.articles) - n_articles
        self.sort_contribs()
        if len(new_revisions) > 0 or new_articles > 0:
            log(" -> [%s] Added %d new revisions, %d new articles from API" % (site_key, len(new_revisions), new_articles))

        # 2) Check if pages are redirects (this information can not be cached, because other users may make the page a redirect)
        #    If we fail to notice a redirect, the contributions to the page will be double-counted, so lets check

        #titles = [a.name for a in self.articles.values() if a.site.key == site_key]
        #for s0 in range(0, len(titles), apilim):
        #    ids = '|'.join(titles[s0:s0+apilim])
        #    for page in site.api('query', prop = 'info', titles = ids)['query']['pages'].itervalues():
        #        article_key = site_key + ':' + page['title']
        #        self.articles[article_key].redirect = ('redirect' in page.keys())

        # 3) Fetch info about the new revisions: diff size, possibly content

        props = 'ids|size'
        if fulltext:
            props += '|content'
        revids = [str(r.revid) for r in new_revisions]
        parentids = []
        nr = 0
        for s0 in range(0, len(new_revisions), apilim):
            #print "API limit is ",apilim," getting ",s0
            ids = '|'.join(revids[s0:s0 + apilim])
            for page in site.api('query', prop='revisions', rvprop=props, revids=ids)['query']['pages'].itervalues():
                article_key = site_key + ':' + page['title']
                for apirev in page['revisions']:
                    nr += 1
                    rev = self.articles[article_key].revisions[apirev['revid']]
                    rev.parentid = apirev['parentid']
                    rev.size = apirev['size']
                    if '*' in apirev.keys():
                        rev.text = apirev['*']
                    if not rev.new:
                        parentids.append(rev.parentid)
        if nr > 0:
            log(" -> [%s] Checked %d of %d revisions, found %d parent revisions" % (site_key, nr, len(new_revisions), len(parentids)))

        if nr != len(new_revisions):
            raise StandardError("Did not get all revisions")

        # 4) Fetch info about the parent revisions: diff size, possibly content

        props = 'ids|size'
        if fulltext:
            props += '|content'
        nr = 0
        parentids = [str(i) for i in parentids]
        for s0 in range(0, len(parentids), apilim):
            ids = '|'.join(parentids[s0:s0 + apilim])
            for page in site.api('query', prop='revisions', rvprop=props, revids=ids)['query']['pages'].itervalues():
                article_key = site_key + ':' + page['title']
                
                # In the case of a merge, the new title (article_key) might not be part of the user's 
                # contribution list (self.articles), so we need to check:
                if article_key in self.articles:
                    article = self.articles[article_key]
                    for apirev in page['revisions']:
                        nr += 1
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
        if nr > 0:
            log(" -> [%s] Checked %d parent revisions" % (site_key, nr))

    def save_contribs_to_db(self, sql):
        """ Save self.articles to DB so it can be read by add_contribs_from_db """

        cur = sql.cursor()
        nrevs = 0
        ntexts = 0

        for article_key, article in self.articles.iteritems():
            site_key = article.site.key

            for revid, rev in article.revisions.iteritems():
                ts = datetime.fromtimestamp(rev.timestamp).strftime('%F %T')

                # Save revision if not already saved
                if len(cur.execute(u'SELECT revid FROM contribs WHERE revid=? AND site=?', [revid, site_key]).fetchall()) == 0:
                    cur.execute(u'INSERT INTO contribs (revid, site, parentid, user, page, timestamp, size, parentsize) VALUES (?,?,?,?,?,?,?,?)',
                                (revid, site_key, rev.parentid, self.name, article.name, ts, rev.size, rev.parentsize))
                    nrevs += 1

                # Save revision text if we have it and if not already saved
                if len(rev.text) > 0 and len(cur.execute(u'SELECT revid FROM fulltexts WHERE revid=? AND site=?', [revid, site_key]).fetchall()) == 0:
                    cur.execute(u'INSERT INTO fulltexts (revid, site, revtxt) VALUES (?,?,?)', (revid, site_key, rev.text))
                    ntexts += 1

                # Save parent revision text if we have it and if not already saved
                if len(rev.parenttext) > 0 and len(cur.execute(u'SELECT revid FROM fulltexts WHERE revid=? AND site=?', [rev.parentid, site_key]).fetchall()) == 0:
                    cur.execute(u'INSERT INTO fulltexts (revid, site, revtxt) VALUES (?,?,?)', (rev.parentid, site_key, rev.parenttext))
                    ntexts += 1

        sql.commit()
        cur.close()
        if nrevs > 0 or ntexts > 0:
            log(" -> Wrote %d revisions and %d fulltexts to DB" % (nrevs, ntexts))

    def add_contribs_from_db(self, sql, start, end, sites):
        """
        Populates self.articles with entries from SQLite DB

            sql   : sqlite3.Connection object
            start : datetime object
            end   : datetime object
        """
        cur = sql.cursor()
        cur2 = sql.cursor()
        ts_start = start.astimezone(pytz.utc).strftime('%F %T')
        ts_end = end.astimezone(pytz.utc).strftime('%F %T')
        nrevs = 0
        narts = 0
        for row in cur.execute(u"""SELECT revid, site, parentid, page, timestamp, size, parentsize FROM contribs
                                   WHERE user=? AND timestamp >= ? AND timestamp <= ?""", (self.name, ts_start, ts_end)):

            rev_id, site_key, parent_id, article_title, ts, size, parentsize = row
            article_key = site_key + ':' + article_title

            ts = unix_time(pytz.utc.localize(datetime.strptime(ts, '%Y-%m-%d %H:%M:%S')))

            # Add article if not present
            if not article_key in self.articles:
                narts += 1
                self.articles[article_key] = Article(sites[site_key], self, article_title)
                if article_key in self.disqualified_articles:
                    self.articles[article_key].disqualified = True
            article = self.articles[article_key]

            # Add revision if not present
            if not rev_id in self.revisions:
                nrevs += 1
                article.add_revision(rev_id, timestamp=ts, parentid=parent_id, size=size, parentsize=parentsize, username=self.name)
            rev = self.revisions[rev_id]

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

        if nrevs > 0 or narts > 0:
            log(" -> Added %d revisions, %d articles from DB" % (nrevs, narts))

    def filter(self, filters, serial=False):

        if serial:
            for filter in filters:
                if self.contest.verbose:
                    log('>> Before %s (%d) : %s' % (type(filter).__name__, len(self.articles), ', '.join(self.articles.keys())))

                self.articles = filter.filter(self.articles)

                if self.contest.verbose:
                    log('>> After %s (%d) : %s' % (type(filter).__name__, len(self.articles), ', '.join(self.articles.keys())))
        else:
            articles = odict([])
            if self.contest.verbose:
                log('>> Before filtering (%d) : %s' % (len(self.articles), ', '.join(self.articles.keys())))
            for filter in filters:
                for a in filter.filter(self.articles):
                    if a not in articles:
                        #print a
                        articles[a] = self.articles[a]
                if self.contest.verbose:
                    log('>> After %s (%d) : %s' % (type(filter).__name__, len(articles), ', '.join(articles.keys())))
            self.articles = articles

        # We should re-sort afterwards since not all filters preserve the order (notably the CatFilter)
        self.sort_contribs()

        log(" -> %d articles remain after filtering" % len(self.articles))
        if self.contest.verbose:
            log('----')
            for a in self.articles.iterkeys():
                log('%s' % a)
            log('----')

    @property
    def bytes(self):
        return np.sum([a.bytes for a in self.articles.itervalues()])

    @property
    def newpages(self):
        return np.sum([1 for a in self.articles.itervalues() if a.new_non_redirect])

    @property
    def words(self):
        return np.sum([a.words for a in self.articles.itervalues()])

    @property
    def points(self):
        """ The points for all the user's articles, excluding disqualified ones """
        p = 0.
        for article_key, article in self.articles.iteritems():
            p += article.get_points()
        return p
        #return np.sum([a.points for a in self.articles.values()])

    def analyze(self, rules):

        x = []
        y = []
        utc = pytz.utc

        # loop over articles
        for article_key, article in self.articles.iteritems():
            if self.contest.verbose:
                log(article_key)
            else:
                log('.', newline=False)
            #log(article_key)

            # loop over revisions
            for revid, rev in article.revisions.iteritems():

                rev.points = []

                # loop over rules
                for rule in rules:
                    #log('   %d : %s' % (revid, type(rule).__name__))
                    rule.test(rev)

                if not article.disqualified:

                    dt = pytz.utc.localize(datetime.fromtimestamp(rev.timestamp))
                    if self.suspended_since is None or dt < self.suspended_since:

                        if rev.get_points() > 0:
                            #print self.name, rev.timestamp, rev.get_points()
                            ts = float(unix_time(utc.localize(datetime.fromtimestamp(rev.timestamp)).astimezone(wiki_tz)))
                            x.append(ts)
                            y.append(float(rev.get_points()))
                            
                            if self.contest.verbose:
                                log('    %d : %d ' % (revid, rev.get_points()))

        x = np.array(x)
        y = np.array(y)

        o = np.argsort(x)
        x = x[o]
        y = y[o]
        #pl = np.array(pl, dtype=float)
        #pl.sort(axis = 0)
        y2 = np.array([np.sum(y[:q + 1]) for q in range(len(y))])
        self.plotdata = np.column_stack((x, y2))
        #np.savetxt('user-%s'%self.name, np.column_stack((x,y,y2)))

    def format_result(self, pos=-1, closing=False, prices=[]):

        entries = []
        config = self.contest.config

        utc = pytz.utc

        if self.contest.verbose:
            log('Formatting results for user %s' % self.name)
        # loop over articles
        for article_key, article in self.articles.iteritems():

            brutto = article.get_points(ignore_suspension_period=True, ignore_point_deductions=True, ignore_disqualification=True)
            netto = article.get_points()

            if brutto == 0.0:

                if self.contest.verbose:
                    log('    %s: skipped (0 points)' % article_key)

            else:

                # loop over revisions
                revs = []
                for revid, rev in article.revisions.iteritems():

                    if len(rev.points) > 0:
                        descr = ' + '.join(['%.1f p (%s)' % (p[0], p[2]) for p in rev.points])
                        for p in rev.point_deductions:
                            if p[0] > 0:
                                descr += ' <span style="color:red">− %.1f p (%s)</span>' % (p[0], p[1])
                            else:
                                descr += ' <span style="color:#44bb44">+ %.1f p (%s)</span>' % (-p[0], p[1])

                        dt = utc.localize(datetime.fromtimestamp(rev.timestamp))
                        dt_str = dt.astimezone(wiki_tz).strftime(_('%A, %H:%M')).decode('utf-8')
                        out = '[%s %s]: %s' % (rev.get_link(), dt_str, descr)
                        if self.suspended_since is not None and dt > self.suspended_since:
                            out = '<s>' + out + '</s>'
                        if len(rev.errors) > 0:
                            out = '[[File:Ambox warning yellow.svg|12px|%s]] ' % (', '.join(rev.errors)) + out
                        revs.append(out)

                titletxt = ''
                try:
                    titletxt = "''" + _('Category hit') + "'': " + ' &gt; '.join(article.cat_path) + '<br />'
                except AttributeError:
                    pass
                titletxt += '<br />'.join(revs)
                # if len(article.point_deductions) > 0:
                #     pds = []
                #     for points, reason in article.point_deductions:
                #         pds.append('%.f p: %s' % (-points, reason))
                #     titletxt += '<div style="border-top:1px solid #CCC">\'\'' + _('Notes') + ':\'\'<br />%s</div>' % '<br />'.join(pds)

                titletxt += '<div style="border-top:1px solid #CCC">' + _('Total: {{formatnum:%(bytecount)d}} bytes, %(wordcount)d words') % {'bytecount': article.bytes, 'wordcount': article.words} + '.</div>'

                p = '%.1f p' % brutto
                if brutto != netto:
                    p = '<s>' + p + '</s> '
                    if netto != 0.:
                        p += '%.1f p' % netto

                out = '[[:%s|%s]]' % (article_key, article.name)
                if article_key in self.disqualified_articles:
                    out = '[[File:Qsicon Achtung.png|14px]] <s>' + out + '</s>'
                    titletxt += '<div style="border-top:1px solid red; background:#ffcccc;">' + _('<strong>Note:</strong> The contributions to this article are currently disqualified.') + '</div>'
                elif brutto != netto:
                    out = '[[File:Qsicon Achtung.png|14px]] ' + out
                    #titletxt += '<div style="border-top:1px solid red; background:#ffcccc;"><strong>Merk:</strong> En eller flere revisjoner er ikke talt med fordi de ble gjort mens brukeren var suspendert. Hvis suspenderingen oppheves vil bidragene telle med.</div>'
                if article.new:
                    out += ' ' + _('<abbr class="newpage" title="New page">N</abbr>')
                out += ' (<abbr class="uk-ap">%s</abbr>)' % p

                out = '# ' + out
                out += '<div class="uk-ap-title" style="font-size: smaller; color:#888; line-height:100%;">' + titletxt + '</div>'

                entries.append(out)
                if self.contest.verbose:
                    log('    %s: %.f / %.f points' % (article_key, netto, brutto), newline=False)

        ros = ''
        if closing:
            if pos == 0:
                for r in prices:
                    if r[1] == 'winner':
                        ros += '[[File:%s|20px]] ' % config['awards'][r[0]]['file']
                        break
            for r in prices:
                if r[1] == 'pointlimit' and self.points >= r[2]:
                    ros += '[[File:%s|20px]] ' % config['awards'][r[0]]['file']
                    break
        suspended = ''
        if self.suspended_since is not None:
            suspended = ', ' + _('suspended since') + ' %s' % self.suspended_since.strftime(_('%A, %H:%M')).decode('utf-8')
        userprefix = self.contest.homesite.namespaces[2]
        out = '=== %s [[%s:%s|%s]] (%.f p%s) ===\n' % (ros, userprefix, self.name, self.name, self.points, suspended)
        if len(entries) == 0:
            out += "''" + _('No qualifying contributions registered yet') + "''"
        else:
            out += '%d %s, {{formatnum:%.2f}} kB\n' % (len(entries), _('articles'), self.bytes / 1000.)
        if len(entries) > 10:
            out += _('{{Kolonner}}\n')
        out += '\n'.join(entries)
        out += '\n\n'

        return out


class UK(object):

    def __init__(self, page, catignore, sites, homesite, sql, config, verbose=False):
        """
            page: mwclient.Page object
            catignore: string
            sites: list
            sql: sqlite3 object
            verbose: boolean
        """
        self.page = page
        self.name = self.page.name
        self.config = config
        self.homesite = homesite
        resultsSection = config['contestPages']['resultsSection']
        txt = page.edit()
        m = re.search('==\s*' + resultsSection + '\s*==', txt)
        if not m:
            raise ParseError(_('Found no "%(section)s" sections in the page "%(page)s"') % {'section': resultsSection, 'page': self.page.name})

        txt = txt[:m.end()]

        self.verbose = verbose
        self.sql = sql
        sections = [s.strip() for s in re.findall('^[\s]*==([^=]+)==', txt, flags=re.M)]
        self.results_section = sections.index(resultsSection) + 1

        self.sites = sites
        self.users = [User(n, self) for n in self.extract_userlist(txt)]
        self.rules, self.filters = self.extract_rules(txt, catignore)

        if self.startweek == self.endweek:
            log('@ Week %d' % self.startweek)
        else:
            log('@ Week %d–%d' % (self.startweek, self.endweek))

    def extract_userlist(self, txt):
        lst = []
        m = re.search('==\s*' + self.config['contestPages']['participantsSection'] + '\s*==', txt)
        if not m:
            raise ParseError(_("Couldn't find the list of participants!"))
        deltakerliste = txt[m.end():]
        m = re.search('==[^=]+==', deltakerliste)
        if not m:
            raise ParseError('Fant ingen overskrift etter deltakerlisten!')
        deltakerliste = deltakerliste[:m.start()]
        for d in deltakerliste.split('\n'):
            q = re.search(r'\[\[([^:]+):([^|\]]+)', d)
            if q:
                lst.append(q.group(2))
        log("@ Found %d participants" % (len(lst)))
        return lst

    def extract_rules(self, txt, catignore_txt):
        rules = []
        filters = []
        config = self.config

        dp = TemplateEditor(txt)
        if catignore_txt == '':
            catignore = []
            log('Note: Empty catignore page')
        else:

            if not config['templates']['rule']['name'] in dp.templates:
                raise ParseError(_('There are no point rules defined for this contest. Point rules are defined by {{tl|%(template)s}}.') % {'template': config['templates']['rule']['name']})

            #if not 'ukens konkurranse kriterium' in dp.templates.keys():
            #    raise ParseError('Denne konkurransen har ingen bidragskriterier. Kriterier defineres med {{tl|ukens konkurranse kriterium}}.')

            infobox = config['templates']['infobox']
            if not infobox['name'] in dp.templates:
                raise ParseError(_('This contest is missing a {{tl|%(template)s}} template.') % {'template': infobox['name']})

            try:
                m = re.search(r'<pre>(.*?)</pre>', catignore_txt, flags=re.DOTALL)
                catignore = m.group(1).strip().splitlines()
            except (IndexError, KeyError):
                raise ParseError(_('Could not parse the catignore page'))

        ######################## Read filters ########################

        nfilters = 0
        #print dp.templates.keys()
        filtercfg = config['templates']['filter']
        if filtercfg['name'] in dp.templates:
            for templ in dp.templates[filtercfg['name']]:

                par = templ.parameters
                anon = templ.get_anonymous_parameters()

                key = anon[1].lower()
                params = {'verbose': self.verbose}
                if key == filtercfg['new']:
                    if templ.has_param(filtercfg['redirects']):
                        params['redirects'] = True
                    filt = NewPageFilter(**params)

                elif key == filtercfg['existing']:
                    filt = ExistingPageFilter(**params)

                # elif key == 'stubb':
                #     filt = StubFilter(**params)

                elif key == filtercfg['template']:
                    if len(anon) < 3:
                        raise ParseError(_('No template (second argument) given to {{tlx|%(template)s|%(firstarg)s}}') % {'template': filtercfg['name'], 'firstarg': filtercfg['template']})
                    if templ.has_param(filtercfg['alias']):
                        params['aliases'] = [a.strip() for a in par[filtercfg['alias']].split(',')]
                    params['templates'] = anon[2:]
                    filt = TemplateFilter(**params)

                elif key == filtercfg['bytes']:
                    if len(anon) < 3:
                        raise ParseError(_('No byte limit (second argument) given to {{tlx|%(template)s|%(firstarg)s}}') % {'template': filtercfg['name'], 'firstarg': filtercfg['bytes']})
                    params['bytelimit'] = anon[2]
                    filt = ByteFilter(**params)

                elif key == filtercfg['category']:
                    if len(anon) < 3:
                        raise ParseError(_('No categories given to {{tlx|%(template)s|%(firstarg)s}}') % {'template': filtercfg['name'], 'firstarg': filtercfg['bytes']})
                    params['sites'] = self.sites
                    params['catnames'] = anon[2:]
                    params['ignore'] = catignore
                    if templ.has_param(filtercfg['maxdepth']):
                        params['maxdepth'] = int(par[filtercfg['maxdepth']])
                    filt = CatFilter(**params)

                elif key == filtercfg['backlink']:
                    params['sites'] = self.sites
                    params['articles'] = anon[2:]
                    filt = BackLinkFilter(**params)

                elif key == filtercfg['forwardlink']:
                    params['sites'] = self.sites
                    params['articles'] = anon[2:]
                    filt = ForwardLinkFilter(**params)

                elif key == filtercfg['namespace']:
                    params['namespace'] = int(anon[2])
                    filt = NamespaceFilter(**params)

                elif key == filtercfg['pages']:
                    params['sites'] = self.sites
                    params['pages'] = anon[2:]
                    filt = PageFilter(**params)

                else:
                    raise ParseError(_('Unknown argument given to {{tl|%(template)s}}: %(argument)s') % {'template': filtercfg['name'], 'argument': key})

                foundfilter = False
                for f in filters:
                    if type(f) == type(filt):
                        foundfilter = True
                        f.extend(filt)
                if not foundfilter:
                    nfilters += 1
                    filters.append(filt)

        ######################## Read rules ########################

        rulecfg = config['templates']['rule']
        nrules = 0
        for templ in dp.templates[rulecfg['name']]:
            nrules += 1
            p = templ.parameters
            anon = templ.get_anonymous_parameters()

            key = anon[1].lower()
            maxpoints = rulecfg['maxpoints']

            if key == rulecfg['new']:
                rules.append(NewPageRule(key, anon[2]))

            elif key == rulecfg['redirect']:
                rules.append(RedirectRule(key, anon[2]))

            elif key == rulecfg['qualified']:
                rules.append(QualiRule(key, anon[2]))

            elif key == rulecfg['refsectionfi']:
                params = {'key': key, 'points': anon[2]}
                if templ.has_param(maxpoints):
                    params['maxpoints'] = p[maxpoints]
                rules.append(RefSectionFiRule(**params))

            # elif key == 'stubb':
            #     rules.append(StubRule(anon[1]))

            elif key == rulecfg['byte']:
                params = {'key': key, 'points': anon[2]}
                if templ.has_param(maxpoints):
                    params['maxpoints'] = p[maxpoints]
                rules.append(ByteRule(**params))

            elif key == rulecfg['word']:
                params = {'key': key, 'points': anon[2]}
                if templ.has_param(maxpoints):
                    params['maxpoints'] = p[maxpoints]
                rules.append(WordRule(**params))

            elif key == rulecfg['image']:
                params = {'key': key, 'points': anon[2]}
                if templ.has_param(maxpoints):
                    params['maxpoints'] = p[maxpoints]
                if templ.has_param(rulecfg['own']):
                    params['own'] = p[rulecfg['own']]
                if templ.has_param(rulecfg['maxinitialcount']):
                    params['maxinitialcount'] = p[rulecfg['maxinitialcount']]
                rules.append(ImageRule(**params))

            elif key == rulecfg['external_link']:
                params = {'key': key, 'points': anon[2]}
                if templ.has_param(maxpoints):
                    params['maxpoints'] = p[maxpoints]
                rules.append(ExternalLinkRule(**params))

            elif key == rulecfg['ref']:
                params = {'key': key, 'sourcepoints': anon[2], 'refpoints': anon[3]}
                rules.append(RefRule(**params))

            elif key == rulecfg['templateremoval']:
                params = {'key': key, 'points': anon[2], 'template': anon[3]}
                if templ.has_param(rulecfg['alias']):
                    params['aliases'] = [a.strip() for a in p[rulecfg['alias']].value.split(',')]
                rules.append(TemplateRemovalRule(**params))

            elif key == rulecfg['bytebonus']:
                rules.append(ByteBonusRule(key, anon[2], anon[3]))

            elif key == rulecfg['wordbonus']:
                rules.append(WordBonusRule(key, anon[2], anon[3]))

            else:
                raise ParseError(_('Unkown argument given to {{tl|%(template)s}}: %(argument)s') % {'template': rulecfg['name'], 'argument': key})

        log("@ Found %d filters and %d rules" % (nfilters, nrules))

        ######################## Read infobox ########################

        ibcfg = config['templates']['infobox']
        commonargs = config['templates']['commonargs']

        try:
            infoboks = dp.templates[ibcfg['name']][0]
        except:
            raise ParseError(_('Could not parse the {{tl|%(template)s}} template.') % {'template': infoboxcfg['name']})

        utc = pytz.utc

        if infoboks.has_param(commonargs['year']) and infoboks.has_param(commonargs['week']):
            year = int(re.sub(ur'<\!--.+?-->', ur'', unicode(infoboks.parameters[commonargs['year']])).strip())
            startweek = int(re.sub(ur'<\!--.+?-->', ur'', unicode(infoboks.parameters[commonargs['week']])).strip())
            if infoboks.has_param(commonargs['week2']):
                endweek = re.sub(ur'<\!--.+?-->', ur'', unicode(infoboks.parameters[commonargs['week2']])).strip()
                if endweek == '':
                    endweek = startweek
            else:
                endweek = startweek
            endweek = int(endweek)

            startweek = Week(year, startweek)
            endweek = Week(year, endweek)
            self.start = wiki_tz.localize(datetime.combine(startweek.monday(), dt_time(0, 0, 0)))
            self.end = wiki_tz.localize(datetime.combine(endweek.sunday(), dt_time(23, 59, 59)))
        elif infoboks.has_param(ibcfg['start']) and infoboks.has_param(ibcfg['end']):
            startdt = infoboks.parameters[ibcfg['start']].value
            enddt = infoboks.parameters[ibcfg['end']].value
            self.start = wiki_tz.localize(datetime.strptime(startdt + ' 00 00 00', '%Y-%m-%d %H %M %S'))
            self.end = wiki_tz.localize(datetime.strptime(enddt + ' 23 59 59', '%Y-%m-%d %H %M %S'))
        else:
            args = {'week': commonargs['week'], 'year': commonargs['year'], 'start': ibcfg['start'], 'end': ibcfg['end'], 'template': ibcfg['name']}
            raise ParseError(_('Did not find %(week)s+%(year)s or %(start)s+%(end)s in {{tl|%(templates)s}}.') % args)

        self.year = self.start.isocalendar()[0]
        self.startweek = self.start.isocalendar()[1]
        self.endweek = self.end.isocalendar()[1]

        userprefix = self.homesite.namespaces[2]
        self.ledere = re.findall(r'\[\[(?:User|%s):([^\|\]]+)' % userprefix, unicode(infoboks.parameters[ibcfg['organizer']]), flags=re.I)
        if len(self.ledere) == 0:
            log('Did not find any organizers in {{tl|%(template)s}}.' % {'template': ibcfg['name']})

        awards = config['awards']
        self.prices = []
        for col in awards.keys():
            if infoboks.has_param(col):
                r = re.sub(ur'<\!--.+?-->', ur'', unicode(infoboks.parameters[col])).strip()  # strip comments, then whitespace
                if r != '':
                    r = r.split()[0].lower()
                    #print col,r
                    if r == ibcfg['winner']:
                        self.prices.append([col, 'winner', 0])
                    elif r != '':
                        try:
                            self.prices.append([col, 'pointlimit', int(r)])
                        except ValueError:
                            pass
                            #raise ParseError('Klarte ikke tolke verdien til parameteren %s gitt til {{tl|infoboks ukens konkurranse}}.' % col)

        if not 'winner' in [r[1] for r in self.prices]:
            winnerawards = ', '.join(['{{para|%s|vinner}}' % k for k, v in awards.items() if 'winner' in v])
            #raise ParseError(_('Found no winner award in {{tl|%(template)s}}. Winner award is set by one of the following: %(awards)s.') % {'template': ibcfg['name'], 'awards': winnerawards})
            log('Found no winner award in {{tl|%(template)s}}. Winner award is set by one of the following: %(awards)s.' % {'template': ibcfg['name'], 'awards': winnerawards})

        self.prices.sort(key=lambda x: x[2], reverse=True)

        ######################## Read disqualifications ########################

        sucfg = config['templates']['suspended']
        if sucfg['name'] in dp.templates:
            for templ in dp.templates[sucfg['name']]:
                uname = templ.parameters[1].value
                try:
                    sdate = wiki_tz.localize(datetime.strptime(templ.parameters[2].value, '%Y-%m-%d %H:%M'))
                except ValueError:
                    raise ParseError(_("Couldn't parse the date given to the {{tl|%(template)s}} template.") % sucfg['name'])

                #print 'Suspendert bruker:',uname,sdate
                ufound = False
                for u in self.users:
                    if u.name == uname:
                        #print " > funnet"
                        u.suspended_since = sdate
                        ufound = True
                if not ufound:
                    pass
                    # TODO: logging.warning
                    #raise ParseError('Fant ikke brukeren %s gitt til {{tl|UK bruker suspendert}}-malen.' % uname)

        dicfg = config['templates']['disqualified']
        if dicfg['name'] in dp.templates:
            for templ in dp.templates[dicfg['name']]:
                uname = templ.parameters[1].value
                anon = templ.get_anonymous_parameters()
                uname = anon[1]
                if not templ.has_param('s'):
                    for aname in anon[2:]:
                        #print 'Diskvalifiserte bidrag:',uname,aname
                        ufound = False
                        for u in self.users:
                            if u.name == uname:
                                #print " > funnet"
                                u.disqualified_articles.append(aname)
                                ufound = True
                        if not ufound:
                            raise ParseError(_('Could not find the user %(user)s given to the {{tl|%(template)s}} template.') % {'user': uname, 'template': dicfg['name']})

        pocfg = config['templates']['penalty']
        if pocfg['name'] in dp.templates:
            for templ in dp.templates[pocfg['name']]:
                uname = templ.parameters[1].value
                revid = int(templ.parameters[2].value)

                #if not re.match('^[a-z]{2,3}:', aname):
                #    aname = config['default_prefix'] + ':' + aname

                points = float(templ.parameters[3].value.replace(',', '.'))
                reason = templ.parameters[4].value
                ufound = False
                log('poengtrekk: USER: %s REVISION: %s POINTS: %d REASON: %s' % (uname, revid, points, reason))
                for u in self.users:
                    if u.name == uname:
                        u.point_deductions.append([revid, points, reason])
                        ufound = True
                if not ufound:
                    raise ParseError(_("Couldn't find the user %(user)s given to the {{tl|%(template)s}} template.") % {'user': uname, 'template': dicfg['name']})

        # try:
        #     infoboks = dp.templates['infoboks ukens konkurranse'][0]
        # except:
        #     raise ParseError('Klarte ikke å tolke innholdet i {{tl|infoboks ukens konkurranse}}-malen.')

        return rules, filters

    def plot(self):
        import matplotlib.pyplot as plt

        w = 20 / 2.54
        goldenratio = 1.61803399
        h = w / goldenratio
        fig = plt.figure(figsize=(w, h))

        ax = fig.add_subplot(1, 1, 1, frame_on=False)
        ax.grid(True, which='major', color='gray', alpha=0.5)
        fig.subplots_adjust(left=0.10, bottom=0.09, right=0.65, top=0.94)

        t0 = float(unix_time(self.start))

        datediff = self.end - self.start
        ndays = datediff.days + 1

        xt = t0 + np.arange(ndays + 1) * 86400
        xt_mid = t0 + 43200 + np.arange(ndays) * 86400

        now = float(unix_time(server_tz.localize(datetime.now()).astimezone(pytz.utc)))

        yall = []
        cnt = 0

        alldata = {}

        for u in self.users:
            alldata[u.name] = []
            for point in u.plotdata:
                alldata[u.name].append({'x': point[0], 'y': point[1]})
            if u.plotdata.shape[0] > 0:
                cnt += 1
                x = list(u.plotdata[:, 0])
                y = list(u.plotdata[:, 1])
                yall.extend(y)
                x.insert(0, xt[0])
                y.insert(0, 0)
                if now < xt[-1]:
                    x.append(now)
                    y.append(y[-1])
                else:
                    x.append(xt[-1])
                    y.append(y[-1])
                l = ax.plot(x, y, linewidth=1.2, label=u.name)  # markerfacecolor='#FF8C00', markeredgecolor='#888888', label = u.name)
                c = l[0].get_color()
                #ax.plot(x[1:-1], y[1:-1], marker='.', markersize=4, markerfacecolor=c, markeredgecolor=c, linewidth=0., alpha=0.5)  # markerfacecolor='#FF8C00', markeredgecolor='#888888', label = u.name)
                if cnt >= 15:
                    break

        if 'datafile' in config['plot']:
            datafile = open(config['plot']['datafile'], 'w')
            json.dump(alldata, datafile)

        if now < xt[-1]:   # showing vertical line telling day when plot was updated
            ax.axvline(now, color='black', alpha=0.5)

        ax.set_xticks(xt, minor=False)
        ax.set_xticklabels([], minor=False)

        ax.set_xticks(xt_mid, minor=True)
        abday = map(lambda x: calendar.day_abbr[x].decode('utf-8'), [0, 1, 2, 3, 4, 5, 6])
        if ndays == 7:
            ax.set_xticklabels(abday, minor=True)
        elif ndays == 14:
            ax.set_xticklabels([abday[0], '', abday[2], '', abday[4], '', abday[6], '', abday[1], '', abday[3], '', abday[5], ''], minor=True)
        elif ndays == 30:   # for longer contest show numeral ticks
            ax.set_xticklabels(['1', '', '', '', '5', '', '', '', '', '10', '', '', '', '', '15', '', '', '', '', '20', '', '', '', '', '25', '', '', '', '', '30'], minor=True)
        elif ndays == 31:
            ax.set_xticklabels(['1', '', '', '', '5', '', '', '', '', '10', '', '', '', '', '15', '', '', '', '', '20', '', '', '', '', '25', '', '', '', '', '', '31'], minor=True)

        for i in range(1, ndays, 2):
            ax.axvspan(xt[i], xt[i + 1], facecolor='#000099', linewidth=0., alpha=0.03)

        for i in range(0, ndays, 2):
            ax.axvspan(xt[i], xt[i + 1], facecolor='#000099', linewidth=0., alpha=0.07)

        for line in ax.xaxis.get_ticklines(minor=False):
            line.set_markersize(0)

        for line in ax.xaxis.get_ticklines(minor=True):
            line.set_markersize(0)

        for line in ax.yaxis.get_ticklines(minor=False):
            line.set_markersize(0)

        if len(yall) > 0:
            ax.set_xlim(t0, xt[-1])
            ax.set_ylim(0, 1.05 * np.max(yall))

            ax.set_xlabel(_('Day'))
            ax.set_ylabel(_('Points'))

            now = server_tz.localize(datetime.now())
            now2 = now.astimezone(wiki_tz).strftime(_('%e. %B %Y, %H:%M')).decode('utf-8')
            ax_title = _('Updated %(date)s')

            #print ax_title.encode('utf-8')
            #print now2.encode('utf-8')
            ax_title = ax_title % {'date': now2}
            ax.set_title(ax_title)

            plt.legend()
            ax = plt.gca()
            ax.legend(
                # ncol = 4, loc = 3, bbox_to_anchor = (0., 1.02, 1., .102), mode = "expand", borderaxespad = 0.
                loc=2, bbox_to_anchor=(1.0, 1.0), borderaxespad=0., frameon=0.
            )
            figname = '../plots/' + self.config['plot']['figname'] % {'year': self.year, 'week': self.startweek}
            plt.savefig(figname.encode('utf-8'), dpi=200)

    def format_msg(self, template, award):
        tpl = self.config['award_message']
        args = {
            'template': tpl[template],
            'yearname': self.config['templates']['commonargs']['year'],
            'weekname': self.config['templates']['commonargs']['week'],
            'week2name': self.config['templates']['commonargs']['week2'],
            'extraargs': (tpl['extraargs'] if 'extraargs' in tpl else ''),
            'year': self.year,
            'week': self.startweek,
            'award': award,
            'yes': self.config['templates']['commonargs'][True],
            'no': self.config['templates']['commonargs'][False]
        }
        if self.startweek == self.endweek:
            return '{{%(template)s|%(yearname)s=%(year)d|%(weekname)s=%(week)02d|%(award)s=%(yes)s%(extraargs)s' % args
        else:
            args['week2'] = self.endweek
            return '{{%(template)s|%(yearname)s=%(year)d|%(weekname)s=%(week)02d|%(week2name)s=%(week2)02d|%(award)s=%(yes)s%(extraargs)s' % args

    def msg_heading(self):
        if self.startweek == self.endweek:
            return '== ' + _('Weekly contest for week %(week)d') % {'week': self.startweek} + ' =='
        else:
            return '== ' + _('Weekly contest for week %(startweek)d–%(endweek)d') % {'startweek': self.startweek, 'endweek': self.endweek} + ' =='

    def deliver_prices(self):

        config = self.config
        heading = self.msg_heading()

        for i, u in enumerate(self.users):

            prizefound = False
            if i == 0:
                mld = ''
                for r in self.prices:
                    if r[1] == 'winner':
                        prizefound = True
                        mld = self.format_msg('winner_template', r[0])
                        break
                for r in self.prices:
                    if r[1] == 'pointlimit' and u.points >= r[2]:
                        mld += '|%s=%s' % (r[0], self.config['templates']['commonargs'][True])
                        break
                mld += '}}\n'
            else:
                mld = ''
                for r in self.prices:
                    if r[1] == 'pointlimit' and u.points >= r[2]:
                        prizefound = True
                        mld = self.format_msg('participant_template', r[0])
                        break
                mld += '}}\n'

            now = server_tz.localize(datetime.now())
            yearweek = now.astimezone(wiki_tz).strftime('%Y-%V')
            userprefix = self.homesite.namespaces[2]
            usertalkprefix = self.homesite.namespaces[3]

            mld += _("Note that the contest this week is [[%(url)s|{{%(template)s|%(weekarg)s=%(week)s}}]]. Join in!") % {
                'url': self.config['pages']['base'] + ' ' + yearweek,
                'template': self.config['templates']['contestlist']['name'],
                'weekarg': self.config['templates']['commonargs']['week'],
                'week': yearweek
            } + ' '
            mld += _('Regards') + ' ' + ', '.join(['[[%s:%s|%s]]' % (userprefix, s, s) for s in self.ledere]) + ' ' + _('and') + ' ~~~~'

            if prizefound:
                page = self.homesite.pages['%s:%s' % (usertalkprefix, u.name)]
                log(' -> Delivering message to %s' % page.name)
                page.save(text=mld, bot=False, section='new', summary=heading)

    def deliver_leader_notification(self, pagename):
        heading = self.msg_heading()
        args = {'prefix': self.homesite.site['server'] + self.homesite.site['script'], 'page': config['awardstatus']['pagename'], 'title': urllib.quote(config['awardstatus']['send'])}
        link = '%(prefix)s?title=%(page)s&action=edit&section=new&preload=%(page)s/Preload&preloadtitle=%(title)s' % args
        usertalkprefix = self.homesite.namespaces[3]
        oaward = ''
        for key, award in self.config['awards'].items():
            if 'organizer' in award:
                oaward = key
        if oaward == '':
            raise StandardError('No organizer award found in config')
        for u in self.ledere:
            if self.startweek == self.endweek:
                mld = '{{%(template)s|%(yeararg)s=%(year)d|%(weekarg)s=%(week)02d|%(organizeraward)s=%(yes)s%(extraargs)s}}\n' % {
                    'template': self.config['award_message']['organizer_template'],
                    'yeararg': self.config['templates']['commonargs']['year'],
                    'weekarg': self.config['templates']['commonargs']['week'],
                    'year': self.year,
                    'week': self.startweek,
                    'extraargs': (self.config['award_message']['extraargs'] if 'extraargs' in self.config['award_message'] else ''),
                    'organizeraward': oaward,
                    'yes': self.config['templates']['commonargs'][True]
                }
            else:
                mld = '{{%(template)s|%(yeararg)s=%(year)d|%(weekarg)s=%(week)02d|%(week2arg)s=%(week2)02d|%(organizeraward)s=%(yes)s%(extraargs)s}}\n' % {
                    'template': self.config['award_message']['organizer_template'],
                    'yeararg': self.config['templates']['commonargs']['year'],
                    'weekarg': self.config['templates']['commonargs']['week'],
                    'week2arg': self.config['templates']['commonargs']['week2'],
                    'year': self.year,
                    'week': self.startweek,
                    'week2': self.endweek,
                    'extraargs': (self.config['award_message']['extraargs'] if 'extraargs' in self.config['award_message'] else ''),
                    'organizeraward': oaward,
                    'yes': self.config['templates']['commonargs'][True]
                }
            mld += _('Now you must check if the results look ok. If there are error messages at the bottom of the [[%(page)s|contest page]], you should check that the related contributions have been awarded the correct number of points. Also check if there are comments or complaints on the discussion page. If everything looks fine, [%(link)s click here] (and save) to indicate that I can send out the awards at first occasion.') % {'page': pagename, 'link': link}
            mld += ' ' + _('Thanks, ~~~~')

            page = self.homesite.pages['%s:%s' % (usertalkprefix, u)]
            log(' -> Leverer arrangørmelding til %s' % page.name)
            page.save(text=mld, bot=False, section='new', summary=heading)

    def deliver_receipt_to_leaders(self):
        heading = self.msg_heading()
        usertalkprefix = self.homesite.namespaces[3]

        args = {'prefix': self.homesite.site['server'] + self.homesite.site['script'], 'page': 'Special:Contributions'}
        link = '%(prefix)s?title=%(page)s&contribs=user&target=UKBot&namespace=3' % args
        mld = '\n:' + _('Awards have been [%(link)s sent out].') % {'link': link} + ' ~~~~'
        for u in self.ledere:
            page = self.homesite.pages['%s:%s' % (usertalkprefix, u)]
            log(' -> Leverer kvittering til %s' % page.name)

            # Find section number
            txt = page.edit()
            sections = [s.strip() for s in re.findall('^[\s]*==([^=]+)==', txt, flags=re.M)]
            try:
                csection = sections.index(heading) + 1
            except ValueError:
                log('[ERROR] Fant ikke "%s" i "%s' % (heading, page.name))
                return

            # Append text to section
            txt = page.edit(section=csection)
            page.save(appendtext=mld, bot=False, summary=heading)

    def delete_contribs_from_db(self):
        cur = self.sql.cursor()
        cur2 = self.sql.cursor()
        ts_start = self.start.astimezone(pytz.utc).strftime('%F %T')
        ts_end = self.end.astimezone(pytz.utc).strftime('%F %T')
        ndel = 0
        for row in cur.execute(u"SELECT site,revid,parentid FROM contribs WHERE timestamp >= ? AND timestamp <= ?", (ts_start, ts_end)):
            row2 = cur2.execute(u"DELETE FROM fulltexts WHERE site=? AND revid=?", [row[0], row[1]])
            ndel += row2.rowcount
            row2 = cur2.execute(u"DELETE FROM fulltexts WHERE site=? AND revid=?", [row[0], row[2]])
            ndel += row2.rowcount

        nremain = cur.execute('SELECT COUNT(*) FROM fulltexts').fetchone()[0]
        log('> Cleaned %d rows from fulltexts-table. %d rows remain' % (ndel, nremain))

        row = cur.execute(u"""DELETE FROM contribs WHERE timestamp >= ? AND timestamp <= ?""", (ts_start, ts_end))
        ndel = row.rowcount
        nremain = cur.execute('SELECT COUNT(*) FROM contribs').fetchone()[0]
        log('> Cleaned %d rows from contribs-table. %d rows remain' % (ndel, nremain))

        cur.close()
        cur2.close()
        self.sql.commit()

    def deliver_warnings(self, simulate=False):
        """
        Inform users about problems with their contribution(s)
        """
        usertalkprefix = self.homesite.namespaces[3]
        cur = self.sql.cursor()
        for u in self.users:
            msgs = []
            if u.suspended_since is not None:
                d = [self.name, u.name, 'suspension', '']
                if len(cur.execute(u'SELECT id FROM notifications WHERE contest=? AND user=? AND class=? AND args=?', d).fetchall()) == 0:
                    msgs.append('Du er inntil videre suspendert fra konkurransen med virkning fra %s. Dette innebærer at dine bidrag gjort etter dette tidspunkt ikke teller i konkurransen, men alle bidrag blir registrert og skulle suspenderingen oppheves i løpet av konkurranseperioden vil også bidrag gjort i suspenderingsperioden telle med. Vi oppfordrer deg derfor til å arbeide med problemene som førte til suspenderingen slik at den kan oppheves.' % u.suspended_since.strftime(_('%e. %B %Y, %H:%M')).decode('utf-8'))
                    if not simulate:
                        cur.execute(u'INSERT INTO notifications (contest, user, class, args) VALUES (?,?,?,?)', d)
            discs = []
            for article_key, article in u.articles.iteritems():
                if article.disqualified:
                    d = [self.name, u.name, 'disqualified', article_key]
                    if len(cur.execute(u'SELECT id FROM notifications WHERE contest=? AND user=? AND class=? AND args=?', d).fetchall()) == 0:
                        discs.append('[[:%s|%s]]' % (article_key, article.name))
                        if not simulate:
                            cur.execute(u'INSERT INTO notifications (contest, user, class, args) VALUES (?,?,?,?)', d)
            if len(discs) > 0:
                if len(discs) == 1:
                    s = discs[0]
                else:
                    s = ', '.join(discs[:-1]) + ' og ' + discs[-1]
                msgs.append('Bidragene dine til %s er diskvalifisert fra konkurransen. En diskvalifisering kan oppheves hvis du selv ordner opp i problemet som førte til diskvalifiseringen. Hvis andre brukere ordner opp i problemet er det ikke sikkert at den vil kunne oppheves.' % s)

            if len(msgs) > 0:
                if self.startweek == self.endweek:
                    heading = '== Viktig informasjon angående Ukens konkurranse uke %d ==' % self.startweek
                else:
                    heading = '== Viktig informasjon angående Ukens konkurranse uke %d–%d ==' % (self.startweek, self.endweek)
                #msg = 'Arrangøren av denne [[%(pagename)s|ukens konkurranse]] har registrert problemer ved noen av dine bidrag:
                #så langt. Det er dessverre registrert problemer med enkelte av dine bidrag som medfører at vi er nødt til å informere deg om følgende:\n' % { 'pagename': self.name }

                msg = ''.join(['* %s\n' % m for m in msgs])
                msg += 'Denne meldingen er generert fra anmerkninger gjort av konkurransearrangør på [[%(pagename)s|konkurransesiden]]. Du finner mer informasjon på konkurransesiden og/eller tilhørende diskusjonsside. Så lenge konkurransen ikke er avsluttet, kan problemer løses i løpet av konkurransen. Om du ønsker det, kan du fjerne denne meldingen når du har lest den. ~~~~' % {'pagename': self.name}

                #print '------------------------------',u.name
                #print msg
                #print '------------------------------'

                page = self.homesite.pages['%s:%s' % (usertalkprefix, u.name)]
                log(' -> Leverer advarsel til %s' % page.name)
                if simulate:
                    log(msg)
                else:
                    page.save(text=msg, bot=False, section='new', summary=heading)
            self.sql.commit()

############################################################################################################################
# Main
############################################################################################################################


    # try:
    #     log( "Opening message file %s for locale %s" % (filename, loc[0]) )
    #     trans = gettext.GNUTranslations(open( filename, "rb" ) )
    # except IOError:
    #     log( "Locale not found. Using default messages" )
    #     trans = gettext.NullTranslations()
    # trans.install(unicode = True)

if __name__ == '__main__':

    host = config['homesite']
    homesite = Site(host, config['account']['user'], config['account']['pass'])
    prefix = host.split('.')[0]
    sites = {prefix: homesite}
    if 'othersites' in config:
        for host in config['othersites']:
            prefix = host.split('.')[0]
            sites[prefix] = Site(host, config['account']['user'], config['account']['pass'])

    cpage = config['pages']['catignore']
    sql = sqlite3.connect(config['db'])

    now = server_tz.localize(datetime.now())

    # Determine kpage

    if args.close:
        # Check if there are contests to be closed
        cur = sql.cursor()
        rows = cur.execute(u'SELECT name FROM contests WHERE ended=1 AND closed=0 LIMIT 1').fetchall()
        if len(rows) == 0:
            log(" -> Found no contests to close!")
            sys.exit(0)
        cur.close()
        ktitle = rows[0][0]
        log(" -> Contest %s is to be closed" % rows[0])
        lastrev = homesite.pages[config['awardstatus']['pagename']].revisions(prop='user|comment').next()
        closeuser = lastrev['user']
        revc = lastrev['comment']
        if revc.find('/* ' + config['awardstatus']['send'] + ' */') == -1:
            log('>> Award delivery has not been confirmed yet')
            sys.exit(0)
    elif args.page is not None:
        ktitle = args.page.decode('utf-8')
    else:
        log('  No page specified. Using default page')
        ktitle = config['pages']['default']
        w = Week.withdate((now - timedelta(hours=1)).astimezone(wiki_tz).date())
        # subtract one hour, so we close last week's contest right after midnight
        ktitle = ktitle % { 'year': w.year, 'week': w.week }
        #strftime(ktitle.encode('utf-8')).decode('utf-8')

    # Is ktitle redirect? Resolve

    log('@ ktitle is %s' % ktitle)
    pp = homesite.api('query', prop='pageprops', titles=ktitle, redirects='1')
    if 'redirects' in pp['query']:
        ktitle = pp['query']['redirects'][0]['to']
        log('  -> Redirected to:  %s' % ktitle)

    # Check that we're not given some very wrong page
    userprefix = homesite.namespaces[2]
    #if not (re.match('^'+config['pages']['base'], ktitle) or re.match('^' + userprefix + ':UKBot/', ktitle)):
    #    raise StandardError('I refuse to work with that page!')

    # Check if page exists

    kpage = homesite.pages[ktitle]
    if not kpage.exists:
        log('  !! kpage does not exist! Exiting')
        sys.exit(0)

    # Initialize the contest

    try:
        uk = UK(kpage, homesite.pages[cpage].edit(), sites=sites, homesite=homesite, sql=sql, verbose=args.verbose, config=config)
    except ParseError as e:
        err = "\n* '''%s'''" % e.msg
        out = '\n{{%s | error | %s }}' % (config['templates']['botinfo'], err)
        if args.simulate:
            print out.encode('utf-8')
        else:
            kpage.save('dummy', summary=_('UKBot encountered a problem'), appendtext=out)
        raise

    if args.close and closeuser not in uk.ledere:
        log('!! Konkurransen ble forsøkt avsluttet av %s, men konkurranseledere er oppgitt som: %s' % (closeuser, ', '.join(uk.ledere)))
        #log('!! Konkurransen ble forsøkt avsluttet av andre enn konkurranseleder')
        #sys.exit(0)

    # Check if contest is to be ended

    log('@ Contest open from %s to %s' % (uk.start.strftime('%F %T'), uk.end.strftime('%F %T')))
    ending = False
    if args.close is False and now > uk.end:
        ending = True
        log("  -> Ending contest")
        cur = sql.cursor()
        if len(cur.execute(u'SELECT ended FROM contests WHERE name=? AND ended=1', [ktitle]).fetchall()) == 1:
            log("  -> Already ended. Abort")
            #print "Konkurransen kunne ikke avsluttes da den allerede er avsluttet"
            sys.exit(0)

        cur.close()

    # Loop over users

    narticles = 0
    nbytes = 0
    nwords = 0
    nnewpages = 0

    # extraargs = {'namespace': 0}
    extraargs = {}
    for f in uk.filters:
        if type(f) == NamespaceFilter:
            extraargs['namespace'] = f.namespace

    for u in uk.users:
        log("=== %s ===" % u.name)

        # First read contributions from db
        u.add_contribs_from_db(sql, uk.start, uk.end, sites)

        # Then fill in new contributions from wiki
        for site in sites.itervalues():
            u.add_contribs_from_wiki(site, uk.start, uk.end, fulltext=True, **extraargs)

        # And update db
        u.save_contribs_to_db(sql)

        try:

            # Filter out relevant articles
            u.filter(uk.filters)

            # And calculate points
            log(' -> Analyzing ', newline=False)
            u.analyze(uk.rules)
            log('OK (%.f points)' % u.points)

            narticles += len(u.articles)
            nbytes += u.bytes
            nwords += u.words
            nnewpages += u.newpages

        except ParseError as e:
            err = "\n* '''%s'''" % e.msg
            out = '\n{{%s | error | %s }}' % (config['templates']['botinfo'], err)
            if args.simulate:
                print out
            else:
                kpage.save('dummy', summary=_('UKBot encountered a problem'), appendtext=out)
            raise

    # Sort users by points

    uk.users.sort(key=lambda x: x.points, reverse=True)

    # Make outpage

    out = ''
    #out += '[[File:Nowp Ukens konkurranse %s.svg|thumb|400px|Resultater (oppdateres normalt hver natt i halv ett-tiden, viser kun de ti med høyest poengsum)]]\n' % uk.start.strftime('%Y-%W')

    sammen = ''
    if 'status' in config['templates']:
        sammen = '{{%s' % config['templates']['status']

        ft = [type(f) for f in uk.filters]
        rt = [type(r) for r in uk.rules]

        #if StubFilter in ft:
        #    sammen += '|avstubbet=%d' % narticles

        trn = 0
        for f in uk.rules:
            if type(f) == NewPageRule:
                sammen += '|%s=%d' % (f.key, nnewpages)
            elif type(f) == ByteRule:
                if nbytes >= 10000:
                    sammen += '|kilo%s=%.f' % (f.key, nbytes / 1000.)
                else:
                    sammen += '|%s=%d' % (f.key, nbytes)
            elif type(f) == WordRule:
                sammen += '|%s=%d' % (f.key, nwords)
            elif type(f) == RefRule:
                sammen += '|%s=%d' % (f.key, f.totalsources)
            elif type(f) == RefSectionFiRule:
                sammen += '|%s=%d' % (f.key, f.totalrefsectionsadded)
            elif type(f) == ImageRule:
                sammen += '|%s=%d' % (f.key, f.totalimages)
            elif type(f) == TemplateRemovalRule:
                trn += 1
                sammen += '|%(key)s%(idx)d=%(tpl)s|%(key)s%(idx)dn=%(cnt)d' % {
                    'key': f.key, 'idx': trn, 'tpl': f.template, 'cnt': f.total}

        sammen += '}}'

    #out += sammen + '\n'

    now = server_tz.localize(datetime.now())
    if ending:
        # Konkurransen er nå avsluttet – takk til alle som deltok! Rosetter vil bli delt ut så snart konkurransearrangøren(e) har sjekket resultatene.
        out += "''" + _('This contest is closed – thanks to everyone who participated! Awards will be sent out as soon as the contest organizer has checked the results.') + "''\n\n"
    elif args.close:
        out += "''" + _('This contest is closed – thanks to everyone who participated!') + "''\n\n"
    else:
        oargs = {
            'lastupdate': now.astimezone(wiki_tz).strftime(_('%e. %B %Y, %H:%M')).decode('utf-8'),
            'startdate': uk.start.strftime(_('%e. %B %Y, %H:%M')).decode('utf-8'),
            'enddate': uk.end.strftime(_('%e. %B %Y, %H:%M')).decode('utf-8')
        }
        out += "''" + _('Last updated %(lastupdate)s. The contest is open from %(startdate)s to %(enddate)s.') % oargs + "''\n\n"

    for i, u in enumerate(uk.users):
        out += u.format_result(pos=i, closing=args.close, prices=uk.prices)

    article_errors = {}
    for u in uk.users:
        for article in u.articles.itervalues():
            k = article.site.key + ':' + article.name
            if len(article.errors) > 0:
                article_errors[k] = article.errors
            for rev in article.revisions.itervalues():
                if len(rev.errors) > 0:
                    if k in article_errors:
                        article_errors[k].extend(rev.errors)
                    else:
                        article_errors[k] = rev.errors

    errors = []
    for art, err in article_errors.iteritems():
        if len(err) > 8:
            err = err[:8]
            err.append('(...)')
        errors.append('\n* ' + _('UKBot encountered the following problems with the article [[:%s]]') % art + ''.join(['\n** %s' % e for e in err]))

    for site in uk.sites.itervalues():
        for error in site.errors:
            errors.append('\n* %s' % error)

    if len(errors) == 0:
        out += '{{%s | ok | %s }}' % (config['templates']['botinfo'], now.astimezone(wiki_tz).strftime('%F %T'))
    else:
        out += '{{%s | 1=note | 2=%s | 3=%s }}' % (config['templates']['botinfo'], now.astimezone(wiki_tz).strftime('%F %T'), ''.join(errors))

    out += '\n' + config['contestPages']['footer'] % {'year': uk.year} + '\n'

    ib = config['templates']['infobox']

    if not args.simulate:
        txt = kpage.edit()
        tp = TemplateEditor(txt)
        #print "---"
        #print sammen
        #print "---"
        if sammen != '':
            tp.templates[ib['name']][0].parameters[ib['status']] = sammen
        txt = tp.wikitext()
        secstart = -1
        secend = -1
        for s in re.finditer(r'^[\s]*==([^=]+)==[\s]*\n', txt, flags=re.M):
            if s.group(1).strip() == config['contestPages']['resultsSection']:
                secstart = s.end()
            elif secstart != -1:
                secend = s.start()
                break
        if secstart == -1:
            raise StandardError("Error: secstart=%d,secend=%d" % (secstart, secend))
        else:
            if secend == -1:
                txt = txt[:secstart] + out
            else:
                txt = txt[:secstart] + out + txt[secend:]

            log(" -> Updating wiki, section = %d " % (uk.results_section))
            if ending:
                kpage.save(txt, summary=_('Updating with final results, the contest is now closed.'))
            elif args.close:
                kpage.save(txt, summary=_('Checking results and handing out awards'))
            else:
                kpage.save(txt, summary=_('Updating'))

    if args.output != '':
        print "Writing output to file"
        f = codecs.open(args.output, 'w', 'utf-8')
        f.write(out)
        f.close()

    if ending:
        log(" -> Ending contest")
        if not args.simulate:
            uk.deliver_leader_notification(ktitle)

            aws = config['awardstatus']
            page = homesite.pages[aws['pagename']]
            page.save(text=aws['wait'], summary=aws['wait'], bot=True)

            cur = sql.cursor()
            cur.execute(u'INSERT INTO contests (name, ended, closed) VALUES (?,1,0)', [ktitle])
            sql.commit()
            cur.close()

    if args.close:
        log(" -> Delivering prices")
        uk.deliver_prices()

        cur = sql.cursor()
        for u in uk.users:
            arg = [ktitle, u.name, int(uk.startweek), u.points, int(u.bytes), int(u.newpages), '']
            if uk.startweek != uk.endweek:
                arg[-1] = int(uk.endweek)
            #print arg
            cur.execute(u"INSERT INTO users (contest, user, week, points, bytes, newpages, week2) VALUES (?,?,?,?,?,?,?)", arg)

        cur.execute(u'UPDATE contests SET closed=1 WHERE name=?', [ktitle])
        sql.commit()
        cur.close()

        aws = config['awardstatus']
        page = homesite.pages[aws['pagename']]
        page.save(text=aws['sent'], summary=aws['sent'], bot=True)

        uk.deliver_receipt_to_leaders()

        log(' -> Cleaning DB')
        uk.delete_contribs_from_db()

    # Notify users about issues

    # uk.deliver_warnings(simulate=args.simulate)

    # Update WP:UK

    if 'redirect' in config['pages']:
        if re.match('^' + config['pages']['base'], ktitle) and not args.simulate and not args.close and not ending:
            page = homesite.pages[config['pages']['redirect']]
            txt = _('#REDIRECT [[%s]]') % ktitle
            if page.edit() != txt:
                page.save(txt, summary=_('Redirecting to %s') % ktitle)

    # Update Wikipedia:Portal/Oppslagstavle

    if 'noticeboard' in config:
        boardname = config['noticeboard']['name']
        boardtpl = config['noticeboard']['template']
        commonargs = config['templates']['commonargs']
        tplname = boardtpl['name']
        oppslagstavle = homesite.pages[boardname]
        txt = oppslagstavle.edit()

        dp = TemplateEditor(txt)
        ntempl = len(dp.templates[tplname])
        if ntempl != 1:
            raise StandardError(u'Feil: Fant %d %s-maler i %s' % (ntempl, tplname, boardname))

        tpl = dp.templates[tplname][0]
        now2 = now.astimezone(wiki_tz)
        if int(tpl.parameters['uke']) != int(now2.strftime('%V')):
            log('-> Updating %s' % boardname)
            tpllist = config['templates']['contestlist']
            commonargs = config['templates']['commonargs']
            tema = homesite.api('parse', text='{{subst:%s|%s=%s}}' % (tpllist['name'], commonargs['week'], now2.strftime('%Y-%V')), pst=1, onlypst=1)['parse']['text']['*']
            tpl.parameters[1] = tema
            tpl.parameters[boardtpl['date']] = now2.strftime('%e. %h')
            tpl.parameters[commonargs['year']] = now2.strftime('%Y')
            tpl.parameters[commonargs['week']] = now2.strftime('%V')
            txt2 = dp.wikitext()
            if txt != txt2:
                oppslagstavle.save(txt2, summary=_('The weekly contest is: %(link)s') % {'link': tema})

    # Make a nice plot

    uk.plot()

    runend = server_tz.localize(datetime.now())
    runtime = (runend - runstart).total_seconds()
    log('UKBot finishing at %s. Runtime was %.f seconds.' % (runend.strftime('%F %T'), runtime))
