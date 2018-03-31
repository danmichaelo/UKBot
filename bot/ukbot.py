# encoding=utf-8
# vim: fenc=utf-8 et sw=4 ts=4 sts=4 ai
import time
import sys
runstart_s = time.time()

import logging
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)     # DEBUG if verbose
syslog = logging.StreamHandler()
# formatter = logging.Formatter('%(asctime)s [%(mem_usage)s MB] %(name)s %(levelname)s : %(message)s')
logger.addHandler(syslog)
syslog.setLevel(logging.INFO)

if sys.version_info < (3, 4):
    print('Requires Python >= 3.4')
    sys.exit(1)

logger.info('Loading')

import matplotlib
matplotlib.use('svg')

import weakref
import numpy as np
import time
import calendar
from datetime import datetime, timedelta
from datetime import time as dt_time
import gettext
import pytz
from isoweek import Week  # Sort-of necessary until datetime supports %V, see http://bugs.python.org/issue12006
                          # and See http://stackoverflow.com/questions/5882405/get-date-from-iso-week-number-in-python
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
import mwtemplates
from mwtemplates import TemplateEditor
from mwtextextractor import get_body_text
import ukcommon

from ukcommon import get_mem_usage, Localization, t, _, InvalidContestPage
import locale
from ukrules import *
from ukfilters import *


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
 
all_chars = (chr(i) for i in range(sys.maxunicode))
control_chars = ''.join(c for c in all_chars if unicodedata.category(c) in set(['Cc','Cf']))
control_char_re = re.compile('[%s]' % re.escape(control_chars))
logger.info('Control char regexp is ready')

def remove_control_chars(s):
    if isinstance(s, str):
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


class Site(mwclient.Site):

    def __init__(self, host, prefixes, **kwargs):

        self.errors = []
        self.name = host
        self.key = host
        self.prefixes = prefixes
        logger.debug('Initializing site: %s', host)
        ua = 'UKBot. Run by User:Danmichaelo. Using mwclient/' + mwclient.__ver__
        mwclient.Site.__init__(self, host, clients_useragent=ua, **kwargs)

        res = self.api('query', meta='siteinfo', siprop='magicwords|namespaces|namespacealiases|interwikimap')['query']

        self.file_prefixes = [res['namespaces']['6']['*'], res['namespaces']['6']['canonical']] + [x['*'] for x in res['namespacealiases'] if x['id'] == 6]
        logger.debug('File prefixes: %s', '|'.join(self.file_prefixes))

        redirect_words = [x['aliases'] for x in res['magicwords'] if x['name'] == 'redirect'][0]
        logger.debug('Redirect words: %s', '|'.join(redirect_words))
        self.redirect_regexp = re.compile(u'(?:%s)' % u'|'.join(redirect_words), re.I)

        self.interwikimap = {x['prefix']: x['url'].split('//')[1].split('/')[0].split('?')[0] for x in res['interwikimap']}

    def get_revertpage_regexp(self):
        msg = self.pages['MediaWiki:Revertpage'].text()
        msg = re.sub('\[\[[^\]]+\]\]', '.*?', msg)
        return msg

    def match_prefix(self, prefix):
        return prefix in self.prefixes or prefix == self.key

    def link_to(self, page):
        link = '%s:%s' % (self.page.site.prefixes[0], page.name)
        return link.lstrip(':')


