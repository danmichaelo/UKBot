# encoding=utf-8
# vim: fenc=utf-8 et sw=4 ts=4 sts=4 ai
import sys
import re
from copy import copy
from odict import odict
import logging
import json
import time
import urllib
import requests
from mwtemplates.templateeditor2 import TemplateParseError

from .common import t, _, InvalidContestPage

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class CategoryLoopError(Exception):
    """Raised when a category loop is found."""
    def __init__(self, catpath):
        """
        Args:
            catpath -- category path followed while getting lost in the loop
        """
        self.catpath = catpath
        self.msg = 'Entered a category loop'


class Filter(object):

    def __init__(self, sites):
        """
        Args:
            sites (SiteManager): References to the sites part of this contest
        """
        self.sites = sites
        self.page_keys = set()

    @classmethod
    def make(cls, tpl, **kwargs):
        return cls(tpl.sites)

    def test_page(self, page):
        """
        Return True if the page matches the current filter, False otherwise.
        """
        return page.key in self.page_keys

    def filter(self, articles):
        out = odict()
        for article_key, article in articles.items():
            if self.test_page(article):
                out[article_key] = article
        logger.info(' - %s: Articles reduced from %d to %d',
                    type(self).__name__, len(articles), len(out))
        return out

#class StubFilter(Filter):
#    """ Filters articles that was stubs, but is no more """

#    def __init__(self):
#        Filter.__init__(self)

#    def is_stub(self, text):
#        """ Checks if a given text is a stub """

#        m = re.search(r'{{[^}]*(?:stubb|spire)[^}]*}}', text, re.IGNORECASE)
#        if m:
#            if self.verbose:
#                log(" >> %s " % m.group(0), newline = False)
#            return True
#        return False

    #def filter(self, articles):

    #    out = odict()
    #    for article_key, article in articles.items():

    #        firstrevid = article.revisions.firstkey()
    #        lastrevid = article.revisions.lastkey()

    #        firstrev = article.revisions[firstrevid]
    #        lastrev = article.revisions[lastrevid]

    #        try:

    #            # skip pages that are definitely not stubs to avoid timeconsuming parsing
    #            if article.new is False and article.redirect is False and len(firstrev.parenttext) < 20000:

    #                # Check if first revision is a stub
    #                if self.is_stub(firstrev.parenttext):

    #                    # Check if last revision is a stub
    #                    if not self.is_stub(lastrev.text):

    #                        out[article_key] = article

    #                    if self.verbose:
    #                        log('')

            #except DanmicholoParseError as e:
            #    log(" >> DanmicholoParser failed to parse " + article_key)
            #    parentid = firstrev.parentid
            #    args = { 'article': article_key, 'prevrev': firstrev.parentid, 'rev': lastrev.revid, 'error': e.msg }
            #    article.site().errors.append(_('Could not analyze the article %(article)s because one of the revisions %(prevrev)d or %(rev)d could not be parsed: %(error)s') % args)

    #    log("  [+] Applying stub filter: %d -> %d" % (len(articles), len(out)))

    #    return out


