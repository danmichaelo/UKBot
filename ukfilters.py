#encoding=utf-8
from __future__ import unicode_literals
import sys, re
from copy import copy
from odict import odict
from danmicholoparser import DanmicholoParser, DanmicholoParseError


class Filter(object):

    def __init__(self):
        pass

class StubFilter(Filter):
    """ Filters articles that was stubs, but is no more """

    def __init__(self):
        Filter.__init__(self)

    def is_stub(self, text, logf, verbose = False):
        """ Checks if a given text is a stub """

        dp = DanmicholoParser(text, debug = False)
        for tname, templ in dp.templates.iteritems():
            if tname.find('stubb') != -1 or tname.find('spire') != -1:
                if verbose:
                    logf.write(" >> %s " % (tname))
                return True
        return False

    def filter(self, articles, logf, verbose = True):

        out = odict()
        for article_key, article in articles.iteritems():

            firstrevid = article.revisions.firstkey()
            lastrevid = article.revisions.lastkey()

            firstrev = article.revisions[firstrevid]
            lastrev = article.revisions[lastrevid]

            try:
                
                # skip pages that are definitely not stubs to avoid timeconsuming parsing
                if article.new == False and article.redirect == False and len(firstrev.parenttext) < 20000:  

                    # Check if first revision is a stub
                    if self.is_stub(firstrev.parenttext, logf, verbose):

                        # Check if last revision is a stub
                        if not self.is_stub(lastrev.text, logf, verbose):

                            out[article_key] = article

                        if verbose:
                            logf.write("\n")
                
            except DanmicholoParseError as e:
                logf.write(" >> DanmicholoParser failed to parse " + article_key + '\n')
                parentid = firstrev.parentid
                article.site.errors.append('Artikkelen %s kunne ikke analyseres fordi en av revisjone %d eller %d ikke kunne parses: %s' % (article_key, firstrev.parentid, lastrev.revid, e.msg))
        
        logf.write("  [+] Applying stub filter: %d -> %d\n" % (len(articles), len(out)))

        return out

class CatFilter(Filter):
    """ Filters articles that belong to a given overcategory """

    def __init__(self, sites, catnames, maxdepth = 4, ignore = []):
        """
        Arguments:
            sites     : dict { 'no': <mwclient.client.Site>, ... }
            catnames  : list of category names
            maxdepth  : number of subcategory levels to traverse
        """
        Filter.__init__(self)
        
        self.ignore = ignore
        self.sites = sites
        self.include = catnames
        self.maxdepth = int(maxdepth)
        self.verbose = True

 
    def fetchcats(self, articles, logf, debug=False):
        """ Fetches categories an overcategories for a set of articles """
        
        # Make a list of the categories of a given article, with one list for each level
        # > cats[article_key][level] = [cat1, cat2, ...]

        cats = { p: [[] for n in range(self.maxdepth)] for p in articles }

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

        parents = { p: {} for p in articles }

        #ctree = Tree()
        #for p in pages:
        #    ctree.add_child( name = p.encode('utf-8') )

        for site_key, site in self.sites.iteritems():
            
            if 'bot' in site.rights:
                apilim = 5000
            else:
                apilim = 50

            # Titles of articles that belong to this site
            titles = [article.name for article in articles.itervalues() if article.site.key == site_key]
            
            logf.write(' ['+site_key+':'+str(len(titles))+']')
            #.flush()
            if len(titles) > 0:
        
                for level in range(self.maxdepth):

                    titles0 = copy(titles)
                    titles = [] # make a new list of titles to search
                    nc = 0
                    nnc = 0
            
                    for s0 in range(0, len(titles0), apilim):
                        #if debug:
                        #print
                        #print "[%d] > Getting %d to %d of %d" % (level, s0, s0+apilim, len(titles0))
                        ids = '|'.join(titles0[s0:s0+apilim])

                        cont = True
                        clcont = ''
                        while cont:
                            #print clcont
                            if clcont != '':
                                q = site.api('query', prop = 'categories', titles = ids, cllimit = apilim, clcontinue = clcont)
                            else:
                                q = site.api('query', prop = 'categories', titles = ids, cllimit = apilim)
                            
                            if 'warnings' in q:
                                raise StandardError(q['warnings']['query']['*'])

                            for pageid, page in q['query']['pages'].iteritems():
                                fulltitle = page['title']
                                shorttitle = fulltitle.split(':',1)[-1]
                                article_key = site_key + ':' + fulltitle
                                if 'categories' in page:
                                    for cat in page['categories']:
                                        cat_title = cat['title']
                                        cat_short= cat_title.split(':',1)[1]
                                        follow = True
                                        for d in self.ignore:
                                            if re.search(d, cat_short):
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
                                            #if debug:
                                            #    print "ignore",cat_title
                                            nnc += 1
                            if 'query-continue' in q:
                                clcont = q['query-continue']['categories']['clcontinue']
                            else:
                                cont = False
                    titles = list(set(titles)) # to remove duplicates (not order preserving)
                    #if level == 0:
                    #    cattree = [p for p in titles]
                    if self.verbose:
                        logf.write(' %d' % (len(titles)))
                        #.stdout.flush()
                        #print "Found %d unique categories (%d total) at level %d (skipped %d categories)" % (len(titles), nc, level, nnc)


        return cats, parents 

    def check_article_cats(self, article_cats):
        """ Checks if article_cats contains any of the cats given in self.include """
        # loop over levels
        for cats in article_cats:
            for inc in self.include:
                if inc in cats:
                    return inc
        return None
    
    def filter(self, articles, logf, debug = False):
        
        if self.verbose:
            logf.write("  [+] Applying category filter")

        cats, parents = self.fetchcats(articles, logf, debug=debug)

        out = odict()

        # loop over articles
        for article_key, article_cats in cats.iteritems():
            #if debug:
            #    print
            article = articles[article_key]
            if debug:
                logf.write(">>> %s"%article.name)
                for l,ca in enumerate(article_cats):
                    logf.write('[%d] %s' % (l, ', '.join(ca)))

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
                    article.errors.append('Havnet i en endeløs kategorisløyfe : ' + ' → '.join(['[[:Kategori:'+c+'|'+c+']]' for c in e.catpath]))

                out[article_key] = article

        if self.verbose:
            logf.write(": %d -> %d\n" % (len(articles), len(out)))
            #sys.stdout.flush()
        return out

class ByteFilter(Filter):
    """Filters articles according to a byte treshold"""

    def __init__(self, bytelimit):
        Filter.__init__(self)
        self.bytelimit = int(bytelimit)

    def filter(self, articles, logf):
        out = odict()
        for article_key, article in articles.iteritems():
            if article.bytes >= self.bytelimit:
                out[article_key] = article
        logf.write("  [+] Applying byte filter (%d bytes): %d -> %d\n" % (self.bytelimit, len(articles), len(out)))
        return out

class NewPageFilter(Filter):
    """Filters new articles"""

    def __init__(self):
        Filter.__init__(self)

    def filter(self, articles, logf):
        logf.write("  [+] Applying new page filter\n")
        out = odict()
        for a, aa in articles.iteritems():
            if aa.new and not aa.redirect:
                out[a] = aa
        return out

class ExistingPageFilter(Filter):
    """ Filters non-new articles """

    def __init__(self):
        Filter.__init__(self)

    def filter(self, articles, logf):
        logf.write("  [+] Applying existing page filter\n")
        out = odict()
        for aname, article in articles.iteritems():
            if not article.new:
                out[aname] = article
        return out
    
