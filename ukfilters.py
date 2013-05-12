#encoding=utf-8
from __future__ import unicode_literals
import sys
import re
from copy import copy
from odict import odict
from ukcommon import log


class CategoryLoopError(Exception):
    """Raised when a category loop is found.

    Attributes:
        catpath -- category path followed while getting lost in the loop
    """
    def __init__(self, catpath):
        self.catpath = catpath
        self.msg = 'Entered a category loop'


class Filter(object):

    def __init__(self, verbose):
        self.verbose = verbose

    def extend(self, ffilter):
        pass

#class StubFilter(Filter):
#    """ Filters articles that was stubs, but is no more """

#    def __init__(self, verbose):
#        Filter.__init__(self, verbose)

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
    #    for article_key, article in articles.iteritems():

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
            #    article.site.errors.append(_('Could not analyze the article %(article)s because one of the revisions %(prevrev)d or %(rev)d could not be parsed: %(error)s') % args)

    #    log("  [+] Applying stub filter: %d -> %d" % (len(articles), len(out)))

    #    return out


class TemplateFilter(Filter):
    """ Filters articles that had any of a given set of templates (or their aliases) at a point"""

    def __init__(self, verbose, templates, aliases=[]):
        Filter.__init__(self, verbose)
        templates.extend([a.lower() for a in aliases])
        self.templates = templates

    def extend(self, templatefilter):
        self.templates.extend(templatefilter.templates)

    def has_template(self, text):
        """ Checks if a given text contains the template"""

        m = re.search(r'{{(%s)[\s]*(\||}})' % '|'.join(self.templates), text, flags=re.IGNORECASE)
        if m:
            return m.group(1)
        return None

    def filter(self, articles):

        out = odict()
        for article_key, article in articles.iteritems():

            firstrevid = article.revisions.firstkey()
            firstrev = article.revisions[firstrevid]

            try:

                #if article.new == False and article.redirect == False:

                # Check if first revision is a stub
                t = self.has_template(firstrev.parenttext)
                if t:
                    if self.verbose:
                        log('      Found template {{%s}} in [[%s]] @ %d' % (t, article_key, firstrevid))
                    out[article_key] = article

            except DanmicholoParseError as e:
                log(" >> DanmicholoParser failed to parse " + article_key)
                parentid = firstrev.parentid
                args = {'article': article_key, 'prevrev': firstrev.parentid, 'rev': lastrev.revid, 'error': e.msg}
                article.site.errors.append(_('Could not analyze the article %(article)s because one of the revisions %(prevrev)d or %(rev)d could not be parsed: %(error)s') % args)

        log("  [+] Applying template filter: %d -> %d" % (len(articles), len(out)))

        return out