class TemplateFilter(Filter):
    """ Filters articles that had any of a given set of templates (or their aliases) at a point"""

    @classmethod
    def make(cls, tpl, **kwargs):
        if len(tpl.anon_params) < 3:
            raise RuntimeError(_('Too few arguments given to this template.'))

        params = {
            'sites': tpl.sites,
            'templates': tpl.anon_params[2:],
        }

        return cls(**params)

    def __init__(self, sites, templates, include_aliases=True):
        """
        The TemplateFilter keeps pages that had any of a given set of templates
        (or their aliases) when the user made their first edit during the
        timeframe of this contest.

        Args:
            sites (SiteManager): References to the sites part of this contest
            templates (list): List of templates to include
            include_aliases (bool): Whether to include aliases, defaults to True
        """
        Filter.__init__(self, sites)

        aliases = []
        for template_name in templates:
            template_page = self.sites.homesite.pages['Template:%s' % template_name]
            if template_page.exists:
                aliases.extend([x.page_title for x in template_page.backlinks(filterredir='redirects')])

        self.templates = templates + aliases

    def text_contains_template(self, text):
        """ Checks if a given text contains the template"""

        tpls = [x.replace('*', '[^}]*?') for x in self.templates]
        m = re.search(r'{{(%s)[\s]*(\||}})' % '|'.join(tpls), text, flags=re.IGNORECASE)
        if m:
            return m.group(1)
        return None

    def test_page(self, page):
        rev_id = page.revisions.firstkey()
        rev = page.revisions[rev_id]

        try:
            template_name = self.text_contains_template(rev.parenttext)
        except TemplateParseError as e:
            logger.warning('TemplateParser failed to parse %s', page.key)
            page.site().errors.append(
                _('Could not analyze page %(article)s because the revision %(rev)d could not be parsed: %(error)s') % {
                    'article': page.key,
                    'rev': rev.parentid,
                    'error': str(e),
                }
            )

        if template_name is None:
            return False
        logger.debug('Found template {{%s}} in [[%s]] @ %d', template_name, page.key, rev.parentid)
        return True


