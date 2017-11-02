# encoding=utf-8
# vim: fenc=utf-8 et sw=4 ts=4 sts=4 ai
from __future__ import unicode_literals

import time
runstart_s = time.time()

import logging
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)     # DEBUG if verbose
syslog = logging.StreamHandler()
# formatter = logging.Formatter('%(asctime)s [%(mem_usage)s MB] %(name)s %(levelname)s : %(message)s')
logger.addHandler(syslog)
syslog.setLevel(logging.INFO)
logger.info('Loading')

import matplotlib
matplotlib.use('svg')

from future.utils import python_2_unicode_compatible
import numpy as np
import time
import calendar
from datetime import datetime, timedelta
from datetime import time as dt_time
import gettext
import pytz
from isoweek import Week  # Sort-of necessary until datetime supports %V, see http://bugs.python.org/issue12006
                          # and See http://stackoverflow.com/questions/5882405/get-date-from-iso-week-number-in-python
import sys
import unicodedata
import re
import json
import os
import mysql.connector
import yaml
from odict import odict
import urllib
import argparse
import codecs


logging.getLogger('requests').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('requests_oauthlib').setLevel(logging.WARNING)
logging.getLogger('oauthlib').setLevel(logging.WARNING)
logging.getLogger('mwtemplates').setLevel(logging.INFO)

import mwclient
from mwtemplates import TemplateEditor
from mwtextextractor import get_body_text
import ukcommon


from ukcommon import log, init_localization, get_mem_usage

import locale

class AppFilter(logging.Filter):

    @staticmethod
    def format_as_mins_and_secs(msecs):
        secs = msecs / 1000.
        mins = secs / 60.
        secs = secs % 60.
        return '%3.f:%02.f' % (mins, secs)

    def filter(self, record):
        record.mem_usage = '%.0f' % (get_mem_usage(),)
        record.relativeSecs = AppFilter.format_as_mins_and_secs(record.relativeCreated)
        return True

formatter = logging.Formatter('[%(relativeSecs)s] [%(mem_usage)s MB] %(levelname)s : %(message)s')
syslog.setFormatter(formatter)
syslog.addFilter(AppFilter())
logger.info('Logger ready')

import rollbar
import platform

#locale.setlocale(locale.LC_TIME, 'no_NO'.encode('utf-8'))

# Read args

# This actually takes about 10 seconds and eats some memory
all_chars = (unichr(i) for i in xrange(sys.maxunicode))
control_chars = ''.join(c for c in all_chars if unicodedata.category(c) in set(['Cc','Cf','Cn','Co','Cs']))
control_char_re = re.compile('[%s]' % re.escape(control_chars))
logger.info('Gigantic regexp is ready')

def remove_control_chars(s):
    if type(s) == str or type(s) == unicode:
        return control_char_re.sub('', s)
    else:
        return s


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

    def __init__(self, host, **kwargs):

        self.errors = []
        self.name = host
        self.key = host.split('.')[0]
        logger.debug('Initializing site: %s', host)
        ua = 'UKBot. Run by User:Danmichaelo. Using mwclient/' + mwclient.__ver__
        mwclient.Site.__init__(self, host, clients_useragent=ua, **kwargs)


@python_2_unicode_compatible
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

    def __str__(self):
        return "<Article %s:%s for user %s>" % (self.site.key, self.name, self.user.name)

    def __repr__(self):
        return __str__(self)

    @property
    def new(self):
        firstrev = self.revisions[self.revisions.firstkey()]
        return firstrev.new

    @property
    def new_non_redirect(self):
        firstrev = self.revisions[self.revisions.firstkey()]
        return firstrev.new and not firstrev.redirect

    def add_revision(self, revid, **kwargs):
        rev = Revision(self, revid, **kwargs)
        self.revisions[revid] = rev
        self.user.revisions[revid] = rev
        return rev

    @property
    def bytes(self):
        return np.sum([rev.bytes for rev in self.revisions.itervalues()])

    @property
    def words(self):
        """
        Returns the total number of words added to this Article. The number
        will never be negative, but words removed in one revision will
        contribute negatively to the sum.
        """
        return np.max([0, np.sum([rev.words for rev in self.revisions.itervalues()])])

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
                    logger.debug('!! Skipping revision %d in suspension period', revid)

        return p
        #return np.sum([a.points for a in self.articles.values()])


@python_2_unicode_compatible
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
        self.parsedcomment = None
        self.saved = False  # Saved in local DB
        self.dirty = False  #

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
            elif k == 'parsedcomment':
                self.parsedcomment = v
            elif k == 'text':
                if v is not None:
                    self.text = v
            elif k == 'parenttext':
                if v is not None:
                    self.parenttext = v
            else:
                raise StandardError('add_revision got unknown argument %s' % k)

        for pd in self.article.user.point_deductions:
            if pd[0] == self.revid:
                self.add_point_deduction(pd[1], pd[2])


    def __str__(self):
        return ("<Revision %d for %s:%s>" % (self.revid, self.article.site.key, self.article.name))

    def __repr__(self):
        return __str__(self)

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
            logger.debug('Body size: %d -> %d, wordcount: %d -> %d (%s)', len(self.parenttext), len(self.text), len(mt2.split()), len(mt1.split()), self.article.name)
            self._wordcount = len(mt1.split()) - len(mt2.split())
            if not self.new and len(mt2.split()) == 0 and self._wordcount > 1:
                w = _('Revision [//%(host)s/w/index.php?diff=prev&oldid=%(revid)s %(revid)s]: The word count difference might be wrong, because no words were found in the parent revision (%(parentid)s) of size %(size)d, possibly due to unclosed tags or templates in that revision.') % { 'host': self.article.site.host, 'revid': self.revid, 'parentid': self.parentid, 'size': len(self.parenttext) }
                logger.warning(w)
                #log(self.parenttext)
                self.errors.append(w)
            elif self._wordcount > 10 and self._wordcount > self.bytes:
                w = _('Revision [//%(host)s/w/index.php?diff=prev&oldid=%(revid)s %(revid)s]: The word count difference might be wrong, because the word count increase (%(words)d) is larger than the byte increase (%(bytes)d). Wrong word counts may occur for invalid wiki text.') % { 'host': self.article.site.host, 'revid': self.revid, 'words': self._wordcount, 'bytes': self.bytes }
                logger.warning(w)
                #log(self.parenttext)
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
        logger.info('Revision %s: Removing %d points for reason: %s', self.revid, points, reason)
        self.point_deductions.append([points, reason])