class CatFilter(Filter):
    """ Filters articles that belong to a given overcategory """

    def __init__(self, verbose, sites, catnames, maxdepth=4, ignore=[]):
        """
        Arguments:
            sites     : dict { 'no': <mwclient.client.Site>, ... }
            catnames  : list of category names
            maxdepth  : number of subcategory levels to traverse
        """
        Filter.__init__(self, verbose)

        self.ignore = ignore
        self.sites = sites
        self.include = [c[c.rfind(':')+1:] for c in catnames]
        self.maxdepth = int(maxdepth)
        if self.verbose:
            log("  CatFilter: %s" % (" OR ".join(self.include)))

    def extend(self, catfilter):
        self.include.extend(catfilter.include)

    def fetchcats(self, articles, debug=False):
        """ Fetches categories an overcategories for a set of articles """

        # Make a list of the categories of a given article, with one list for each level
        # > cats[article_key][level] = [cat1, cat2, ...]

        cats = {p: [[] for n in range(self.maxdepth)] for p in articles}

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

        for site_key, site in self.sites.iteritems():

            if 'bot' in site.rights:
                requestlimit = 500
                returnlimit = 5000
            else:
                requestlimit = 50
                returnlimit = 500

            # Titles of articles that belong to this site
            titles = [article.name for article in articles.itervalues() if article.site.key == site_key]

            log(' ['+site_key+':'+str(len(titles))+']', newline=False)
            #.flush()
            if len(titles) > 0:

                for level in range(self.maxdepth):

                    titles0 = copy(titles)
                    titles = []  # make a new list of titles to search
                    nc = 0
                    nnc = 0

                    for s0 in range(0, len(titles0), requestlimit):
                        if debug:
                            print
                            print "[%d] > Getting %d to %d of %d" % (level, s0, s0+requestlimit, len(titles0))
                        ids = '|'.join(titles0[s0:s0+requestlimit])

                        cont = True
                        clcont = ''
                        while cont:
                            #print clcont
                            if clcont != '':
                                q = site.api('query', prop='categories', titles=ids, cllimit=returnlimit, clcontinue=clcont)
                            else:
                                q = site.api('query', prop='categories', titles=ids, cllimit=returnlimit)

                            if 'warnings' in q:
                                raise StandardError(q['warnings']['query']['*'])

                            for pageid, page in q['query']['pages'].iteritems():
                                fulltitle = page['title']
                                shorttitle = fulltitle.split(':', 1)[-1]
                                article_key = site_key + ':' + fulltitle
                                if 'categories' in page:
                                    for cat in page['categories']:
                                        cat_title = cat['title']
                                        cat_short = cat_title.split(':', 1)[1]
                                        follow = True
                                        for d in self.ignore:
                                            if re.search(d, cat_short):
                                                if self.verbose:
                                                    log(' - Ignore: "%s" matched "%s"' % (cat_title, d))
                                                follow = False
                                        if follow:
                                            nc += 1
                                            titles.append(cat_title)
                                            if level == 0:
                                                cats[article_key][level].append(cat_short)
                                                parents[article_key][cat_short] = fulltitle
                                                #print cat_short
                                                # use iter_search_nodes instead?
                                                #ctree.search_nodes( name = fulltitle.encode('utf-8') )[0].add_child( name = cat_short.encode('utf-8') )
                                            else:
                                                for article_key, ccc in cats.iteritems():
                                                    if shorttitle in ccc[level-1]:
                                                        ccc[level].append(cat_short)
                                                        parents[article_key][cat_short] = shorttitle

                                                        #for node in ctree.search_nodes( name = shorttitle.encode('utf-8') ):
                                                        #    if not cat_short.encode('utf-8') in [i.name for i in node.get_children()]:
                                                        #        node.add_child(name = cat_short.encode('utf-8'))
                                        else:
                                            nnc += 1
                            if 'query-continue' in q:
                                clcont = q['query-continue']['categories']['clcontinue']
                            else:
                                cont = False
                    titles = list(set(titles))  # to remove duplicates (not order preserving)
                    #if level == 0:
                    #    cattree = [p for p in titles]
                    #if self.verbose:
                    log(' %d' % (len(titles)), newline=False)
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

        #if self.verbose:
        log("  [+] Applying category filter", newline=False)

        cats, parents = self.fetchcats(articles, debug=debug)

        out = odict()

        # loop over articles
        for article_key, article_cats in cats.iteritems():
            #if debug:
            #    print
            article = articles[article_key]
            if debug:
                log(">>> %s" % article.name, newline=False)
                for l, ca in enumerate(article_cats):
                    log('[%d] %s' % (l, ', '.join(ca)), newline=False)

            #print article_key
            #print article_cats
            catname = self.check_article_cats(article_cats)
            if catname:

                # Add category path to the article object, so we can check how the article matched
                article.cat_path = [catname]
                try:
                    i = 0
                    while not catname == article.name:
                        #print ' [%d] %s' % (i,catname)
                        if not parents[article_key][catname] == article.name:
                            article.cat_path.append(parents[article_key][catname])
                        catname = parents[article_key][catname]
                        i += 1
                        if i > 50:
                            raise CategoryLoopError(article.cat_path)
                except CategoryLoopError as e:
                    article.errors.append(_('Encountered an infinite category loop: ') + ' → '.join(['[[:Kategori:'+c+'|'+c+']]' for c in e.catpath]))

                out[article_key] = article

        #if self.verbose:
        log(": %d -> %d" % (len(articles), len(out)))
        return out


class ByteFilter(Filter):
    """Filters articles according to a byte treshold"""

    def __init__(self, verbose, bytelimit):
        Filter.__init__(self, verbose)
        self.bytelimit = int(bytelimit)

    def filter(self, articles):
        out = odict()
        for article_key, article in articles.iteritems():
            if article.bytes >= self.bytelimit:
                out[article_key] = article
        log("  [+] Applying byte filter (%d bytes): %d -> %d" % (self.bytelimit, len(articles), len(out)))
        return out