class CatFilter(Filter):
    """ Filters articles that belong to a given overcategory """

    @staticmethod
    def get_ignore_list(tpl, page_name):
        if page_name is None or page_name == '':
            return []

        catignore_txt = tpl.sites.homesite.pages[page_name].text()

        if catignore_txt == '':
            logger.info('Note: catignore page is empty or does not exist')
            return []

        try:
            m = re.search(r'<pre>(.*?)</pre>', catignore_txt, flags=re.DOTALL)
            return m.group(1).strip().splitlines()
        except (IndexError, KeyError):
            raise RuntimeError(_('Could not parse the catignore page'))

    @classmethod
    def make(cls, tpl, cfg, **kwargs):
        if len(tpl.anon_params) < 3:
            raise RuntimeError(_('No category values given!'))

        params = {
            'sites': tpl.sites,
            'ignore': cls.get_ignore_list(tpl, cfg.get('ignore_page')),
            'categories': [
                tpl.sites.resolve_page(cat_name, 14, True)
                for cat_name in tpl.anon_params[2:] if cat_name.strip() is not ''
            ],
        }

        if tpl.has_param('ignore'):
            params['ignore'].extend([
                a.strip()
                for a in tpl.get_param('ignore').split(',')
            ])

        if tpl.has_param('maxdepth'):
            params['maxdepth'] = int(tpl.get_param('maxdepth'))

        return cls(**params)

    def __init__(self, sites, categories, maxdepth=5, ignore=[]):
        """
        Arguments:
            sites (SiteManager): References to the sites part of this contest
            categories (list): Page objects
            maxdepth (int):  number of subcategory levels to traverse
            ignore (list): list of categories to ignore
        """
        Filter.__init__(self, sites)

        self.ignore = ignore
        self.include = ['%s:%s' % (x.site.key, x.name) for x in categories]
        self.maxdepth = int(maxdepth)
        logger.debug("Initializing CatFilter: %s, maxdepth=%d",
                    " OR ".join(self.include), maxdepth)

    def fetchcats(self, articles, debug=False):
        """ Fetches categories an overcategories for a set of articles """

        # Make a list of the categories of a given article, with one list for each level
        # > cats[article_key][level] = [cat1, cat2, ...]

        cats = {p: [[] for n in range(self.maxdepth + 1)] for p in articles}

        # Also, for each article, keep a list of category parents, so we can build
        # a path along the category tree from any matched category to the article
        # > parents[article_key][category] = parent_category
        #
        # Example:
        #                   /- cat 2
        #             /- cat1 -|
        # no:giraffe -|        \-
        #             \-
        #
        # parents['no:giraffe']['cat2'] = 'cat1'
        # parents['no:giraffe']['cat1'] = 'giraffe'
        #
        # We could also build full category trees for each article from the available
        # information, but they can grow quite big and slow to search

        parents = {p: {} for p in articles}

        #ctree = Tree()
        #for p in pages:
        #    ctree.add_child( name = p.encode('utf-8') )

        for site_key, site in self.sites.sites.items():

            if 'bot' in site.rights:
                requestlimit = 500
                returnlimit = 5000
            else:
                requestlimit = 50
                returnlimit = 500

            # Titles of articles that belong to this site
            titles = [article.name for article in articles.values() if article.site().key == site_key]

            # logger.debug(' ['+site_key+':'+str(len(titles))+']')
            #.flush()
            if len(titles) > 0:

                for level in range(self.maxdepth + 1):

                    titles0 = copy(titles)
                    titles = []  # make a new list of titles to search
                    nc = 0
                    nnc = 0

                    for s0 in range(0, len(titles0), requestlimit):
                        logger.debug('[%d] > Getting %d to %d of %d', level, s0, s0+requestlimit, len(titles0))
                        ids = '|'.join(titles0[s0:s0+requestlimit])

                        cont = True
                        clcont = {'continue': ''}
                        while cont:
                            # print clcont
                            args = {'prop': 'categories', 'titles': ids, 'cllimit': returnlimit}
                            args.update(clcont)
                            q = site.api('query', **args)

                            if 'warnings' in q:
                                raise RuntimeError(q['warnings']['query']['*'])

                            for pageid, page in q['query']['pages'].items():
                                fulltitle = page['title']
                                shorttitle = fulltitle.split(':', 1)[-1]
                                article_key = site_key + ':' + fulltitle
                                if 'categories' in page:
                                    for cat in page['categories']:
                                        cat_title = cat['title']
                                        cat_short = cat_title.split(':', 1)[1]
                                        site_cat = site_key + ':' + cat_title
                                        follow = True
                                        for d in self.ignore:
                                            if re.search(d, cat_short):
                                                logger.debug(' - Ignore: "%s" matched "%s"', cat_title, d)
                                                follow = False
                                        if follow:
                                            nc += 1
                                            titles.append(cat_title)
                                            if level == 0:
                                                cats[article_key][level].append(site_cat)
                                                parents[article_key][site_cat] = article_key
                                                #print cat_short
                                                # use iter_search_nodes instead?
                                                #ctree.search_nodes( name = fulltitle.encode('utf-8') )[0].add_child( name = cat_short.encode('utf-8') )
                                            else:
                                                for article_key2, ccc in cats.items():
                                                    if article_key in ccc[level-1]:
                                                        ccc[level].append(site_cat)
                                                        parents[article_key2][site_cat] = article_key
                                                        # print '>',article_key2, ':', site_cat,' = ',article_key

                                                        #for node in ctree.search_nodes( name = shorttitle.encode('utf-8') ):
                                                        #    if not cat_short.encode('utf-8') in [i.name for i in node.get_children()]:
                                                        #        node.add_child(name = cat_short.encode('utf-8'))
                                        else:
                                            nnc += 1
                            if 'continue' in q:
                                clcont = q['continue']
                            else:
                                cont = False
                    titles = list(set(titles))  # to remove duplicates (not order preserving)
                    #if level == 0:
                    #    cattree = [p for p in titles]
                    logger.debug(' %d', len(titles))
                    #.stdout.flush()
                    #print "Found %d unique categories (%d total) at level %d (skipped %d categories)" % (len(titles), nc, level, nnc)
        
        return cats, parents

    def check_article_cats(self, article_cats):
        """ Checks if article_cats contains any of the cats given in self.include """
        # loop over levels
        for inc in self.include:
            for cats in article_cats:
                if inc in cats:
                    return inc
        return None

    def filter(self, articles, debug=False):

        cats, parents = self.fetchcats(articles, debug=debug)

        out = odict()

        # loop over articles
        for article_key, article_cats in cats.items():
            #if debug:
            #    print
            article = articles[article_key]
            lang = article_key.split(':')[0]
            if debug:
                logger.debug("CatFilter: %s", article.name)
                for l, ca in enumerate(article_cats):
                    logger.debug('CatFilter [%d] %s', l, ', '.join(ca))

            #print
            #print article_key
            #print article_cats
            #print
            catname = self.check_article_cats(article_cats)
            if catname:

                # Add category path to the article object, so we can check how the article matched
                article.cat_path = [catname]
                # print '[%s]' % (article_key)
                try:
                    i = 0
                    aname = article.site().key + ':' + article.name
                    while not catname == aname:
                        # print ' [%d] %s' % (i,catname)
                        if not parents[article_key][catname] == aname:
                            article.cat_path.append(parents[article_key][catname])
                        catname = parents[article_key][catname]
                        i += 1
                        if i > 50:
                            raise CategoryLoopError(article.cat_path)
                except CategoryLoopError as e:
                    article.errors.append(_('Encountered an infinite category loop: ')
                        + ' → '.join(['[[:%(catname)s|]]'
                        % {'catname': c} for c in e.catpath]))

                out[article_key] = article

        logger.info(" - CatFilter: Articles reduced from %d to %d", len(articles), len(out))
        return out