class Article(object):

    def __init__(self, site, user, name):
        """
        An article is uniquely identified by its name and its site
        """
        self.site = weakref.ref(site)
        self.user = weakref.ref(user)
        self.name = name
        self.disqualified = False

        self.revisions = odict()
        #self.redirect = False
        self.errors = []

    def __eq__(other):
        if self.site() == other.site() and self.name == other.name:
            return True
        else:
            return False

    def __str__(self):
        return "<Article %s:%s for user %s>" % (self.site().key, self.name, self.user().name)

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
        self.user().revisions[revid] = rev
        return rev

    @property
    def bytes(self):
        return np.sum([rev.bytes for rev in self.revisions.values()])

    @property
    def words(self):
        """
        Returns the total number of words added to this Article. The number
        will never be negative, but words removed in one revision will
        contribute negatively to the sum.
        """
        return np.max([0, np.sum([rev.words for rev in self.revisions.values()])])

    @property
    def points(self):
        """ The article score is the sum of the score for its revisions, independent of whether the article is disqualified or not """
        return self.get_points()
        #return np.sum([rev.get_points() for rev in self.revisions.values()])

    def get_points(self, ptype='', ignore_max=False, ignore_suspension_period=False,
                   ignore_disqualification=False, ignore_point_deductions=False):
        p = 0.
        article_key = self.site().key + ':' + self.name
        if ignore_disqualification or not article_key in self.user().disqualified_articles:
            for revid, rev in self.revisions.items():
                dt = pytz.utc.localize(datetime.fromtimestamp(rev.timestamp))
                if ignore_suspension_period is True or self.user().suspended_since is None or dt < self.user().suspended_since:
                    p += rev.get_points(ptype, ignore_max, ignore_point_deductions)
                else:
                    logger.debug('!! Skipping revision %d in suspension period', revid)

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
        self.article = weakref.ref(article)
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
        self._te_text = None  # Loaded as needed
        self._te_parenttext = None  # Loaded as needed

        self.points = []

        for k, v in kwargs.items():
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
                raise Exception('add_revision got unknown argument %s' % k)

        for pd in self.article().user().point_deductions:
            if pd['revid'] == self.revid and self.article().site().match_prefix(pd['site']):
                self.add_point_deduction(pd['points'], pd['reason'])

    def te_text(self):
        if self._te_text is None:
            self._te_text = TemplateEditor(re.sub('<nowiki ?/>', '', self.text))
        return self._te_text

    def te_parenttext(self):
        if self._te_parenttext is None:
            self._te_parenttext = TemplateEditor(re.sub('<nowiki ?/>', '', self.parenttext))
        return self._te_parenttext

    def __str__(self):
        return ("<Revision %d for %s:%s>" % (self.revid, self.article().site().key, self.article().name))

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
            pass

        mt1 = get_body_text(re.sub('<nowiki ?/>', '', self.text))
        mt0 = get_body_text(re.sub('<nowiki ?/>', '', self.parenttext))

        if self.article().site().key == 'ja.wikipedia.org':
            words1 = len(mt1) / 3.0
            words0 = len(mt0) / 3.0
        elif self.article().site().key == 'zh.wikipedia.org':
            words1 = len(mt1) / 2.0
            words0 = len(mt0) / 2.0
        else:
            words1 = len(mt1.split())
            words0 = len(mt0.split())

        charcount = len(mt1) - len(mt0)
        self._wordcount = words1 - words0

        logger.debug('Wordcount: Revision %s@%s: %+d bytes, %+d characters, %+d words',
                     self.revid, self.article().site().key, self.bytes, charcount, self._wordcount)

        if not self.new and words0 == 0 and self._wordcount > 1:
            w = _('Revision [//%(host)s/w/index.php?diff=prev&oldid=%(revid)s %(revid)s]: The word count difference might be wrong, because no words were found in the parent revision (%(parentid)s) of size %(size)d, possibly due to unclosed tags or templates in that revision.') % {
                'host': self.article().site().host,
                'revid': self.revid,
                'parentid': self.parentid,
                'size': len(self.parenttext)
            }
            logger.warning(w)
            self.errors.append(w)

        elif self._wordcount > 10 and self._wordcount > self.bytes:
            w = _('Revision [//%(host)s/w/index.php?diff=prev&oldid=%(revid)s %(revid)s]: The word count difference might be wrong, because the word count increase (%(words)d) is larger than the byte increase (%(bytes)d). Wrong word counts may occur for invalid wiki text.') % {
                'host': self.article().site().host,
                'revid': self.revid,
                'words': self._wordcount,
                'bytes': self.bytes
            }
            logger.warning(w)
            self.errors.append(w)

        #s = _('A problem encountered with revision %(revid)d may have influenced the word count for this revision: <nowiki>%(problems)s</nowiki> ')
        #s = _('Et problem med revisjon %d kan ha påvirket ordtellingen for denne: <nowiki>%s</nowiki> ')
        del mt1
        del mt0
        # except DanmicholoParseError as e:
        #     log("!!!>> FAIL: %s @ %d" % (self.article().name, self.revid))
        #     self._wordcount = 0
        #     #raise
        return self._wordcount

    @property
    def new(self):
        return self.parentid == 0 or (self.parentredirect and not self.redirect)

    @property
    def redirect(self):
        return bool(self.article().site().redirect_regexp.match(self.text))

    @property
    def parentredirect(self):
        return bool(self.article().site().redirect_regexp.match(self.parenttext))

    def get_link(self):
        """ returns a link to revision """
        q = {'title': self.article().name, 'oldid': self.revid}
        if not self.new:
            q['diff'] = 'prev'
        return '//' + self.article().site().host + self.article().site().site['script'] + '?' + urllib.parse.urlencode(q)

    def get_parent_link(self):
        """ returns a link to parent revision """
        q = {'title': self.article().name, 'oldid': self.parentid}
        return '//' + self.article().site().host + self.article().site().site['script'] + '?' + urllib.parse.urlencode(q)

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
        self.contest = weakref.ref(contest)
        self.suspended_since = None
        self.disqualified_articles = []
        self.point_deductions = []

    def __repr__(self):
        return "<User %s>" % self.name

    def sort_contribs(self):

        # sort revisions by revision id
        for article in self.articles.values():
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

        site_key = site.host

        ts_start = start.astimezone(pytz.utc).strftime('%FT%TZ')
        ts_end = end.astimezone(pytz.utc).strftime('%FT%TZ')

        # 1) Fetch user contributions

        args = {}
        if 'namespace' in kwargs:
            args['namespace'] = kwargs['namespace']
            logger.debug('Limiting to namespaces: %s', args['namespace'])

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
                logger.info('Found %d new revisions from API so far (%.0f secs elapsed)',
                            len(new_revisions), dt0)


            #pageid = c['pageid']
            if 'comment' in c:
                article_comment = c['comment']

                ignore = False
                for pattern in self.contest().config['ignore']:
                    if re.search(pattern, article_comment):
                        ignore = True
                        logger.info('Ignoring revision %d of %s:%s because it matched /%s/', c['revid'], site_key, c['title'], pattern)
                        break

                if not ignore:
                    rev_id = c['revid']
                    article_title = c['title']
                    article_key = site_key + ':' + article_title

                    if rev_id in self.revisions:
                        # We check self.revisions instead of article.revisions, because the revision may
                        # already belong to "another article" (another title) if the article has been moved

                        if self.revisions[rev_id].article().name != article_title:
                            rev = self.revisions[rev_id]
                            logger.info('Moving revision %d from "%s" to "%s"', rev_id, rev.article().name, article_title)
                            article = self.add_article_if_necessary(site, article_title)
                            rev.article().revisions.pop(rev_id)  # remove from old article
                            article.revisions[rev_id] = rev    # add to new article
                            rev.article = weakref.ref(article)              # and update reference

                    else:

                        article = self.add_article_if_necessary(site, article_title)
                        rev = article.add_revision(rev_id, timestamp=time.mktime(c['timestamp']), username=self.name)
                        rev.saved = False  # New revision that should be stored in DB
                        new_revisions.append(rev)

        # If revisions were moved from one article to another, and the redirect was not created by the same user,
        # some articles may now have zero revisions. We should drop them
        for article_key, article in self.articles.items():
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
        #    for page in site.api('query', prop = 'info', titles = ids)['query']['pages'].values():
        #        article_key = site_key + ':' + page['title']
        #        self.articles[article_key].redirect = ('redirect' in page.keys())

        # 3) Fetch info about the new revisions: diff size, possibly content

        props = 'ids|size|parsedcomment'
        if fulltext:
            props += '|content'
        revids = [str(r.revid) for r in new_revisions]
        parentids = set()
        revs = set()

        while len(revids) > 0:
            try:
                ids = '|'.join(revids[:apilim])
                logger.info('Checking ids: %s', ids)
                for page in site.api('query', prop='revisions', rvprop=props, revids=ids, uselang='nb')['query']['pages'].values():
                    article_key = site_key + ':' + page['title']
                    for apirev in page['revisions']:
                        rev = self.articles[article_key].revisions[apirev['revid']]
                        rev.parentid = apirev['parentid']
                        rev.size = apirev['size']
                        rev.parsedcomment = apirev['parsedcomment']
                        if '*' in apirev.keys():
                            rev.text = apirev['*']
                            rev.dirty = True
                        if not rev.new:
                            parentids.add(rev.parentid)
                        revs.add(apirev['revid'])
                revids = revids[apilim:]
            except KeyError:
                # We ran into Manual:$wgAPIMaxResultSize, try reducing
                apilim = 1

        dt = time.time() - t0
        t0 = time.time()
        if len(revs) > 0:
            logger.info('Checked %d revisions, found %d parent revisions in %.2f secs',
                        len(revs), len(parentids), dt)

        if len(revs) != len(new_revisions):
            raise Exception('Expected %d revisions, but got %d' % (len(new_revisions), len(revs)))

        # 4) Fetch info about the parent revisions: diff size, possibly content

        props = 'ids|size'
        if fulltext:
            props += '|content'
        nr = 0
        parentids = [str(i) for i in parentids]
        for s0 in range(0, len(parentids), apilim):
            ids = '|'.join(parentids[s0:s0 + apilim])
            for page in site.api('query', prop='revisions', rvprop=props, revids=ids)['query']['pages'].values():
                article_key = site_key + ':' + page['title']

                # In the case of a merge, the new title (article_key) might not be part of the user's 
                # contribution list (self.articles), so we need to check:
                if article_key in self.articles:
                    article = self.articles[article_key]
                    for apirev in page['revisions']:
                        nr += 1
                        parentid = apirev['revid']
                        found = False
                        for revid, rev in article.revisions.items():
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

        for article_key, article in self.articles.items():
            site_key = article.site().key

            for revid, rev in article.revisions.items():
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

        chunk_size = 100
        for n in range(0, len(fulltexts_query_params), chunk_size):
            data = fulltexts_query_params[n:n+chunk_size]
            logger.info('Adding %d fulltexts to database', len(data))
            t0 = time.time()

            cur.executemany("""
                insert into fulltexts (revid, site, revtxt)
                values (%s,%s,%s)
                on duplicate key update revtxt=values(revtxt);
                """, data
            )

            dt = time.time() - t0
            logger.info('Added %d fulltexts to database in %.2f secs', len(data), dt)

        sql.commit()
        cur.close()

    def backfill_text(self, sql, site, rev):
        parentid = None
        props = 'ids|size|content'
        res = site.api('query', prop='revisions', rvprop=props, revids='{}|{}'.format(rev.revid, rev.parentid))['query']
        if res.get('pages') is None:
            logger.info('Failed to get revision %d, revision deleted?', rev.revid)
            return

        for page in res['pages'].values():
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

            sql       : SQL Connection object
            start : datetime object
            end   : datetime object
            sites : list of sites
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

            if site_key not in sites:
                # Contribution from a wiki which is not part of this contest config
                continue

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

        if len(filters) == 1 and isinstance(filters[0], NamespaceFilter):
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
        for a in self.articles.keys():
            logger.debug(' - %s', a)

    @property
    def bytes(self):
        return np.sum([a.bytes for a in self.articles.values()])

    @property
    def newpages(self):
        return np.sum([1 for a in self.articles.values() if a.new_non_redirect])

    @property
    def words(self):
        return np.sum([a.words for a in self.articles.values()])

    @property
    def points(self):
        """ The points for all the user's articles, excluding disqualified ones """
        p = 0.
        for article_key, article in self.articles.items():
            p += article.get_points()
        return p
        #return np.sum([a.points for a in self.articles.values()])

    def analyze(self, rules):

        x = []
        y = []
        utc = pytz.utc

        # loop over articles
        for article_key, article in self.articles.items():
            # if self.contest().verbose:
            #     logger.info(article_key)
            # else:
            #     logger.info('.', newline=False)
            #log(article_key)

            # loop over revisions
            for revid, rev in article.revisions.items():

                rev.points = []

                # loop over rules
                for rule in rules:
                    logger.debug('Applying %s to %s', type(rule).__name__, revid)
                    rule.test(rev)
                    # logger.debug('Generated %.1f points', rev.points[-1])

                if not article.disqualified:

                    dt = pytz.utc.localize(datetime.fromtimestamp(rev.timestamp))
                    if self.suspended_since is None or dt < self.suspended_since:

                        if rev.get_points() > 0:
                            #print self.name, rev.timestamp, rev.get_points()
                            ts = float(unix_time(utc.localize(datetime.fromtimestamp(rev.timestamp)).astimezone(self.contest().wiki_tz)))
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

    def format_result(self):

        entries = []
        config = self.contest().config

        utc = pytz.utc

        logger.debug('Formatting results for user %s', self.name)
        # loop over articles
        for article_key, article in self.articles.items():

            brutto = article.get_points(ignore_suspension_period=True, ignore_point_deductions=True, ignore_disqualification=True)
            netto = article.get_points()

            if brutto == 0.0:

                logger.debug('    %s: skipped (0 points)', article_key)

            else:

                # loop over revisions
                revs = []
                for revid, rev in article.revisions.items():

                    if len(rev.points) > 0:
                        descr = ' + '.join(['%.1f p (%s)' % (p[0], p[2]) for p in rev.points])
                        for p in rev.point_deductions:
                            if p[0] > 0:
                                descr += ' <span style="color:red">− %.1f p (%s)</span>' % (p[0], p[1])
                            else:
                                descr += ' <span style="color:green">+ %.1f p (%s)</span>' % (-p[0], p[1])

                        dt = utc.localize(datetime.fromtimestamp(rev.timestamp))
                        dt_str = dt.astimezone(self.contest().wiki_tz).strftime(_('%A, %H:%M'))
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

        ros = '{awards}'

        suspended = ''
        if self.suspended_since is not None:
            suspended = ', ' + _('suspended since') + ' %s' % self.suspended_since.strftime(_('%A, %H:%M'))
        userprefix = self.contest().homesite.namespaces[2]
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