class NewPageFilter(Filter):
    """Filters new articles"""

    def __init__(self, verbose):
        Filter.__init__(self, verbose)

    def filter(self, articles):
        log("  [+] Applying new page filter")
        out = odict()
        for a, aa in articles.iteritems():
            if aa.new and not aa.redirect:
                out[a] = aa
        return out


class ExistingPageFilter(Filter):
    """ Filters non-new articles """

    def __init__(self, verbose):
        Filter.__init__(self, verbose)

    def filter(self, articles):
        log("  [+] Applying existing page filter")
        out = odict()
        for aname, article in articles.iteritems():
            if not article.new:
                out[aname] = article
        return out


class BackLinkFilter(Filter):
    """Filters articles with backlinks to <name>"""

    def __init__(self, verbose, sites, articles):
        """
        Arguments:
            sites     : dict { 'no': <mwclient.client.Site>, ... }
            articles  : list of article names
        """
        Filter.__init__(self, verbose)
        self.sites = sites
        self.articles = articles
        self.links = []
        log("  [+] Initializing backlink filter: " + ','.join(self.articles))
        #print sites

        for site_key, site in self.sites.iteritems():
            for aname in self.articles:
                aname2 = aname
                kv = aname.split(':', 1)
                if len(kv) == 2 and len(kv[0]) == 2:
                    if kv[0] != site_key:
                        continue
                    else:
                        aname2 = kv[1]
                p = site.pages[aname2]
                if p.exists:
                    for link in p.links(redirects=True):
                        self.links.append(site_key+':'+link.name)

        #print self.links

    def extend(self, blfilter):
        self.links.extend(blfilter.links)
        self.articles.extend(blfilter.articles)

    def filter(self, articles):
        out = odict()
        for article_key, article in articles.iteritems():
            if article_key in self.links:
                out[article_key] = article
        log("  [+] Applying backlink filter (%s): %d -> %d" % (','.join(self.articles), len(articles), len(out)))
        return out


class ForwardLinkFilter(Filter):
    """Filters articles with forwardlinks to <name>"""

    def __init__(self, verbose, sites, articles):
        """
        Arguments:
            sites     : dict { 'no': <mwclient.client.Site>, ... }
            articles  : list of article names
        """
        Filter.__init__(self, verbose)
        self.sites = sites
        self.articles = articles
        self.links = []

        for site_key, site in self.sites.iteritems():
            for aname in self.articles:
                p = site.pages[aname]
                if p.exists:
                    for link in p.backlinks(redirect=True):
                        self.links.append(site_key+':'+link.name)

        #print self.links

    def extend(self, flfilter):
        self.links.extend(flfilter.links)
        self.articles.extend(flfilter.articles)

    def filter(self, articles):
        out = odict()
        for article_key, article in articles.iteritems():
            if article_key in self.links:
                out[article_key] = article
        log("  [+] Applying forward link filter (%s): %d -> %d" % (','.join(self.articles), len(articles), len(out)))
        return out


class PageFilter(Filter):
    """Filters articles with forwardlinks to <name>"""

    def __init__(self, verbose, sites, pages):
        """
        Arguments:
            sites     : dict { 'no': <mwclient.client.Site>, ... }
            pages     : list of page names
        """
        Filter.__init__(self, verbose)
        self.sites = sites
        self.pages = pages

    def extend(self, flfilter):
        self.pages.extend(flfilter.pages)

    def filter(self, articles):
        out = odict()
        for article_key, article in articles.iteritems():
            if article_key in self.pages:
                out[article_key] = article
        log("  [+] Applying page link filter (%s): %d -> %d" % (','.join(self.pages), len(articles), len(out)))
        return out


class NamespaceFilter(Filter):
    """Filters articles with forwardlinks to <name>"""

    def __init__(self, verbose, namespace):
        """
        Arguments:
            namespace : int
        """
        Filter.__init__(self, verbose)
        self.namespace = namespace

    def filter(self, articles):
        #out = odict()
        #for article_key, article in articles.iteritems():
        #    if article.namespace == self.namespace:
        #        out[article_key] = article
        #log("  [+] Applying namespace filter (%s): %d -> %d" % (','.join(self.articles), len(articles), len(out)))
        return articles  # already filtered