class ByteFilter(Filter):
    """Filters articles according to a byte treshold"""

    @classmethod
    def make(cls, tpl, sites, **kwargs):
        if len(tpl.anon_params) < 3:
            raise RuntimeError(_('No byte limit (second argument) given'))
        params = {
            'sites': tpl.sites,
            'bytelimit': int(tpl.anon_params[2]),
        }
        return cls(**params)

    def __init__(self, sites, bytelimit):
        """
        The ByteFilter keeps pages with a byte size above a certain threshold limit. 

        Args:
            sites (SiteManager): References to the sites part of this contest
            bytelimit (int): The minimum number of bytes required to keep a page
        """
        Filter.__init__(self, sites)
        self.bytelimit = bytelimit

    def test_page(self, page):
        """
        Return True if the page matches the current filter, False otherwise.
        """
        return page.bytes >= self.bytelimit


class NewPageFilter(Filter):
    """Filters new articles"""

    @classmethod
    def make(cls, tpl, contest, **kwargs):
        params = {
            'sites': tpl.sites,
            'contest': contest,
        }
        if tpl.has_param('redirects'):
            params['redirects'] = True
        return cls(**params)

    def __init__(self, sites, contest, redirects=False):
        """
        The NewPageFilter keeps pages that was created within the timeframe of a contest.
        In order to encourage collaboration on articles, the filter does not discriminate
        on which user created the page. 

        Args:
            sites (SiteManager): References to the sites part of this contest
            contest (Contest): The current contest
            redirects (bool): Whether to include redirect pages, defaults to False
        """
        Filter.__init__(self, sites)
        self.contest_start = contest.start
        self.contest_end = contest.end
        self.redirects = redirects

    def test_page(self, page):
        """
        Return True if the page matches the current filter, False otherwise.
        """
        if page.redirect and not self.redirects:
            return False
        return page.created_at >= self.contest_start and page.created_at < self.contest_end


class ExistingPageFilter(Filter):
    """ Filters non-new articles """

    @classmethod
    def make(cls, tpl, contest, **kwargs):
        params = {
            'sites': tpl.sites,
            'contest': contest,
        }
        return cls(**params)

    def __init__(self, sites, contest):
        """
        The ExistingPageFilter keeps pages that was created before the start of a contest.
        This is useful in contests that are about improving existing content.

        Args:
            sites (SiteManager): References to the sites part of this contest
            contest (Contest): The current contest
        """
        Filter.__init__(self, sites)
        self.contest_start = contest.start

    def test_page(self, page):
        """
        Return True if the page matches the current filter, False otherwise.
        """
        return page.created_at < self.contest_start