class Contest(object):

    def __init__(self, page, sites, homesite, sql, config, wiki_tz, server_tz, project_dir, contest_name):
        """
            page: mwclient.Page object
            sites: list
            sql: mysql Connection object
        """
        logger.info('Initializing contest [[%s]]', page.name)
        self.page = page
        self.name = self.page.name
        self.config = config
        self.homesite = homesite
        self.project_dir = project_dir
        self.contest_name = contest_name
        txt = page.text()

        self.sql = sql
        self.wiki_tz = wiki_tz
        self.server_tz = server_tz

        self.sites = sites
        self.users = [User(n, self) for n in self.extract_userlist(txt)]
        self.rules, self.filters = self.extract_rules(txt, self.config.get('catignore', ''))

        logger.info(" - %d participants", len(self.users))
        logger.info(" - %d filter(s) and %d rule(s)", len(self.filters), len(self.rules))
        logger.info(' - Open from %s to %s',
                    self.start.strftime('%F %T'),
                    self.end.strftime('%F %T'))

        # if self.startweek == self.endweek:
        #     logger.info(' - Week %d', self.startweek)
        # else:
        #     logger.info(' - Week %d–%d', self.startweek, self.endweek)

    def site_from_prefix(self, key, raise_on_error=False):
        for site in self.sites.values():
            if site.match_prefix(key):
                return site
        if raise_on_error:
            raise InvalidContestPage(_('Could not found a site matching the prefix "%(key)s"') % {
                'key': key
            })

    def resolve_page(self, value, default_ns=0):
        logger.debug('Resolving: %s', value)
        values = value.split(':')
        site = self.homesite
        ns = site.namespaces[default_ns]

        # check all prefixes
        for val in values[:-1]:
            if val == '':
                continue
            elif val in self.homesite.namespaces.values():
                # reverse namespace lookup
                ns = val  # [k for k, v in self.homesite.namespaces.items() if v == val][0]
            else:
                tmp = self.site_from_prefix(val)
                if tmp is not None:
                    site = tmp
                else:
                    raise InvalidContestPage(_('Failed to parse prefix "%(element)s" as namespace or site, from title "%(value)s"') % {
                        'element': val,
                        'value': value,
                    })

        value = values[-1]
        value = value[0].upper() + value[1:]

        value = '%s:%s' % (ns, value)
        logger.debug('proceed: %s', value)

        page = site.pages[value]
        if not page.exists:
            raise InvalidContestPage(_('Page does not exist: [[%(pagename)s]]') % {
                'pagename': site.link_to(page)
            })
        return page

    def extract_userlist(self, txt):
        lst = []
        m = re.search('==\s*' + self.config['contestPages']['participantsSection'] + '\s*==', txt)
        if not m:
            raise InvalidContestPage(_("Couldn't find the list of participants!"))
        deltakerliste = txt[m.end():]
        m = re.search('==[^=]+==', deltakerliste)
        if not m:
            raise InvalidContestPage('Fant ingen overskrift etter deltakerlisten!')
        deltakerliste = deltakerliste[:m.start()]
        for d in deltakerliste.split('\n'):
            q = re.search(r'\[\[(?:[^|\]]+):([^|\]]+)', d)
            if q:
                lst.append(q.group(1))
        return lst

    def extract_rules(self, txt, catignore_page=''):
        rules = []
        filters = []
        config = self.config

        rulecfg = config['templates']['rule']
        maxpoints = rulecfg['maxpoints']
        site_param = rulecfg['site']

        dp = TemplateEditor(txt)

        catignore_txt = ''
        if catignore_page != '':
            catignore_txt = self.homesite.pages[catignore_page].text()

        if catignore_txt == '':
            catignore = []
            logger.info('Note: catignore page is empty or does not exist')
        else:
            try:
                m = re.search(r'<pre>(.*?)</pre>', catignore_txt, flags=re.DOTALL)
                catignore = m.group(1).strip().splitlines()
            except (IndexError, KeyError):
                raise ParseError(_('Could not parse the catignore page'))

        if config['templates']['rule']['name'] not in dp.templates:
            raise InvalidContestPage(_('There are no point rules defined for this contest. Point rules are defined by {{tl|%(template)s}}.') % {'template': config['templates']['rule']['name']})

        #if not 'ukens konkurranse kriterium' in dp.templates.keys():
        #    raise InvalidContestPage('Denne konkurransen har ingen bidragskriterier. Kriterier defineres med {{tl|ukens konkurranse kriterium}}.')

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
                        raise InvalidContestPage(_('No template (second argument) given to {{tlx|%(template)s|%(firstarg)s}}') % {'template': filtercfg['name'], 'firstarg': filtercfg['template']})

                    params['templates'] = anon[2:]
                    params['aliases'] = []
                    for tp in params['templates']:
                        tplpage = self.homesite.pages['Template:' + tp]
                        if tplpage.exists:
                            params['aliases'].extend([x.page_title for x in tplpage.backlinks(filterredir='redirects')])

                    filt = TemplateFilter(**params)

                elif key == filtercfg['bytes']:
                    if len(anon) < 3:
                        raise InvalidContestPage(_('No byte limit (second argument) given to {{tlx|%(template)s|%(firstarg)s}}') % {'template': filtercfg['name'], 'firstarg': filtercfg['bytes']})
                    params['bytelimit'] = anon[2]
                    filt = ByteFilter(**params)

                elif key == filtercfg['category']:
                    if len(anon) < 3:
                        raise InvalidContestPage(_('No categories given to {{tlx|%(template)s|%(firstarg)s}}') % {'template': filtercfg['name'], 'firstarg': filtercfg['bytes']})

                    params['ignore'] = catignore
                    if templ.has_param(filtercfg['ignore']):
                        params['ignore'].extend([a.strip() for a in par[filtercfg['ignore']].split(',')])

                    params['sites'] = self.sites
                    params['categories'] = [self.resolve_page(x, default_ns=14) for x in anon[2:] if x.strip() is not '']

                    if templ.has_param(filtercfg['maxdepth']):
                        params['maxdepth'] = int(par[filtercfg['maxdepth']])
                    filt = CatFilter(**params)

                elif key == filtercfg['sparql']:
                    if not templ.has_param(filtercfg['query']):
                        raise InvalidContestPage(_('No "%(query)s" parameter given to {{tlx|%(template)s|%(firstarg)s}}') % {
                            'query': filtercfg['query'],
                            'template': filtercfg['name'],
                            'firstarg': filtercfg['sparql']
                        })
                    params['query'] = par[filtercfg['query']]
                    params['sites'] = self.sites.keys()
                    filt = SparqlFilter(**params)

                elif key == filtercfg['backlink']:
                    params['pages'] = [self.resolve_page(x) for x in anon[2:] if x.strip() is not '']
                    params['site_from_prefix'] = self.site_from_prefix
                    filt = BackLinkFilter(**params)

                elif key == filtercfg['forwardlink']:
                    params['pages'] = [self.resolve_page(x) for x in anon[2:] if x.strip() is not '']
                    params['site_from_prefix'] = self.site_from_prefix
                    filt = ForwardLinkFilter(**params)

                elif key == filtercfg['namespace']:
                    params['namespaces'] = [x.strip() for x in anon[2:]]
                    if templ.has_param(site_param):
                        params['site'] = par[site_param]
                    filt = NamespaceFilter(**params)

                elif key == filtercfg['pages']:
                    params['pages'] = [self.resolve_page(x) for x in anon[2:] if x.strip() is not '']
                    filt = PageFilter(**params)

                else:
                    raise InvalidContestPage(_('Unknown argument given to {{tl|%(template)s}}: %(argument)s') % {'template': filtercfg['name'], 'argument': key})

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
                file_prefixes = set([prefix for site in self.sites.values() for prefix in site.file_prefixes])
                params = {'key': key, 'points': anon[2], 'file_prefixes': file_prefixes}
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
                raise InvalidContestPage(_('Unkown argument given to {{tl|%(template)s}}: %(argument)s') % {'template': rulecfg['name'], 'argument': key})

        ######################## Read infobox ########################

        commonargs = config['templates']['commonargs']
        ibcfg = config['templates']['infobox']
        if ibcfg['name'] not in dp.templates:
            raise InvalidContestPage(_('This contest is missing a {{tl|%(template)s}} template.') % {'template': ibcfg['name']})

        infoboks = dp.templates[ibcfg['name']][0]
        utc = pytz.utc

        if infoboks.has_param(commonargs['year']) and infoboks.has_param(commonargs['week']):
            year = int(re.sub(r'<\!--.+?-->', r'', infoboks.parameters[commonargs['year']].value).strip())
            startweek = int(re.sub(r'<\!--.+?-->', r'', infoboks.parameters[commonargs['week']].value).strip())
            if infoboks.has_param(commonargs['week2']):
                endweek = re.sub(r'<\!--.+?-->', r'', infoboks.parameters[commonargs['week2']].value).strip()
                if endweek == '':
                    endweek = startweek
            else:
                endweek = startweek
            endweek = int(endweek)

            startweek = Week(year, startweek)
            endweek = Week(year, endweek)
            self.start = self.wiki_tz.localize(datetime.combine(startweek.monday(), dt_time(0, 0, 0)))
            self.end = self.wiki_tz.localize(datetime.combine(endweek.sunday(), dt_time(23, 59, 59)))
        elif infoboks.has_param(ibcfg['start']) and infoboks.has_param(ibcfg['end']):
            startdt = infoboks.parameters[ibcfg['start']].value
            enddt = infoboks.parameters[ibcfg['end']].value
            self.start = self.wiki_tz.localize(datetime.strptime(startdt + ' 00 00 00', '%Y-%m-%d %H %M %S'))
            self.end = self.wiki_tz.localize(datetime.strptime(enddt + ' 23 59 59', '%Y-%m-%d %H %M %S'))
        else:
            args = {'week': commonargs['week'], 'year': commonargs['year'], 'start': ibcfg['start'], 'end': ibcfg['end'], 'template': ibcfg['name']}
            raise InvalidContestPage(_('Did not find %(week)s+%(year)s or %(start)s+%(end)s in {{tl|%(templates)s}}.') % args)

        self.year = self.start.isocalendar()[0]

        self.startweek = self.start.isocalendar()[1]
        self.endweek = self.end.isocalendar()[1]
        self.month = self.start.month

        userprefix = self.homesite.namespaces[2]
        self.ledere = []
        if ibcfg['organizer'] in infoboks.parameters:
            self.ledere = re.findall(r'\[\[(?:User|%s):([^\|\]]+)' % userprefix, infoboks.parameters[ibcfg['organizer']].value, flags=re.I)
        if len(self.ledere) == 0:
            logger.warning('Found no organizers in {{tl|%s}}.', ibcfg['name'])

        awards = config['awards']
        self.prices = []
        for col in awards.keys():
            if infoboks.has_param(col):
                r = re.sub(r'<\!--.+?-->', r'', infoboks.parameters[col].value.strip())  # strip comments, then whitespace
                if r != '':
                    r = r.lower().replace('&nbsp;', ' ').split()[0]
                    #print col,r
                    if r == ibcfg['winner']:
                        self.prices.append([col, 'winner', 0])
                    elif r != '':
                        try:
                            self.prices.append([col, 'pointlimit', int(r)])
                        except ValueError:
                            pass
                            #raise InvalidContestPage('Klarte ikke tolke verdien til parameteren %s gitt til {{tl|infoboks ukens konkurranse}}.' % col)

        if not 'winner' in [r[1] for r in self.prices]:
            winnerawards = ', '.join(['{{para|%s|vinner}}' % k for k, v in awards.items() if 'winner' in v])
            #raise InvalidContestPage(_('Found no winner award in {{tl|%(template)s}}. Winner award is set by one of the following: %(awards)s.') % {'template': ibcfg['name'], 'awards': winnerawards})
            logger.warning('Found no winner award in {{tl|%s}}. Winner award is set by one of the following: %s.', ibcfg['name'], winnerawards)

        self.prices.sort(key=lambda x: x[2], reverse=True)

        ####################### Check if contest is in DB yet ##################

        cur = self.sql.cursor()
        cur.execute('SELECT contest_id FROM contests WHERE site=%s AND name=%s', [self.homesite.key, self.name])
        rows = cur.fetchall()
        if len(rows) == 0:
            cur.execute('INSERT INTO contests (site, name, start_date, end_date) VALUES (%s,%s,%s,%s)', [self.homesite.key, self.name, self.start.strftime('%F %T'), self.end.strftime('%F %T')])
            self.sql.commit()
        cur.close()

        ######################## Read disqualifications ########################

        sucfg = self.config['templates']['suspended']
        if sucfg['name'] in dp.templates:
            for templ in dp.templates[sucfg['name']]:
                uname = templ.parameters[1].value
                try:
                    sdate = self.wiki_tz.localize(datetime.strptime(templ.parameters[2].value, '%Y-%m-%d %H:%M'))
                except ValueError:
                    raise InvalidContestPage(_("Couldn't parse the date given to the {{tl|%(template)s}} template.") % sucfg['name'])

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
                    #raise InvalidContestPage('Fant ikke brukeren %s gitt til {{tl|UK bruker suspendert}}-malen.' % uname)

        dicfg = self.config['templates']['disqualified']
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
                            raise InvalidContestPage(_('Could not find the user %(user)s given to the {{tl|%(template)s}} template.') % {'user': uname, 'template': dicfg['name']})

        pocfg = self.config['templates']['penalty']
        if pocfg['name'] in dp.templates:
            for templ in dp.templates[pocfg['name']]:
                uname = templ.parameters[1].value
                revid = int(templ.parameters[2].value)
                site_key = ''
                if 'site' in templ.parameters:
                    site_key = templ.parameters['site'].value

                site = self.site_from_prefix(site_key)
                if site is None:
                    raise InvalidContestPage(_('Failed to parse the %(template)s template: Did not find a site matching the site prefix %(prefix)s') % {
                        'template': pocfg['name'],
                        'prefix': site_key,
                    })

                points = float(templ.parameters[3].value.replace(',', '.'))
                reason = templ.parameters[4].value
                ufound = False
                logger.info('Point deduction: %d points to %s for revision %s:%s. Reason: %s', points, uname, site.key, revid, reason)
                for u in self.users:
                    if u.name == uname:
                        u.point_deductions.append({
                            'site': site.key,
                            'revid': revid,
                            'points': points,
                            'reason': reason,
                        })
                        ufound = True
                if not ufound:
                    raise InvalidContestPage(_("Couldn't find the user %(user)s given to the {{tl|%(template)s}} template.") % {
                        'user': uname,
                        'template': pocfg['name'],
                    })

        pocfg = self.config['templates']['bonus']
        if pocfg['name'] in dp.templates:
            for templ in dp.templates[pocfg['name']]:
                uname = templ.parameters[1].value
                revid = int(templ.parameters[2].value)
                site_key = ''
                if 'site' in templ.parameters:
                    site_key = templ.parameters['site'].value

                site = None
                for s in self.sites.values():
                    if s.match_prefix(site_key):
                        site = s
                        break

                if site is None:
                    raise InvalidContestPage(_('Failed to parse the %(template)s template: Did not find a site matching the site prefix %(prefix)s') % {
                        'template': pocfg['name'],
                        'prefix': site_key,
                    })

                points = float(templ.parameters[3].value.replace(',', '.'))
                reason = templ.parameters[4].value
                ufound = False
                logger.info('Point addition: %d points to %s for revision %s:%s. Reason: %s', points, uname, site.key, revid, reason)
                for u in self.users:
                    if u.name == uname:
                        u.point_deductions.append({
                            'site': site.key,
                            'revid': revid,
                            'points': -points,
                            'reason': reason
                        })
                        ufound = True
                if not ufound:
                    raise InvalidContestPage(_("Couldn't find the user %(user)s given to the {{tl|%(template)s}} template.") % {
                        'user': uname,
                        'template': pocfg['name'],
                    })

        # try:
        #     infoboks = dp.templates['infoboks ukens konkurranse'][0]
        # except:
        #     raise InvalidContestPage('Klarte ikke å tolke innholdet i {{tl|infoboks ukens konkurranse}}-malen.')

        return rules, filters

    def prepare_plotdata(self, results):
        plotdata = []
        for result in results:
            tmp = {'name': result['name'], 'values': []}
            for point in result['plotdata']:
                tmp['values'].append({'x': point[0], 'y': point[1]})
            plotdata.append(tmp)

        datafile = os.path.join(self.project_dir, 'plots', '%s.json' % self.contest_name)
        with open(datafile, 'w+') as f:
            json.dump(plotdata, f)

        return plotdata

    def plot(self, plotdata):
        import matplotlib.pyplot as plt

        w = 20 / 2.54
        goldenratio = 1.61803399
        h = w / goldenratio
        fig = plt.figure(figsize=(w, h))

        ax = fig.add_subplot(1, 1, 1, frame_on=True)
        # ax.grid(True, which='major', color='gray', alpha=0.5)
        fig.subplots_adjust(left=0.10, bottom=0.09, right=0.65, top=0.94)

        t0 = float(unix_time(self.start))

        datediff = self.end - self.start
        ndays = datediff.days + 1

        xt = t0 + np.arange(ndays + 1) * 86400
        xt_mid = t0 + 43200 + np.arange(ndays) * 86400

        now = float(unix_time(self.server_tz.localize(datetime.now()).astimezone(pytz.utc)))

        yall = []
        cnt = 0

        for result in plotdata:
            x = [t['x'] for t in result['values']]
            y = [t['y'] for t in result['values']]

            if len(x) > 0:
                cnt += 1
                yall.extend(y)
                x.insert(0, xt[0])
                y.insert(0, 0)
                if now < xt[-1]:
                    x.append(now)
                    y.append(y[-1])
                else:
                    x.append(xt[-1])
                    y.append(y[-1])
                l = ax.plot(x, y, linewidth=1.2, label=result['name'])  # markerfacecolor='#FF8C00', markeredgecolor='#888888', label = u['name'])
                c = l[0].get_color()
                #ax.plot(x[1:-1], y[1:-1], marker='.', markersize=4, markerfacecolor=c, markeredgecolor=c, linewidth=0., alpha=0.5)  # markerfacecolor='#FF8C00', markeredgecolor='#888888', label = u['name'])
                if cnt >= 15:
                    break

        if now < xt[-1]:   # showing vertical line indicating when the plot was updated
            ax.axvline(now, color='black', alpha=0.5)

        abday = [calendar.day_abbr[x] for x in [0, 1, 2, 3, 4, 5, 6]]

        x_ticks_major_size = 5
        x_ticks_minor_size = 0

        if ndays == 7:
            # Tick marker every midnight
            ax.set_xticks(xt, minor=False)
            ax.set_xticklabels([], minor=False)

            # Tick labels at the middle of every day
            ax.set_xticks(xt_mid, minor=True)
            ax.set_xticklabels(abday, minor=True)
        elif ndays == 14:
            # Tick marker every midnight
            ax.set_xticks(xt, minor=False)
            ax.set_xticklabels([], minor=False)

            # Tick labels at the middle of every day
            ax.set_xticks(xt_mid, minor=True)
            ax.set_xticklabels([abday[0], '', abday[2], '', abday[4], '', abday[6], '', abday[1], '', abday[3], '', abday[5], ''], minor=True)
        elif ndays > 14:

            # Tick marker every week
            x_ticks_major_labels = np.arange(0, ndays + 1, 7)
            x_ticks_major = t0 + x_ticks_major_labels * 86400
            ax.set_xticks(x_ticks_major, minor=False)
            ax.set_xticklabels(x_ticks_major_labels, minor=False)

            # Tick every day
            x_ticks_minor = t0 + np.arange(ndays + 1) * 86400
            ax.set_xticks(x_ticks_minor, minor=True)
            x_ticks_minor_size = 3

            # ax.set_xticklabels(['1', '', '', '', '5', '', '', '', '', '10', '', '', '', '', '15', '', '', '', '', '20', '', '', '', '', '25', '', '', '', '', '30'], minor=True)
        # elif ndays == 31:
        #     ax.set_xticklabels(['1', '', '', '', '5', '', '', '', '', '10', '', '', '', '', '15', '', '', '', '', '20', '', '', '', '', '25', '', '', '', '', '', '31'], minor=True)



        for i in range(1, ndays, 2):
            ax.axvspan(xt[i], xt[i + 1], facecolor='#000099', linewidth=0., alpha=0.03)

        for i in range(0, ndays, 2):
            ax.axvspan(xt[i], xt[i + 1], facecolor='#000099', linewidth=0., alpha=0.07)

        for line in ax.xaxis.get_ticklines(minor=False):
            line.set_markersize(x_ticks_major_size)

        for line in ax.xaxis.get_ticklines(minor=True):
            line.set_markersize(x_ticks_minor_size)

        for line in ax.yaxis.get_ticklines(minor=False):
            line.set_markersize(x_ticks_major_size)

        if len(yall) > 0:
            ax.set_xlim(t0, xt[-1])
            ax.set_ylim(0, 1.05 * np.max(yall))

            ax.set_xlabel(_('Day'))
            ax.set_ylabel(_('Points'))

            now = self.server_tz.localize(datetime.now())
            now2 = now.astimezone(self.wiki_tz).strftime(_('%e. %B %Y, %H:%M'))
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
            figname = os.path.join(self.project_dir, 'plots', self.config['plot']['figname'] % {'year': self.year, 'week': self.startweek, 'month': self.month})
            plt.savefig(figname, dpi=200)
            logger.info('Wrote plot: %s', figname)

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
            'month': self.month,
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
        flow_enabled = ('enabled' in list(flinfo['query']['pages'].values())[0]['flowinfo']['flow'])

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


    def deliver_prices(self, results, simulate=False):
        config = self.config
        heading = self.format_heading()

        cur = self.sql.cursor()
        cur.execute('SELECT contest_id FROM contests WHERE site=%s AND name=%s', [self.homesite.key, self.name])
        contest_id = cur.fetchall()[0][0]

        logger.info('Delivering prices for contest %d' % (contest_id,))

        # self.sql.commit()
        # cur.close()

        for i, result in enumerate(results):

            prizefound = False
            if i == 0:
                mld = ''
                for r in self.prices:
                    if r[1] == 'winner':
                        prizefound = True
                        mld = self.format_msg('winner_template', r[0])
                        break
                for r in self.prices:
                    if r[1] == 'pointlimit' and result['points'] >= r[2]:
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
                    if r[1] == 'pointlimit' and result['points'] >= r[2]:
                        prizefound = True
                        mld = self.format_msg('participant_template', r[0])
                        break
                mld += '}}\n'

            now = self.server_tz.localize(datetime.now())
            yearweek = now.astimezone(self.wiki_tz).strftime('%Y-%V')
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
                    cur.execute('SELECT prize_id FROM prizes WHERE contest_id=%s AND site=%s AND user=%s', [contest_id, self.homesite.key, result['name']])
                    rows = cur.fetchall()
                    if len(rows) == 0:
                        self.deliver_message(result['name'], heading, mld, sig)
                        cur.execute('INSERT INTO prizes (contest_id, site, user, timestamp) VALUES (%s,%s,%s, NOW())', [contest_id, self.homesite.key, result['name']])
                        self.sql.commit()
            else:
                logger.info('No price for %s', result['name'])

    def deliver_leader_notification(self):
        heading = self.format_heading()
        args = {
            'prefix': self.homesite.site['server'] + self.homesite.site['script'],
            'page': self.config['awardstatus']['pagename'],
            'title': urllib.parse.quote(self.config['awardstatus']['send'])
        }
        link = '%(prefix)s?title=%(page)s&action=edit&section=new&preload=%(page)s/Preload&preloadtitle=%(title)s' % args
        usertalkprefix = self.homesite.namespaces[3]
        oaward = ''
        for key, award in self.config['awards'].items():
            if 'organizer' in award:
                oaward = key
        if oaward == '':
            raise Exception('No organizer award found in config')
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
            mld += _('Now you must check if the results look ok. If there are error messages at the bottom of the [[%(page)s|contest page]], you should check that the related contributions have been awarded the correct number of points. Also check if there are comments or complaints on the discussion page. If everything looks fine, [%(link)s click here] (and save) to indicate that I can send out the awards at first occasion.') % {'page': self.name, 'link': link}
            sig = _('Thanks, ~~~~')

            logger.info('Leverer arrangørmelding for %s', self.name )
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
                d = [self.homesite.key, self.name, u.name, 'suspension', '']
                cur.execute('SELECT id FROM notifications WHERE site=%s AND contest=%s AND user=%s AND class=%s AND args=%s', d)
                if len(cur.fetchall()) == 0:
                    msgs.append('Du er inntil videre suspendert fra konkurransen med virkning fra %s. Dette innebærer at dine bidrag gjort etter dette tidspunkt ikke teller i konkurransen, men alle bidrag blir registrert og skulle suspenderingen oppheves i løpet av konkurranseperioden vil også bidrag gjort i suspenderingsperioden telle med. Vi oppfordrer deg derfor til å arbeide med problemene som førte til suspenderingen slik at den kan oppheves.' % u.suspended_since.strftime(_('%e. %B %Y, %H:%M')))
                    if not simulate:
                        cur.execute('INSERT INTO notifications (site, contest, user, class, args) VALUES (%s,%s,%s,%s,%s)', d)
            discs = []
            for article_key, article in u.articles.items():
                if article.disqualified:
                    d = [self.homesite.key, self.name, u.name, 'disqualified', article_key]
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

    def run(self, simulate=False, output=''):
        config = self.config

        if not self.page.exists:
            logger.error('Contest page [[%s]] does not exist! Exiting', self.page.name)
            return

        # Loop over users

        narticles = 0
        nbytes = 0
        nwords = 0
        nnewpages = 0

        # extraargs = {'namespace': 0}
        extraargs = {}
        host_filter = None
        for f in self.filters:
            if isinstance(f, NamespaceFilter):
                extraargs['namespace'] = '|'.join(f.namespaces)
                host_filter = f.site

        article_errors = {}
        results = []

        while True:
            if len(self.users) == 0:
                break
            user = self.users.pop()

            logger.info('=== User:%s ===', user.name)

            # First read contributions from db
            user.add_contribs_from_db(self.sql, self.start, self.end, self.sites)

            # Then fill in new contributions from wiki
            for site in self.sites.values():

                if host_filter is None or site.host == host_filter:
                    user.add_contribs_from_wiki(site, self.start, self.end, fulltext=True, **extraargs)

            # And update db
            user.save_contribs_to_db(self.sql)

            try:

                # Filter out relevant articles
                user.filter(self.filters)

                # And calculate points
                logger.info('Calculating points')
                tp0 = time.time()
                user.analyze(self.rules)
                tp1 = time.time()
                logger.info('%s: %.f points (calculated in %.1f secs)', user.name, user.points, tp1 - tp0)

                narticles += len(user.articles)
                nbytes += user.bytes
                nwords += user.words
                nnewpages += user.newpages
                tp2 = time.time()
                logger.info('Wordcount done in %.1f secs', tp2 - tp1)

                for article in user.articles.values():
                    k = article.site().key + ':' + article.name
                    if len(article.errors) > 0:
                        article_errors[k] = article.errors
                    for rev in article.revisions.values():
                        if len(rev.errors) > 0:
                            if k in article_errors:
                                article_errors[k].extend(rev.errors)
                            else:
                                article_errors[k] = rev.errors

                results.append({
                    'name': user.name,
                    'points': user.points,
                    'bytes': int(user.bytes),
                    'newpages': int(user.newpages),
                    'result': user.format_result(),
                    'plotdata': user.plotdata,
                })

            except InvalidContestPage as e:
                err = "\n* '''%s'''" % e.msg
                out = '\n{{%s | error | %s }}' % (config['templates']['botinfo'], err)
                if simulate:
                    logger.error(out)
                else:
                    self.page.save('dummy', summary=_('UKBot encountered a problem'), appendtext=out)
                raise

            del user

        # Sort users by points

        logger.info('Sorting contributions and preparing contest page')

        results.sort(key=lambda x: x['points'], reverse=True)

        # Make outpage

        out = ''
        #out += '[[File:Nowp Ukens konkurranse %s.svg|thumb|400px|Resultater (oppdateres normalt hver natt i halv ett-tiden, viser kun de ti med høyest poengsum)]]\n' % self.start.strftime('%Y-%W')

        sammen = ''
        if 'status' in config['templates']:
            sammen = '{{%s' % config['templates']['status']

            ft = [type(f) for f in self.filters]
            rt = [type(r) for r in self.rules]

            #if StubFilter in ft:
            #    sammen += '|avstubbet=%d' % narticles

            trn = 0
            for f in self.rules:
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

        now = self.server_tz.localize(datetime.now())
        if kstatus == 'ending':
            # Konkurransen er nå avsluttet – takk til alle som deltok! Rosetter vil bli delt ut så snart konkurransearrangøren(e) har sjekket resultatene.
            out += "''" + _('This contest is closed – thanks to everyone who participated! Awards will be sent out as soon as the contest organizer has checked the results.') + "''\n\n"
        elif kstatus == 'closing':
            out += "''" + _('This contest is closed – thanks to everyone who participated!') + "''\n\n"
        else:
            oargs = {
                'lastupdate': now.astimezone(self.wiki_tz).strftime(_('%e. %B %Y, %H:%M')),
                'startdate': self.start.strftime(_('%e. %B %Y, %H:%M')),
                'enddate': self.end.strftime(_('%e. %B %Y, %H:%M'))
            }
            out += "''" + _('Last updated %(lastupdate)s. The contest is open from %(startdate)s to %(enddate)s.') % oargs + "''\n\n"

        for i, result in enumerate(results):
            awards = ''
            if kstatus == 'closing':
                if i == 0:
                    for price in self.prices:
                        if price[1] == 'winner':
                            awards += '[[File:%s|20px]] ' % config['awards'][price[0]]['file']
                            break
                for price in self.prices:
                    if price[1] == 'pointlimit' and result['points'] >= price[2]:
                        awards += '[[File:%s|20px]] ' % config['awards'][price[0]]['file']
                        break
            out += result['result'].replace('{awards}', awards)

        errors = []
        for art, err in article_errors.items():
            if len(err) > 8:
                err = err[:8]
                err.append('(...)')
            errors.append('\n* ' + _('UKBot encountered the following problems with the article [[:%s]]') % art + ''.join(['\n** %s' % e for e in err]))

        for site in self.sites.values():
            for error in site.errors:
                errors.append('\n* %s' % error)

        if len(errors) == 0:
            out += '{{%s | ok | %s }}' % (config['templates']['botinfo'], now.astimezone(self.wiki_tz).strftime('%F %T'))
        else:
            out += '{{%s | 1=note | 2=%s | 3=%s }}' % (config['templates']['botinfo'], now.astimezone(self.wiki_tz).strftime('%F %T'), ''.join(errors))

        out += '\n' + config['contestPages']['footer'] % {'year': self.year} + '\n'

        ib = config['templates']['infobox']

        if not simulate:
            txt = self.page.text()
            tp = TemplateEditor(txt)
            #print "---"
            #print sammen
            #print "---"
            if sammen != '':
                tp.templates[ib['name']][0].parameters[ib['status']] = sammen
            txt = tp.wikitext()
            secstart = -1
            secend = -1

            # Check if <!-- Begin:ResultsSection --> exists first
            try:
                trs1 = next(re.finditer('<!--\s*Begin:ResultsSection\s*-->', txt, re.I))
                trs2 = next(re.finditer('<!--\s*End:ResultsSection\s*-->', txt, re.I))
                secstart = trs1.end()
                secend = trs2.start()

            except StopIteration:
                if 'resultsSection' not in config['contestPages']:
                    raise InvalidContestPage(_('Results markers %(start_marker)s and %(end_marker)s not found') % {
                        'start_marker': '<!-- Begin:ResultsSection -->', 
                        'end_marker': '<!-- End:ResultsSection -->',
                    })
                for s in re.finditer(r'^[\s]*==([^=]+)==[\s]*\n', txt, flags=re.M):
                    if s.group(1).strip() == config['contestPages']['resultsSection']:
                        secstart = s.end()
                    elif secstart != -1:
                        secend = s.start()
                        break
            if secstart == -1:
                raise InvalidContestPage(_('No "%(section_name)s" section found.') % {
                    'section_name': config['contestPages']['resultsSection'], 
                })
            if secend == -1:
                txt = txt[:secstart] + out
            else:
                txt = txt[:secstart] + out + txt[secend:]

            logger.info('Updating wiki')
            if kstatus == 'ending':
                self.page.save(txt, summary=_('Updating with final results, the contest is now closed.'))
            elif kstatus == 'closing':
                self.page.save(txt, summary=_('Checking results and handing out awards'))
            else:
                self.page.save(txt, summary=_('Updating'))

        if output != '':
            logger.info("Writing output to file")
            f = codecs.open(output, 'w', 'utf-8')
            f.write(out)
            f.close()

        if kstatus == 'ending':
            logger.info('Ending contest')
            if not simulate:
                self.deliver_leader_notification()

                aws = config['awardstatus']
                page = self.homesite.pages[aws['pagename']]
                page.save(text=aws['wait'], summary=aws['wait'], bot=True)

                cur = self.sql.cursor()
                cur.execute('UPDATE contests SET ended=1 WHERE site=%s AND name=%s', [self.homesite.key, self.name])
                self.sql.commit()
                cur.close()

        if kstatus == 'closing':
            logger.info('Delivering prices')

            self.deliver_prices(results, simulate)

            cur = self.sql.cursor()

            for result in results:
                arg = [self.homesite.key, self.name, result['name'], int(self.startweek), result['points'], result['bytes'], result['newpages'], 0]
                if self.startweek != self.endweek:
                    arg[-1] = int(self.endweek)
                #print arg
                if not simulate:
                    cur.execute(u"INSERT INTO users (site, contest, user, week, points, bytes, newpages, week2) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", arg)

            if not simulate:
                cur.execute('UPDATE contests SET closed=1 WHERE site=%s AND name=%s', [self.homesite.key, self.name])
                self.sql.commit()

            cur.close()

            aws = config['awardstatus']
            page = self.homesite.pages[aws['pagename']]
            page.save(text=aws['sent'], summary=aws['sent'], bot=True)

            # if not simulate:
            #
            # Skip for now: not Flow compatible
            #     self.deliver_receipt_to_leaders()

            logger.info('Cleaning database')
            if not simulate:
                self.delete_contribs_from_db()

        # Notify users about issues

        # self.deliver_warnings(simulate=simulate)

        # Update WP:UK

        if 'redirect' in config['pages']:
            if re.match('^' + config['pages']['base'], self.name) and not simulate and kstatus == 'normal':
                page = self.homesite.pages[config['pages']['redirect']]
                txt = _('#REDIRECT [[%s]]') % self.name
                if page.text() != txt:
                    if not simulate:
                        page.save(txt, summary=_('Redirecting to %s') % self.name)

        # Update Wikipedia:Portal/Oppslagstavle

        if 'noticeboard' in config:
            boardname = config['noticeboard']['name']
            boardtpl = config['noticeboard']['template']
            commonargs = config['templates']['commonargs']
            tplname = boardtpl['name']
            oppslagstavle = self.homesite.pages[boardname]
            txt = oppslagstavle.text()

            dp = TemplateEditor(txt)
            ntempl = len(dp.templates[tplname])
            if ntempl != 1:
                raise Exception('Feil: Fant %d %s-maler i %s' % (ntempl, tplname, boardname))

            tpl = dp.templates[tplname][0]
            now2 = now.astimezone(self.wiki_tz)
            if int(tpl.parameters['uke']) != int(now2.strftime('%V')):
                logger.info('Updating noticeboard: %s', boardname)
                tpllist = config['templates']['contestlist']
                commonargs = config['templates']['commonargs']
                tema = self.homesite.api('parse', text='{{subst:%s|%s=%s}}' % (tpllist['name'], commonargs['week'], now2.strftime('%Y-%V')), pst=1, onlypst=1)['parse']['text']['*']
                tpl.parameters[1] = tema
                tpl.parameters[boardtpl['date']] = now2.strftime('%e. %h')
                tpl.parameters[commonargs['year']] = now2.isocalendar()[0]
                tpl.parameters[commonargs['week']] = now2.isocalendar()[1]
                txt2 = dp.wikitext()
                if txt != txt2:
                    if not simulate:
                        oppslagstavle.save(txt2, summary=_('The weekly contest is: %(link)s') % {'link': tema})

        # Make a nice plot

        if 'plot' in config:
            plotdata = self.prepare_plotdata(results)
            self.plot(plotdata)

    def uploadplot(self, simulate=False, output=''):
        if not self.page.exists:
            logger.error('Contest page [[%s]] does not exist! Exiting', self.page.name)
            return

        if not 'plot' in self.config:
            return

        figname = self.config['plot']['figname'] % {
            'year': self.year,
            'week': self.startweek,
            'month': self.month,
        }
        remote_filename = figname.replace(' ', '_')
        local_filename = os.path.join(self.project_dir, 'plots', figname)

        if not os.path.isfile(local_filename):
            logger.error('File "%s" was not found', local_filename)
            sys.exit(1)

        weeks = '%d' % self.startweek
        if self.startweek != self.endweek:
            weeks += '-%s' % self.endweek

        pagetext = self.config['plot']['description'] % {
            'pagename': self.name,
            'week': weeks,
            'year': self.year,
            'month': self.month,
            'start': self.start.strftime('%F')
        }

        logger.info('Uploading: %s', figname)
        commons = mwclient.Site('commons.wikimedia.org', **self.config['account'])
        file_page = commons.pages['File:' + remote_filename]

        if simulate:
            return

        with open(local_filename.encode('utf-8'), 'rb') as file_buf:
            if not file_page.exists:
                logger.info('Adding plot')
                res = commons.upload(file_buf, remote_filename,
                                     comment='Bot: Uploading new plot',
                                     description=pagetext,
                                     ignore=True)
                logger.info(res)
            else:
                logger.info('Updating plot')
                res = commons.upload(file_buf, remote_filename,
                                     comment='Bot: Updating plot',
                                     ignore=True)
                logger.info(res)