class User(object):

    def __init__(self, username, contest):
        self.name = username
        self.articles = odict()
        self.revisions = odict()
        self.contest = contest
        self.suspended_since = None
        self.disqualified_articles = []
        self.point_deductions = []

    def __repr__(self):
        return ("<User %s>" % self.name).encode('utf-8')

    def sort_contribs(self):

        # sort revisions by revision id
        for article in self.articles.itervalues():
            article.revisions.sort(key=lambda x: x[0])   # sort by key (revision id)

        # sort articles by first revision id
        self.articles.sort(key=lambda x: x[1].revisions.firstkey())

    def add_article_if_necessary(self, site, article_title):
        article_key = site.key + ':' + article_title

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

        # logger.info('Reading contributions from %s', site.host)

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
            logger.debug('Limiting to namespaces: %s', args['namespace'])

        #new_articles = []
        new_revisions = []
        t0 = time.time()
        t1 = time.time()
        tnr = 0
        n_articles = len(self.articles)
        for c in site.usercontributions(self.name, ts_start, ts_end, 'newer', prop='ids|title|timestamp|comment', **args):
            tnr += 1

            dt1 = time.time() - t1
            if dt1 > 10:
                dt0 = time.time() - t0
                t1 = time.time()
                logger.info('Found %d new revisions, %d new articles from API so far (%.0f secs elapsed)',
                            len(new_revisions), new_articles, dt0)


            #pageid = c['pageid']
            if 'comment' in c:
                article_comment = c['comment']

                ignore = False
                for pattern in self.contest.config.get('ignore', []):
                    if re.search(pattern, article_comment):
                        ignore = True
                        logger.debug('Ignoring revision %d of %s because it matched %s', c['revid'], c['title'], pattern)
                        break

                if not ignore:
                    rev_id = c['revid']
                    article_title = c['title']
                    article_key = site_key + ':' + article_title

                    if rev_id in self.revisions:
                        # We check self.revisions instead of article.revisions, because the revision may
                        # already belong to "another article" (another title) if the article has been moved

                        if self.revisions[rev_id].article.name != article_title:
                            rev = self.revisions[rev_id]
                            logger.info('Moving revision %d from "%s" to "%s"', rev_id, rev.article.name, article_title)
                            article = self.add_article_if_necessary(site, article_title)
                            rev.article.revisions.pop(rev_id)  # remove from old article
                            article.revisions[rev_id] = rev    # add to new article
                            rev.article = article              # and update reference

                    else:

                        article = self.add_article_if_necessary(site, article_title)
                        rev = article.add_revision(rev_id, timestamp=time.mktime(c['timestamp']), username=self.name)
                        rev.saved = False  # New revision that should be stored in DB
                        new_revisions.append(rev)

        # If revisions were moved from one article to another, and the redirect was not created by the same user,
        # some articles may now have zero revisions. We should drop them
        for article_key, article in self.articles.iteritems():
            if len(article.revisions) == 0:
                logger.info('Dropping article "%s" due to zero remaining revisions', article.name)
                del self.articles[article_key]

        # Always sort after we've added contribs
        new_articles = len(self.articles) - n_articles
        self.sort_contribs()
        # if len(new_revisions) > 0 or new_articles > 0:
        dt = time.time() - t0
        t0 = time.time()
        logger.info('Checked %d contributions, found %d new revisions and %d new articles from %s in %.2f secs',
                    tnr, len(new_revisions), new_articles, site.host, dt)

        # 2) Check if pages are redirects (this information can not be cached, because other users may make the page a redirect)
        #    If we fail to notice a redirect, the contributions to the page will be double-counted, so lets check

        #titles = [a.name for a in self.articles.values() if a.site.key == site_key]
        #for s0 in range(0, len(titles), apilim):
        #    ids = '|'.join(titles[s0:s0+apilim])
        #    for page in site.api('query', prop = 'info', titles = ids)['query']['pages'].itervalues():
        #        article_key = site_key + ':' + page['title']
        #        self.articles[article_key].redirect = ('redirect' in page.keys())

        # 3) Fetch info about the new revisions: diff size, possibly content

        props = 'ids|size|parsedcomment'
        if fulltext:
            props += '|content'
        revids = [str(r.revid) for r in new_revisions]
        parentids = []
        nr = 0
        for s0 in range(0, len(new_revisions), apilim):
            #print "API limit is ",apilim," getting ",s0
            ids = '|'.join(revids[s0:s0 + apilim])
            for page in site.api('query', prop='revisions', rvprop=props, revids=ids, uselang='nb')['query']['pages'].itervalues():
                article_key = site_key + ':' + page['title']
                for apirev in page['revisions']:
                    nr += 1
                    rev = self.articles[article_key].revisions[apirev['revid']]
                    rev.parentid = apirev['parentid']
                    rev.size = apirev['size']
                    rev.parsedcomment = apirev['parsedcomment']
                    if '*' in apirev.keys():
                        rev.text = apirev['*']
                        rev.dirty = True
                    if not rev.new:
                        parentids.append(rev.parentid)

        dt = time.time() - t0
        t0 = time.time()
        if nr > 0:
            logger.info('Checked %d revisions, found %d parent revisions in %.2f secs',
                        nr, len(parentids), dt)

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
                        if found:
                            rev.parentsize = apirev['size']
                            if '*' in apirev.keys():
                                rev.parenttext = apirev['*']
                                logger.debug('Got revision text for %s: %d bytes', article.name, len(rev.parenttext))
                            else:
                                logger.warning('Did not get revision text for %s', article.name)
                        else:
                            rev.parenttext = ''  # New page
        if nr > 0:
            dt = time.time() - t0
            logger.info('Checked %d parent revisions in %.2f secs', nr, dt)

    def save_contribs_to_db(self, sql):
        """ Save self.articles to DB so it can be read by add_contribs_from_db """

        cur = sql.cursor()

        contribs_query_params = []
        fulltexts_query_params = []

        for article_key, article in self.articles.iteritems():
            site_key = article.site.key

            for revid, rev in article.revisions.iteritems():
                ts = datetime.fromtimestamp(rev.timestamp).strftime('%F %T')

                # Save revision if not already saved
                if not rev.saved:
                    contribs_query_params.append((revid, site_key, rev.parentid, self.name, article.name, ts, rev.size, rev.parentsize, rev.parsedcomment))
                    rev.saved = True

                if rev.dirty:
                    # Save revision text if we have it and if not already saved
                    fulltexts_query_params.append((revid, site_key, rev.text))
                    fulltexts_query_params.append((rev.parentid, site_key, rev.parenttext))

        # Insert all revisions
        if len(contribs_query_params) > 0:
            logger.info('Adding %d contributions to database', len(contribs_query_params))
            t0 = time.time()

            cur.executemany("""
                insert into contribs (revid, site, parentid, user, page, timestamp, size, parentsize, parsedcomment)
                values (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, contribs_query_params
            )

            dt = time.time() - t0
            logger.info('Added %d contributions to database in %.2f secs', len(contribs_query_params), dt)

        if len(fulltexts_query_params) > 0:
            logger.info('Adding %d fulltexts to database', len(fulltexts_query_params))
            t0 = time.time()

            cur.executemany("""
                insert into fulltexts (revid, site, revtxt)
                values (%s,%s,%s)
                on duplicate key update revtxt=values(revtxt);
                """, fulltexts_query_params
            )

            dt = time.time() - t0
            logger.info('Added %d fulltexts to database in %.2f secs', len(fulltexts_query_params), dt)

        sql.commit()
        cur.close()


    def backfill_text(self, sql, site, rev):
        parentid = None
        props = 'ids|size|content'
        res = site.api('query', prop='revisions', rvprop=props, revids='{}|{}'.format(rev.revid, rev.parentid))['query']
        if res.get('pages') is None:
            logger.info('Failed to get revision %d, revision deleted?', rev.revid)
            return

        for page in res['pages'].itervalues():
            for apirev in page['revisions']:
                if apirev['revid'] == rev.revid:
                    if '*' in apirev.keys():
                        rev.text = apirev['*']
                    else:
                        logger.warning('No revision text available!')
                elif apirev['revid'] == rev.parentid:
                    if '*' in apirev.keys():
                        rev.parenttext = apirev['*']
                    else:
                        logger.warning('No parent revision text available!')

        cur = sql.cursor(buffered=True)

        # Save revision text if we have it and if not already saved
        cur.execute('SELECT revid FROM fulltexts WHERE revid=%s AND site=%s', [rev.revid, site.key])
        if len(rev.text) > 0 and len(cur.fetchall()) == 0:
            cur.execute('INSERT INTO fulltexts (revid, site, revtxt) VALUES (%s,%s,%s)', (rev.revid, site.key, rev.text))
            sql.commit()

        # Save parent revision text if we have it and if not already saved
        if parentid is not None:
            logger.debug('Storing parenttext %d , revid %s ', len(rev.parenttext), rev.parentid)
            cur.execute('SELECT revid FROM fulltexts WHERE revid=%s AND site=%s', [rev.parentid, site.key])
            if len(rev.parenttext) > 0 and len(cur.fetchall()) == 0:
                cur.execute('INSERT INTO fulltexts (revid, site, revtxt) VALUES (%s,%s,%s)', (rev.parentid, site.key, rev.parenttext))
                sql.commit()

        cur.close()

    def add_contribs_from_db(self, sql, start, end, sites):
        """
        Populates self.articles with entries from MySQL DB

            sql   : oursql.Connection object
            start : datetime object
            end   : datetime object
        """
        # logger.info('Reading user contributions from database')

        cur = sql.cursor()
        cur2 = sql.cursor()
        ts_start = start.astimezone(pytz.utc).strftime('%F %T')
        ts_end = end.astimezone(pytz.utc).strftime('%F %T')
        nrevs = 0
        narts = 0
        t0 = time.time()
        cur.execute(u"""
            SELECT
                c.revid, c.site, c.parentid, c.page, c.timestamp, c.size, c.parentsize, c.parsedcomment,
                ft.revtxt,
                ft2.revtxt
            FROM contribs AS c
            LEFT JOIN fulltexts AS ft ON ft.revid = c.revid AND ft.site = c.site
            LEFT JOIN fulltexts AS ft2 ON ft2.revid = c.parentid AND ft2.site = c.site
            WHERE c.user = %s
            AND c.timestamp >= %s AND c.timestamp <= %s
            """,
            (self.name, ts_start, ts_end)
        )
        for row in cur.fetchall():

            rev_id, site_key, parent_id, article_title, ts, size, parentsize, parsedcomment, rev_text, parent_rev_txt = row
            article_key = site_key + ':' + article_title

            ts = unix_time(pytz.utc.localize(ts))

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
                article.add_revision(rev_id, timestamp=ts, parentid=parent_id, size=size, parentsize=parentsize,
                    username=self.name, parsedcomment=parsedcomment, text=rev_text, parenttext=parent_rev_txt)
            rev = self.revisions[rev_id]
            rev.saved = True

            # Add revision text
            if rev_text is None or rev_text == '':
                logger.debug('Article: %s, text missing %s, backfilling', article.name, rev_id)
                self.backfill_text(sql, sites[site_key], rev)

            # Add parent revision text
            if not rev.new:
                if parent_rev_txt is None or parent_rev_txt == '':
                    logger.debug('Article: %s, parent text missing: %s,  backfilling', article.name, parent_id)
                    self.backfill_text(sql, sites[site_key], rev)

        cur.close()
        cur2.close()

        # Always sort after we've added contribs
        self.sort_contribs()

        # if nrevs > 0 or narts > 0:
        dt = time.time() - t0
        logger.info('Read %d revisions, %d pages from database in %.2f secs', nrevs, narts, dt)

    def filter(self, filters, serial=False):

        logger.info('Filtering user contributions')
        n0 = len(self.articles)
        t0 = time.time()

        if len(filters) == 1 and type(filters[0]) == NamespaceFilter:
            pass

        else:
            if serial:
                for filter in filters:
                    logger.debug('>> Before %s (%d) : %s',
                                type(filter).__name__,
                                len(self.articles),
                                ', '.join(self.articles.keys()))

                    self.articles = filter.filter(self.articles)

                    logger.debug('>> After %s (%d) : %s',
                                type(filter).__name__,
                                len(self.articles),
                                ', '.join(self.articles.keys()))
            else:
                articles = odict([])
                logger.debug('>> Before filtering (%d) : %s',
                            len(self.articles),
                            ', '.join(self.articles.keys()))
                for filter in filters:
                    for a in filter.filter(self.articles):
                        if a not in articles:
                            #print a
                            articles[a] = self.articles[a]
                    logger.debug('>> After %s (%d) : %s',
                                type(filter).__name__,
                                len(articles),
                                ', '.join(articles.keys()))
                self.articles = articles

        # We should re-sort afterwards since not all filters preserve the order (notably the CatFilter)
        self.sort_contribs()

        dt = time.time() - t0
        logger.info('%d of %d pages remain after filtering. Filtering took %.2f secs', len(self.articles), n0, dt)
        for a in self.articles.iterkeys():
            logger.debug(' - %s', a)

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
            # if self.contest.verbose:
            #     logger.info(article_key)
            # else:
            #     logger.info('.', newline=False)
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

                            logger.debug('    %d : %d ', revid, rev.get_points())

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

        logger.debug('Formatting results for user %s', self.name)
        # loop over articles
        for article_key, article in self.articles.iteritems():

            brutto = article.get_points(ignore_suspension_period=True, ignore_point_deductions=True, ignore_disqualification=True)
            netto = article.get_points()

            if brutto == 0.0:

                logger.debug('    %s: skipped (0 points)', article_key)

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
                                descr += ' <span style="color:green">+ %.1f p (%s)</span>' % (-p[0], p[1])

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
                    cat_path = [x.split(':')[-1] for x in article.cat_path]
                    titletxt = "''" + _('Category hit') + "'': " + ' &gt; '.join(cat_path) + '<br />'
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
                logger.debug('    %s: %.f / %.f points', article_key, netto, brutto)

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
            out += '%s, {{formatnum:%.2f}} kB\n' % (_('articles') % {'articlecount' : len(entries)}, self.bytes / 1000.)
        if len(entries) > 10:
            out += _('{{Kolonner}}\n')
        out += '\n'.join(entries)
        out += '\n\n'

        return out


class UK(object):

    def __init__(self, page, catignore, sites, homesite, sql, config):
        """
            page: mwclient.Page object
            catignore: string
            sites: list
            sql: mysql Connection object
        """
        self.page = page
        self.name = self.page.name
        self.config = config
        self.homesite = homesite
        resultsSection = config['contestPages']['resultsSection']
        txt = page.text()
        m = re.search('==\s*' + resultsSection + '\s*==', txt)
        if not m:
            raise ParseError(_('Found no "%(section)s" sections in the page "%(page)s"') % {'section': resultsSection, 'page': self.page.name})

        txt = txt[:m.end()]

        self.sql = sql
        sections = [s.strip() for s in re.findall('^[\s]*==([^=]+)==', txt, flags=re.M)]
        self.results_section = sections.index(resultsSection) + 1

        self.sites = sites
        self.users = [User(n, self) for n in self.extract_userlist(txt)]
        self.rules, self.filters = self.extract_rules(txt, catignore)

        logger.info(" - %d participants", len(self.users))
        logger.info(" - %d filter(s) and %d rule(s)", len(self.filters), len(self.rules))
        logger.info(' - Open from %s to %s',
                    self.start.strftime('%F %T'),
                    self.end.strftime('%F %T'))

        # if self.startweek == self.endweek:
        #     logger.info(' - Week %d', self.startweek)
        # else:
        #     logger.info(' - Week %d–%d', self.startweek, self.endweek)

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
        logger.info(" - %d participants", len(lst))
        return lst

    def extract_rules(self, txt, catignore_txt):
        rules = []
        filters = []
        config = self.config

        rulecfg = config['templates']['rule']
        maxpoints = rulecfg['maxpoints']
        site_param = rulecfg['site']

        dp = TemplateEditor(txt)
        if catignore_txt == '':
            catignore = []
            logger.info('Note: catignore page is empty')
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


                par = {remove_control_chars(k): remove_control_chars(v.value) for k, v in par.items()}
                anon = [remove_control_chars(v) if v is not None else None for v in anon]

                key = anon[1].lower()
                params = {}
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
                
                    params['templates'] = anon[2:]
                    params['aliases'] = []
                    for tp in params['templates']:
                        tplpage = self.homesite.pages['Template:' + tp] 
                        if tplpage.exists:
                            params['aliases'].extend([x.page_title for x in tplpage.backlinks(filterredir='redirects')])

                    filt = TemplateFilter(**params)

                elif key == filtercfg['bytes']:
                    if len(anon) < 3:
                        raise ParseError(_('No byte limit (second argument) given to {{tlx|%(template)s|%(firstarg)s}}') % {'template': filtercfg['name'], 'firstarg': filtercfg['bytes']})
                    params['bytelimit'] = anon[2]
                    filt = ByteFilter(**params)

                elif key == filtercfg['category']:
                    if len(anon) < 3:
                        raise ParseError(_('No categories given to {{tlx|%(template)s|%(firstarg)s}}') % {'template': filtercfg['name'], 'firstarg': filtercfg['bytes']})
                    params['ignore'] = catignore
                    if templ.has_param(filtercfg['ignore']):
                        params['ignore'].extend([a.strip() for a in par[filtercfg['ignore']].split(',')])
                    params['sites'] = self.sites
                    params['catnames'] = []
                    for x in anon[2:]:
                        xx = x.split(':')
                        if len(xx) == 1:
                            prefix = self.config['default_prefix']
                            val = xx[0]
                        else:
                            prefix = xx[0]
                            val = xx[1]
                        if len(val) > 0:
                            ns = self.sites[prefix].namespaces[14]
                            valn = val[0].upper() + val[1:]
                            params['catnames'].append('%s:%s:%s' % (prefix, ns, valn))
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
                    params['namespaces'] = [x.strip() for x in anon[2:]]
                    if templ.has_param(site_param):
                        params['site'] = par[site_param]
                    filt = NamespaceFilter(**params)

                elif key == filtercfg['pages']:
                    homesiteprefix = self.homesite.site['servername'].split('.')[0]
                    params['sites'] = self.sites
                    params['pages'] = []
                    for x in anon[2:]:
                        y = x.split(':')
                        if len(y) == 1:
                            params['pages'].append('%s:%s' % (homesiteprefix, x))
                        else:
                            params['pages'].append(x)
                    filt = PageFilter(**params)

                else:
                    raise ParseError(_('Unknown argument given to {{tl|%(template)s}}: %(argument)s') % {'template': filtercfg['name'], 'argument': key})

                foundfilter = False
                #for f in filters:
                #    if type(f) == type(filt):
                #        foundfilter = True
                #        f.extend(filt)
                if not foundfilter:
                    nfilters += 1
                    filters.append(filt)

        ######################## Read rules ########################

        nrules = 0
        for templ in dp.templates[rulecfg['name']]:
            nrules += 1
            p = templ.parameters
            anon = templ.get_anonymous_parameters()

            key = anon[1].lower()

            if key == rulecfg['new']:
                rules.append(NewPageRule(key, anon[2]))

            elif key == rulecfg['redirect']:
                rules.append(RedirectRule(key, anon[2]))

            elif key == rulecfg['qualified']:
                rules.append(QualiRule(key, anon[2]))

            elif key == rulecfg['contrib']:
                rules.append(ContribRule(key, anon[2]))

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
                if templ.has_param(rulecfg['ownwork']):
                    params['ownwork'] = p[rulecfg['ownwork']]
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
                tplpage = self.homesite.pages['Template:' + params['template']]
                if tplpage.exists:
                    params['aliases'] = [x.page_title for x in tplpage.backlinks(filterredir='redirects')]

                rules.append(TemplateRemovalRule(**params))

            elif key == rulecfg['bytebonus']:
                rules.append(ByteBonusRule(key, anon[2], anon[3]))

            elif key == rulecfg['wordbonus']:
                rules.append(WordBonusRule(key, anon[2], anon[3]))

            else:
                raise ParseError(_('Unkown argument given to {{tl|%(template)s}}: %(argument)s') % {'template': rulecfg['name'], 'argument': key})

        ######################## Read infobox ########################

        ibcfg = config['templates']['infobox']
        commonargs = config['templates']['commonargs']

        try:
            infoboks = dp.templates[ibcfg['name']][0]
        except:
            raise ParseError(_('Could not parse the {{tl|%(template)s}} template.') % {'template': ibcfg['name']})

        utc = pytz.utc

        if infoboks.has_param(commonargs['year']) and infoboks.has_param(commonargs['week']):
            year = int(re.sub(r'<\!--.+?-->', r'', unicode(infoboks.parameters[commonargs['year']])).strip())
            startweek = int(re.sub(r'<\!--.+?-->', r'', unicode(infoboks.parameters[commonargs['week']])).strip())
            if infoboks.has_param(commonargs['week2']):
                endweek = re.sub(r'<\!--.+?-->', r'', unicode(infoboks.parameters[commonargs['week2']])).strip()
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
            logger.warning('Found no organizers in {{tl|%s}}.', ibcfg['name'])

        awards = config['awards']
        self.prices = []
        for col in awards.keys():
            if infoboks.has_param(col):
                r = re.sub(r'<\!--.+?-->', r'', unicode(infoboks.parameters[col])).strip()  # strip comments, then whitespace
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
            logger.warning('Found no winner award in {{tl|%s}}. Winner award is set by one of the following: %s.', ibcfg['name'], winnerawards)

        self.prices.sort(key=lambda x: x[2], reverse=True)

        ####################### Check if contest is in DB yet ##################

        cur = self.sql.cursor()
        cur.execute('SELECT contest_id FROM contests WHERE site=%s AND name=%s', [self.config['default_prefix'], self.name])
        rows = cur.fetchall()
        if len(rows) == 0:
            cur.execute('INSERT INTO contests (site, name, start_date, end_date) VALUES (%s,%s,%s,%s)', [self.config['default_prefix'], self.name, self.start.strftime('%F %T'), self.end.strftime('%F %T')])
            self.sql.commit()
        cur.close()

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
                logger.info('poengtrekk: USER: %s REVISION: %s POINTS: %d REASON: %s', uname, revid, points, reason)
                for u in self.users:
                    if u.name == uname:
                        u.point_deductions.append([revid, points, reason])
                        ufound = True
                if not ufound:
                    raise ParseError(_("Couldn't find the user %(user)s given to the {{tl|%(template)s}} template.") % {'user': uname, 'template': dicfg['name']})

        pocfg = config['templates']['bonus']
        if pocfg['name'] in dp.templates:
            for templ in dp.templates[pocfg['name']]:
                uname = templ.parameters[1].value
                revid = int(templ.parameters[2].value)

                #if not re.match('^[a-z]{2,3}:', aname):
                #    aname = config['default_prefix'] + ':' + aname

                points = float(templ.parameters[3].value.replace(',', '.'))
                reason = templ.parameters[4].value
                ufound = False
                logger.info('poeng: USER: %s REVISION: %s POINTS: %d REASON: %s', uname, revid, points, reason)
                for u in self.users:
                    if u.name == uname:
                        u.point_deductions.append([revid, -points, reason])
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

    def format_heading(self):
        if self.startweek == self.endweek:
            return _('Weekly contest for week %(week)d') % {'week': self.startweek}
        else:
            return _('Weekly contest for week %(startweek)d–%(endweek)d') % {'startweek': self.startweek, 'endweek': self.endweek}

    def deliver_message(self, username, topic, body, sig='~~~~'):
        logger.info('Delivering message to %s', username)

        prefix = self.homesite.namespaces[3]
        prefixed = prefix + ':' + username

        flinfo = self.homesite.api(action='query', prop='flowinfo', titles=prefixed)
        flow_enabled = ('enabled' in flinfo['query']['pages'].values()[0]['flowinfo']['flow'])

        pagename = '%s:%s' % (prefix, username)

        if flow_enabled:
            token = self.homesite.get_token('csrf')
            self.homesite.api(action='flow',
                              submodule='new-topic',
                              page=pagename,
                              nttopic=topic,
                              ntcontent=body,
                              ntformat='wikitext',
                              token=token)

        else:
            page = self.homesite.pages[pagename]
            page.save(text=body + ' ' + sig, bot=False, section='new', summary=topic)


    def deliver_prices(self, sql, siteprefix, ktitle, simulate):

        config = self.config
        heading = self.format_heading()

        cur = sql.cursor()
        cur.execute('SELECT contest_id FROM contests WHERE site=%s AND name=%s', [config['default_prefix'], ktitle])
        contest_id = cur.fetchall()[0][0]

        logger.info('Delivering prices for contest %d' % (contest_id,))

        # sql.commit()
        # cur.close()

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
                        if prizefound:
                            mld += '|%s=%s' % (r[0], self.config['templates']['commonargs'][True])
                        else:
                            mld = self.format_msg('winner_template', r[0])
                        prizefound = True
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

            mld += _("Note that the contest this week is [[%(url)s|{{%(template)s|%(weekarg)s=%(week)s}}]]. Join in!") % {
                'url': self.config['pages']['base'] + ' ' + yearweek,
                'template': self.config['templates']['contestlist']['name'],
                'weekarg': self.config['templates']['commonargs']['week'],
                'week': yearweek
            }
            sig = _('Regards') + ' ' + ', '.join(['[[%s:%s|%s]]' % (userprefix, s, s) for s in self.ledere]) + ' ' + _('and') + ' ~~~~'

            if prizefound:

                if not simulate:
                    cur.execute('SELECT prize_id FROM prizes WHERE contest_id=%s AND site=%s AND user=%s', [contest_id, siteprefix, u.name])
                    rows = cur.fetchall()
                    if len(rows) == 0:
                        self.deliver_message(u.name, heading, mld, sig)
                        cur.execute('INSERT INTO prizes (contest_id, site, user, timestamp) VALUES (%s,%s,%s, NOW())', [contest_id, siteprefix, u.name])
                        sql.commit()
            else:
                logger.warning('No price found for %s', u.name)

    def deliver_leader_notification(self, pagename):
        heading = self.format_heading()
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
            sig = _('Thanks, ~~~~')

            logger.info('Leverer arrangørmelding til %s', pagename)
            self.deliver_message(u, heading, mld, sig)


    def deliver_receipt_to_leaders(self):
        heading = self.format_heading()
        usertalkprefix = self.homesite.namespaces[3]

        args = {'prefix': self.homesite.site['server'] + self.homesite.site['script'], 'page': 'Special:Contributions'}
        link = '%(prefix)s?title=%(page)s&contribs=user&target=UKBot&namespace=3' % args
        mld = '\n:' + _('Awards have been [%(link)s sent out].') % {'link': link}
        for u in self.ledere:
            page = self.homesite.pages['%s:%s' % (usertalkprefix, u)]
            logger.info('Leverer kvittering til %s', page.name)

            # Find section number
            txt = page.text()
            sections = [s.strip() for s in re.findall('^[\s]*==([^=]+)==', txt, flags=re.M)]
            try:
                csection = sections.index(heading) + 1
            except ValueError:
                logger.error('Fant ikke "%s" i "%s', heading, page.name)
                return

            # Append text to section
            txt = page.text(section=csection)
            page.save(appendtext=mld, bot=False, summary='== ' + heading + ' ==')

    def delete_contribs_from_db(self):
        cur = self.sql.cursor()
        cur2 = self.sql.cursor()
        ts_start = self.start.astimezone(pytz.utc).strftime('%F %T')
        ts_end = self.end.astimezone(pytz.utc).strftime('%F %T')
        ndel = 0
        cur.execute(u"SELECT site,revid,parentid FROM contribs WHERE timestamp >= %s AND timestamp <= %s", (ts_start, ts_end))
        for row in cur.fetchall():
            cur2.execute(u"DELETE FROM fulltexts WHERE site=%s AND revid=%s", [row[0], row[1]])
            ndel += cur2.rowcount
            cur2.execute(u"DELETE FROM fulltexts WHERE site=%s AND revid=%s", [row[0], row[2]])
            ndel += cur2.rowcount

        cur.execute('SELECT COUNT(*) FROM fulltexts')
        nremain = cur.fetchone()[0]
        logger.info('Cleaned %d rows from fulltexts-table. %d rows remain', ndel, nremain)

        cur.execute(u"""DELETE FROM contribs WHERE timestamp >= %s AND timestamp <= %s""", (ts_start, ts_end))
        ndel = cur.rowcount
        cur.execute('SELECT COUNT(*) FROM contribs')
        nremain = cur.fetchone()[0]
        logger.info('Cleaned %d rows from contribs-table. %d rows remain', ndel, nremain)

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
                d = [self.config['default_prefix'], self.name, u.name, 'suspension', '']
                cur.execute('SELECT id FROM notifications WHERE site=%s AND contest=%s AND user=%s AND class=%s AND args=%s', d)
                if len(cur.fetchall()) == 0:
                    msgs.append('Du er inntil videre suspendert fra konkurransen med virkning fra %s. Dette innebærer at dine bidrag gjort etter dette tidspunkt ikke teller i konkurransen, men alle bidrag blir registrert og skulle suspenderingen oppheves i løpet av konkurranseperioden vil også bidrag gjort i suspenderingsperioden telle med. Vi oppfordrer deg derfor til å arbeide med problemene som førte til suspenderingen slik at den kan oppheves.' % u.suspended_since.strftime(_('%e. %B %Y, %H:%M')).decode('utf-8'))
                    if not simulate:
                        cur.execute('INSERT INTO notifications (site, contest, user, class, args) VALUES (%s,%s,%s,%s,%s)', d)
            discs = []
            for article_key, article in u.articles.iteritems():
                if article.disqualified:
                    d = [self.config['default_prefix'], self.name, u.name, 'disqualified', article_key]
                    cur.execute('SELECT id FROM notifications WHERE site=%s AND contest=%s AND user=%s AND class=%s AND args=%s', d)
                    if len(cur.fetchall()) == 0:
                        discs.append('[[:%s|%s]]' % (article_key, article.name))
                        if not simulate:
                            cur.execute('INSERT INTO notifications (site, contest, user, class, args) VALUES (%s,%s,%s,%s,%s)', d)
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
                logger.info('Leverer advarsel til %s', page.name)
                if simulate:
                    logger.info(msg)
                else:
                    page.save(text=msg, bot=False, section='new', summary=heading)
            self.sql.commit()


def get_contest_page_titles(sql, homesite, config):
    cursor = sql.cursor()
    contests = set()

    # 1) Check if there is a contest to close

    cursor.execute('SELECT name FROM contests WHERE site=%s AND ended=1 AND closed=0 LIMIT 1', [config['default_prefix']])
    closing_contests = cursor.fetchall()
    if len(closing_contests) != 0:
        page_title = closing_contests[0][0]
        lastrev = homesite.pages[config['awardstatus']['pagename']].revisions(prop='user|comment').next()
        closeuser = lastrev['user']
        revc = lastrev['comment']
        if revc.find('/* ' + config['awardstatus']['send'] + ' */') == -1:
            logger.info('Contest [[%s]] is to be closed, but award delivery has not been confirmed yet', page_title)
        else:
            logger.info('Will close contest [[%s]], award delivery has been confirmed', page_title)
            contests.add(page_title)
            yield ('closing', page_title)

    # 2) Check if there is a contest to end
    now = server_tz.localize(datetime.now())
    now_s = now.astimezone(wiki_tz).strftime('%F %T')
    cursor.execute('SELECT name FROM contests WHERE site=%s AND ended=0 AND closed=0 AND end_date < %s LIMIT 1', [config['default_prefix'], now_s])
    ending_contests = cursor.fetchall()
    if len(ending_contests) != 0:
        page_title = ending_contests[0][0]
        logger.info('Contest %s just ended', ending_contests[0])
        contests.add(page_title)
        yield ('ending', page_title)

    # 3) Get contest page from current date
    if config['pages'].get('default') is not None:
        page_title = config['pages']['default']
        # subtract one hour, so we close last week's contest right after midnight
        # w = Week.withdate((now - timedelta(hours=1)).astimezone(wiki_tz).date())
        w = Week.withdate(now.astimezone(wiki_tz).date())
        page_title = page_title % { 'year': w.year, 'week': w.week }
        #strftime(page_title.encode('utf-8')).decode('utf-8')
        if page_title not in contests:
            contests.add(page_title)
            yield ('normal', page_title)

    if config['pages'].get('active_contest_category') is not None:
        for page in homesite.categories['Artikkelkonkurranser'].members(namespace=4):
            if page.name not in contests:
                contests.add(page.name)
                yield ('normal', page.name)

    cursor.close()


def get_contest_pages(sql, homesite, config, page_title=None):

    if page_title is not None:
        pages = [('normal', page_title)]
    else:
        pages = get_contest_page_titles(sql, homesite, config)


    for p in pages:
        page = homesite.pages[p[1]]
        page = page.resolve_redirect()

        yield (p[0], page)


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


class MyConverter(mysql.connector.conversion.MySQLConverter):

    def row_to_python(self, row, fields):
        row = super(MyConverter, self).row_to_python(row, fields)

        def to_unicode(col):
            if type(col) == bytearray:
                return col.decode('utf-8')
            return col

        return[to_unicode(col) for col in row]


def main():

    # Configure home site (where the contests live)
    host = config['homesite']
    homesite = Site(host, **config['account'])
    assert homesite.logged_in

    # Connect to DB
    sql = mysql.connector.connect(converter_class=MyConverter, **config['db'])
    logger.debug('Connected to database')

    # Determine what to work with
    active_contests = list(get_contest_pages(sql, homesite, config, args.page))

    logger.info('Number of active contests: %d', len(active_contests))
    for contest in active_contests:
        update_contest(contest, config, homesite, sql)


def update_contest(contest, config, homesite, sql):
    kstatus, kpage = contest

    logger.info('Current contest: [[%s]]', kpage.name)

    prefix = homesite.host.split('.')[0]
    sites = {prefix: homesite}
    if 'othersites' in config:
        for host in config['othersites']:
            prefix = host.split('.')[0]
            sites[prefix] = Site(host, **config['account'])

    cpage = config['pages']['catignore']

    if not kpage.exists:
        logger.error('Contest page [[%s]] does not exist! Exiting', kpage.page_title)
        return

    # Initialize the contest
    try:
        uk = UK(kpage, homesite.pages[cpage].text(), sites=sites, homesite=homesite, sql=sql, config=config)
    except ParseError as e:
        err = "\n* '''%s'''" % e.msg
        out = '\n{{%s | error | %s }}' % (config['templates']['botinfo'], err)
        if args.simulate:
            logger.info(out)
        else:
            kpage.save('dummy', summary=_('UKBot encountered a problem'), appendtext=out)
        raise

    # if kstatus == 'closing' and closeuser not in uk.ledere:
    #     log('!! Konkurransen ble forsøkt avsluttet av %s, men konkurranseledere er oppgitt som: %s' % (closeuser, ', '.join(uk.ledere)))
    #     #log('!! Konkurransen ble forsøkt avsluttet av andre enn konkurranseleder')
    #     #return


    # Loop over users

    narticles = 0
    nbytes = 0
    nwords = 0
    nnewpages = 0

    # extraargs = {'namespace': 0}
    extraargs = {}
    host_filter = None
    for f in uk.filters:
        if type(f) == NamespaceFilter:
            extraargs['namespace'] = '|'.join(f.namespaces)
            host_filter = f.site

    for u in uk.users:

        logger.info('=== User:%s ===', u.name)

        # First read contributions from db
        u.add_contribs_from_db(sql, uk.start, uk.end, sites)

        # Then fill in new contributions from wiki
        for site in sites.itervalues():

            if host_filter is None or site.host == host_filter:
                u.add_contribs_from_wiki(site, uk.start, uk.end, fulltext=True, **extraargs)

        # And update db
        u.save_contribs_to_db(sql)

        try:

            # Filter out relevant articles
            u.filter(uk.filters)

            # And calculate points
            # log(' -> Analyzing ', newline=False)
            u.analyze(uk.rules)
            logger.info('%s: %.f points', u.name, u.points)

            narticles += len(u.articles)
            nbytes += u.bytes
            nwords += u.words
            nnewpages += u.newpages

        except ParseError as e:
            err = "\n* '''%s'''" % e.msg
            out = '\n{{%s | error | %s }}' % (config['templates']['botinfo'], err)
            if args.simulate:
                logger.error(out)
            else:
                kpage.save('dummy', summary=_('UKBot encountered a problem'), appendtext=out)
            raise

    # Sort users by points

    logger.info('Sorting contributions and preparing contest page')

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
    if kstatus == 'ending':
        # Konkurransen er nå avsluttet – takk til alle som deltok! Rosetter vil bli delt ut så snart konkurransearrangøren(e) har sjekket resultatene.
        out += "''" + _('This contest is closed – thanks to everyone who participated! Awards will be sent out as soon as the contest organizer has checked the results.') + "''\n\n"
    elif kstatus == 'closing':
        out += "''" + _('This contest is closed – thanks to everyone who participated!') + "''\n\n"
    else:
        oargs = {
            'lastupdate': now.astimezone(wiki_tz).strftime(_('%e. %B %Y, %H:%M')).decode('utf-8'),
            'startdate': uk.start.strftime(_('%e. %B %Y, %H:%M')).decode('utf-8'),
            'enddate': uk.end.strftime(_('%e. %B %Y, %H:%M')).decode('utf-8')
        }
        out += "''" + _('Last updated %(lastupdate)s. The contest is open from %(startdate)s to %(enddate)s.') % oargs + "''\n\n"

    for i, u in enumerate(uk.users):
        out += u.format_result(pos=i, closing=(kstatus == 'closing'), prices=uk.prices)

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
        txt = kpage.text()
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

            logger.info('Updating wiki, section = %d', uk.results_section)
            if kstatus == 'ending':
                kpage.save(txt, summary=_('Updating with final results, the contest is now closed.'))
            elif kstatus == 'closing':
                kpage.save(txt, summary=_('Checking results and handing out awards'))
            else:
                kpage.save(txt, summary=_('Updating'))

    if args.output != '':
        logger.info("Writing output to file")
        f = codecs.open(args.output, 'w', 'utf-8')
        f.write(out)
        f.close()

    if kstatus == 'ending':
        logger.info('Ending contest')
        if not args.simulate:
            uk.deliver_leader_notification(kpage.name)

            aws = config['awardstatus']
            page = homesite.pages[aws['pagename']]
            page.save(text=aws['wait'], summary=aws['wait'], bot=True)

            cur = sql.cursor()
            cur.execute('UPDATE contests SET ended=1 WHERE site=%s AND name=%s', [config['default_prefix'], kpage.name])
            sql.commit()
            cur.close()

    if kstatus == 'closing':
        logger.info('Delivering prices')

        uk.deliver_prices(sql, config['default_prefix'], kpage.name, args.simulate)

        cur = sql.cursor()

        for u in uk.users:
            arg = [config['default_prefix'], kpage.name, u.name, int(uk.startweek), u.points, int(u.bytes), int(u.newpages), 0]
            if uk.startweek != uk.endweek:
                arg[-1] = int(uk.endweek)
            #print arg
            if not args.simulate:
                cur.execute(u"INSERT INTO users (site, contest, user, week, points, bytes, newpages, week2) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", arg)

        if not args.simulate:
            cur.execute('UPDATE contests SET closed=1 WHERE site=%s AND name=%s', [config['default_prefix'], kpage.name])
            sql.commit()

        cur.close()

        aws = config['awardstatus']
        page = homesite.pages[aws['pagename']]
        page.save(text=aws['sent'], summary=aws['sent'], bot=True)

        # if not args.simulate:
        #
        # Skip for now: not Flow compatible
        #     uk.deliver_receipt_to_leaders()

        logger.info('Cleaning database')
        if not args.simulate:
            uk.delete_contribs_from_db()

    # Notify users about issues

    # uk.deliver_warnings(simulate=args.simulate)

    # Update WP:UK

    if 'redirect' in config['pages']:
        if re.match('^' + config['pages']['base'], kpage.name) and not args.simulate and kstatus == 'normal':
            page = homesite.pages[config['pages']['redirect']]
            txt = _('#REDIRECT [[%s]]') % kpage.name
            if page.text() != txt:
                page.save(txt, summary=_('Redirecting to %s') % kpage.name)

    # Update Wikipedia:Portal/Oppslagstavle

    if 'noticeboard' in config:
        boardname = config['noticeboard']['name']
        boardtpl = config['noticeboard']['template']
        commonargs = config['templates']['commonargs']
        tplname = boardtpl['name']
        oppslagstavle = homesite.pages[boardname]
        txt = oppslagstavle.text()

        dp = TemplateEditor(txt)
        ntempl = len(dp.templates[tplname])
        if ntempl != 1:
            raise StandardError('Feil: Fant %d %s-maler i %s' % (ntempl, tplname, boardname))

        tpl = dp.templates[tplname][0]
        now2 = now.astimezone(wiki_tz)
        if int(tpl.parameters['uke']) != int(now2.strftime('%V')):
            logger.info('Updating noticeboard: %s', boardname)
            tpllist = config['templates']['contestlist']
            commonargs = config['templates']['commonargs']
            tema = homesite.api('parse', text='{{subst:%s|%s=%s}}' % (tpllist['name'], commonargs['week'], now2.strftime('%Y-%V')), pst=1, onlypst=1)['parse']['text']['*']
            tpl.parameters[1] = tema
            tpl.parameters[boardtpl['date']] = now2.strftime('%e. %h')
            tpl.parameters[commonargs['year']] = now2.isocalendar()[0]
            tpl.parameters[commonargs['week']] = now2.isocalendar()[1]
            txt2 = dp.wikitext()
            if txt != txt2:
                oppslagstavle.save(txt2, summary=_('The weekly contest is: %(link)s') % {'link': tema})

    # Make a nice plot

    if 'plot' in config:
        uk.plot()


if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='The UKBot')
    parser.add_argument('--page', required=False, help='Name of the contest page to work with')
    parser.add_argument('--simulate', action='store_true', default=False, help='Do not write results to wiki')
    parser.add_argument('--output', nargs='?', default='', help='Write results to file')
    parser.add_argument('--log', nargs='?', default='', help='Log file')
    parser.add_argument('--verbose', action='store_true', default=False, help='More verbose logging')
    parser.add_argument('--close', action='store_true', help='Close contest')
    parser.add_argument('--config', nargs='?', default='config.yml', help='Config file')
    args = parser.parse_args()

    if args.verbose:
        syslog.setLevel(logging.DEBUG)
    else:
        syslog.setLevel(logging.INFO)

    if args.log != '':
        ukcommon.logfile = open(args.log, 'a')

    config = yaml.load(open(args.config, 'r'))
    # rollbar.init(config['rollbar_token'], 'production')
    wiki_tz = pytz.timezone(config['wiki_timezone'])
    server_tz = pytz.timezone(config['server_timezone'])

    t, _ = init_localization(config['locale'])
    from ukrules import *
    from ukfilters import *

    mainstart = server_tz.localize(datetime.now())
    mainstart_s = time.time()

    logger.info('UKBot starting at %s (server time), %s (wiki time)',
                mainstart.strftime('%F %T'),
                mainstart.astimezone(wiki_tz).strftime('%F %T'))
    logger.info('Running on %s %s %s', *platform.linux_distribution())

    main()

    runend = server_tz.localize(datetime.now())
    runend_s = time.time()

    runtime = runend_s - runstart_s
    logger.info('UKBot finishing at %s. Runtime was %.f seconds (total) or %.f seconds (excluding initialization).',
                runend.strftime('%F %T'),
                runend_s - runstart_s,
                runend_s - mainstart_s)

    #try:
    #    main()
    #except IOError:
    #    rollbar.report_message('Got an IOError in the main loop', 'warning')
    #except:
    #    # catch-all
    #    rollbar.report_exc_info()