class BackLinkFilter(Filter):
    """Filters articles linked to from a list of pages."""

    @classmethod
    def make(cls, tpl, cfg, **kwargs):
        params = {
            'sites': tpl.sites,
            'pages': [tpl.sites.resolve_page(x) for x in tpl.anon_params[2:] if x.strip() is not ''],
            'include_langlinks': cfg.get('include_langlinks', False),
        }
        return cls(**params)

    def __init__(self, sites, pages, include_langlinks=False):
        """
        The BackLinkFilter keeps pages linked to from a list of pages, and optionally also the
        interwiki links of those pages.

        Args:
            sites (SiteManager): References to the sites part of this contest
            pages(list): List of Page objects to extract links from.
            include_langlinks(bool): Whether to include langlinked pages as well. This is useful for 
                multi-language contests, but we can save some time by not checking them.
        """
        Filter.__init__(self, sites)

        page_names = ['%s:%s' % (x.site.key, x.name) for x in pages]
        logger.info('Initializing BackLinkFilter: %s',
                    ','.join(page_names))

        for page in pages:
            for linked_page in page.links(redirects=True):
                link = '%s:%s' % (linked_page.site.key, linked_page.name.replace('_', ' '))
                logger.debug(' - Include: %s', link)
                self.page_keys.add(link)

                # Include langlinks as well
                if include_langlinks:
                    for langlink in linked_page.langlinks():
                        site = self.sites.from_prefix(langlink[0])
                        if site is not None:
                            link = '%s:%s' % (site.host, langlink[1].replace('_', ' '))
                            logger.debug(' - Include: %s', link)
                            self.page_keys.add(link)

        logger.info('BackLinkFilter ready with %d links (after having expanded langlinks)',
                    len(self.page_keys))


class ForwardLinkFilter(Filter):
    """Filters articles linking to <self.links>"""

    @classmethod
    def make(cls, tpl, **kwargs):

        params = {
            'sites': tpl.sites,
            'pages': [tpl.sites.resolve_page(x) for x in tpl.anon_params[2:] if x.strip() is not ''],
        }
        return cls(**params)

    def __init__(self, sites, pages):
        """
        Arguments:
            sites (SiteManager): References to the sites part of this contest
            pages: list of Page objects
        """
        Filter.__init__(self, sites)

        for page in pages:
            for linked_page in page.backlinks(redirect=True):
                link = '%s:%s' % (linked_page.site.key, linked_page.name.replace('_', ' '))
                self.page_keys.add(link)

        logger.info('ForwardLinkFilter ready with %d links', len(self.page_keys))


class PageFilter(Filter):
    """Filters articles with forwardlinks to <name>"""

    @classmethod
    def make(cls, tpl, **kwargs):
        params = {
            'sites': tpl.sites,
            'pages': [tpl.sites.resolve_page(x) for x in tpl.anon_params[2:] if x.strip() is not '']
        }
        return cls(**params)

    def __init__(self, sites, pages):
        """
        Arguments:
            sites (SiteManager): References to the sites part of this contest 
            pages (list): list of Page objects
        """
        Filter.__init__(self, sites)
        self.page_keys = set(['%s:%s' % (page.site.key, page.name) for page in pages])
        logger.info('PageFilter ready with %d links', len(self.page_keys))


class NamespaceFilter(Filter):
    """Filters articles with a given namespaces"""

    @classmethod
    def make(cls, tpl, cfg, **kwargs):
        params = {
            'sites': tpl.sites,
            'namespaces': [x.strip() for x in tpl.anon_params[2:]],
        }
        return cls(**params)

    def __init__(self, sites, namespaces):
        """
        Args:
            sites (SiteManager): References to the sites part of this contest
            namespaces (list): List of namespaces to include
        """
        Filter.__init__(self, sites)
        self.namespaces = namespaces
        logger.info('NamespaceFilter: namespaces: %s', ','.join(self.namespaces))

    def test_page(self, page):
        """
        Return True if the page matches the current filter, False otherwise.
        """
        return page.ns in self.namespaces