def get_contest_page_titles(sql, homesite, config, wiki_tz, server_tz):
    cursor = sql.cursor()
    contests = set()

    # 1) Check if there is a contest to close

    cursor.execute('SELECT name FROM contests WHERE site=%s AND name LIKE %s AND ended=1 AND closed=0 LIMIT 1', [
        homesite.key,
        config['pages']['base'] + '%',
    ])
    closing_contests = cursor.fetchall()
    if len(closing_contests) != 0:
        page_title = closing_contests[0][0]
        award_statuspage = homesite.pages[config['awardstatus']['pagename']]
        if award_statuspage.exists:
            lastrev = award_statuspage.revisions(prop='user|comment').next()
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
    now_w = now.astimezone(wiki_tz)
    now_s = now_w.strftime('%F %T')
    cursor.execute('SELECT name FROM contests WHERE site=%s AND name LIKE %s AND ended=0 AND closed=0 AND end_date < %s LIMIT 1', [
        homesite.key,
        config['pages']['base'] + '%',
        now_s,
    ])
    ending_contests = cursor.fetchall()
    if len(ending_contests) != 0:
        page_title = ending_contests[0][0]
        logger.info('Contest [[%s]] just ended', page_title)
        contests.add(page_title)
        yield ('ending', page_title)

    # 3) Get contest page from current date
    if config['pages'].get('default') is not None:
        page_title = config['pages']['default']
        # subtract one hour, so we close last week's contest right after midnight
        # w = Week.withdate((now - timedelta(hours=1)).astimezone(wiki_tz).date())
        if 'week' in page_title:
            w = Week.withdate(now_w.date())
            page_title = page_title % { 'year': w.year, 'week': w.week }
        else:
            page_title = page_title % { 'year': now_w.year, 'month': now_w.month }
        #strftime(page_title.encode('utf-8'))
        if page_title not in contests:
            contests.add(page_title)
            yield ('normal', page_title)

    if config['pages'].get('active_contest_category') is not None:
        for page in homesite.categories['Artikkelkonkurranser'].members(namespace=4):
            if page.name not in contests:
                contests.add(page.name)
                yield ('normal', page.name)

    cursor.close()