class SparqlFilter(Filter):
    """Filters articles matching a SPARQL query"""

    @classmethod
    def make(cls, tpl, cfg, **kwargs):
        if not tpl.has_param('query'):
            raise RuntimeError(_('No "%s" parameter given') % cfg['params']['query'])
        
        params = {
            'query': tpl.get_param('query'),
            'sites': tpl.sites,
        }
        return cls(**params)

    def __init__(self, sites, query):
        """
        Args:
            sites (SiteManager): References to the sites part of this contest
            query (str): The SPARQL query
        """
        Filter.__init__(self, sites)
        self.query = query
        self.fetch()

    def do_query(self, querystring):
        response = requests.get(
            'https://query.wikidata.org/sparql',
            params={
                'query': querystring,
            },
            headers={
                'accept': 'application/sparql-results+json',
                'accept-encoding': 'gzip, deflate, br',
                'user-agent': 'UKBot/1.0, run by User:Danmichaelo',
            }
        )
        if not response.ok:
            raise IOError('SPARQL query returned status %s', response.status_code)

        expected_length = response.headers.get('Content-Length')
        if expected_length is not None and 'tell' in dir(response.raw):
            actual_length = response.raw.tell()
            expected_length = int(expected_length)
            if actual_length < expected_length:
                raise IOError(
                    'Incomplete read ({} bytes read, {} more expected)'.format(
                        actual_length,
                        expected_length - actual_length
                    )
                )

        res = response.json()
        query_var = res['head']['vars'][0]
        logger.debug('SPARQL query var is: %s', query_var)

        return {
            'var': query_var,
            'rows': [x[query_var]['value'] for x in res['results']['bindings']],
        }

    def fetch(self):
        logger.debug('SparqlFilter: %s', self.query)

        t0 = time.time()
        result = self.do_query(self.query)
        try:
            result = self.do_query(self.query)
        except:
            raise InvalidContestPage(_('SPARQL query invalid or timed out'))
        dt = time.time() - t0

        if len(result['rows']) == 0:
            raise InvalidContestPage(_('SPARQL query returned zero results'))

        query_variable = result['var']

        logger.info('SparqlFilter: Got %d results in %.1f secs', len(result['rows']), dt)

        # Implementatio notes:
        # - When the contest includes multiple sites, we do one query per site. I tried using
        #   a single query with `VALUES ?site { %(sites)s }` instead, but the query time
        #   almost doubled for each additional site, making timeouts likely.
        # - I also tested doing two separate queries rather than one query with a subquery,
        #   but when the number of items became large it resulted in "request too large".
        for site in self.sites.sites.keys():
            logger.debug('Querying site: %s', site)
            article_variable = 'article19472065'  # "random string" to avoid matching anything in the subquery
            query = """
                SELECT ?%(article_variable)s
                WHERE {
                  { %(query)s }
                  ?%(article_variable)s schema:about ?%(query_variable)s .
                  ?%(article_variable)s schema:isPartOf <https://%(site)s/> .
                }
            """ % {
                'query_variable': query_variable,
                'article_variable': article_variable,
                'query': self.query,
                'site': site,
            }
            logger.debug('SparqlFilter: %s', query)

            t0 = time.time()
            n = 0
            for res in self.do_query(query)['rows']:
                n += 1
                article = '/'.join(res.split('/')[4:])
                article = urllib.parse.unquote(article).replace('_', ' ')
                page_key = '%s:%s' % (site, article)
                self.page_keys.add(page_key)

            dt = time.time() - t0
            logger.info('SparqlFilter: Got %d results for %s in %.1f secs', n, site, dt)

        logger.info('SparqlFilter: Initialized with %d articles', len(self.page_keys))