def get_contest_pages(sql, homesite, config, wiki_tz, server_tz, page_title=None):

    if page_title is not None:
        pages = [('normal', page_title)]
    else:
        pages = get_contest_page_titles(sql, homesite, config, wiki_tz, server_tz)


    for p in pages:
        page = homesite.pages[p[1]]
        if not page.exists:
            log.warning('Page does not exist: %s', p[1])
            continue
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
            if isinstance(col, bytearray):
                return col.decode('utf-8')
            elif isinstance(col, bytes):
                return col.decode('utf-8')
            return col

        return[to_unicode(col) for col in row]


class SQL(object):

    def __init__(self, config):
        self.config = config
        self.open_conn()

    def open_conn(self):
        self.conn = mysql.connector.connect(converter_class=MyConverter, **self.config)

    def cursor(self, **kwargs):
        try:
            return self.conn.cursor(**kwargs)
        except mysql.connector.errors.OperationalError:
            # Seems like this can happen if the db connection times out
            self.open_conn()
            return self.conn.cursor(**kwargs)

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()


def init_sites(config):

    if 'ignore' not in config:
        config['ignore'] = []

    # Configure home site (where the contests live)
    host = config['homesite']
    homesite = Site(host, prefixes=[''], **config['account'])

    assert homesite.logged_in

    iwmap = homesite.interwikimap

    # Connect to DB
    sql = SQL(config['db'])
    logger.debug('Connected to database')

    sites = {homesite.host: homesite}
    if 'othersites' in config:
        for host in config['othersites']:
            prefixes = [k for k, v in iwmap.items() if v == host]
            sites[host] = Site(host, prefixes=prefixes, **config['account'])

    for site in sites.values():
        msg = site.get_revertpage_regexp()
        if msg != '':
            logger.debug('Revert page regexp: %s', msg)
            config['ignore'].append(msg)

    return homesite, sites, sql


if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='The UKBot')
    parser.add_argument('--page', required=False, help='Name of the contest page to work with')
    parser.add_argument('--simulate', action='store_true', default=False, help='Do not write results to wiki')
    parser.add_argument('--output', nargs='?', default='', help='Write results to file')
    parser.add_argument('--log', nargs='?', default='', help='Log file')
    parser.add_argument('--verbose', action='store_true', default=False, help='More verbose logging')
    parser.add_argument('--close', action='store_true', help='Close contest')
    parser.add_argument('--contest', help='Contest name')
    parser.add_argument('--action', nargs='?', default='', help='"uploadplot" or "run"')
    args = parser.parse_args()

    if args.verbose:
        syslog.setLevel(logging.DEBUG)
    else:
        syslog.setLevel(logging.INFO)

    if args.log != '':
        ukcommon.logfile = open(args.log, 'a')

    project_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    contest = args.contest
    config_file = os.path.join(project_dir, 'config', 'config.%s.yml' % contest)
    if not os.path.isfile(config_file):
        logger.error('Config file not found: %s', config_file)
        sys.exit(1)

    config = yaml.load(open(config_file, 'r', encoding='utf-8'))
    # rollbar.init(config['rollbar_token'], 'production')
    wiki_tz = pytz.timezone(config['wiki_timezone'])
    server_tz = pytz.timezone(config['server_timezone'])

    Localization().init(config['locale'], project_dir)

    mainstart = server_tz.localize(datetime.now())
    mainstart_s = time.time()

    logger.info('UKBot starting at %s (server time), %s (wiki time)',
                mainstart.strftime('%F %T'),
                mainstart.astimezone(wiki_tz).strftime('%F %T'))
    logger.info('Running on %s %s %s', *platform.linux_distribution())

    status_template = config['templates']['botinfo']

    homesite, sites, sql = init_sites(config)

    # Determine what to work with
    active_contests = list(get_contest_pages(sql, homesite, config, wiki_tz, server_tz, args.page))

    logger.info('Number of active contests: %d', len(active_contests))
    for kstatus, contest_page in active_contests:
        try:
            contest = Contest(contest_page,
                              sites=sites,
                              homesite=homesite,
                              sql=sql,
                              config=config,
                              wiki_tz=wiki_tz,
                              server_tz=server_tz,
                              project_dir=project_dir,
                              contest_name=contest)
        except InvalidContestPage as e:
            if args.simulate:
                logger.error(e.msg)
                sys.exit(1)
            
            error_msg = "\n* '''%s'''" % e.msg

            te = TemplateEditor(contest_page.text())
            if status_template in te.templates:
                te.templates[status_template][0].parameters[1] = 'error'
                te.templates[status_template][0].parameters[2] = error_msg
                contest_page.save(te.wikitext(), summary=_('UKBot encountered a problem'))
            else:
                out = '\n{{%s | error | %s }}' % (config['templates']['botinfo'], error_msg)
                contest_page.save('dummy', summary=_('UKBot encountered a problem'), appendtext=out)
            raise

        if args.action == 'uploadplot':
            contest.uploadplot(args.simulate, args.output)
        elif args.action == 'plot':
            datafile = os.path.join(contest.project_dir, 'plots', '%s.json' % contest.contest_name)
            plotdata = json.load(open(datafile, 'r'))
            contest.plot(plotdata)
        else:
            contest.run(args.simulate, args.output)

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
