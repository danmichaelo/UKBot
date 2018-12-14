# encoding=utf-8
# vim: fenc=utf-8 et sw=4 ts=4 sts=4 ai
import re
from lxml.html import fromstring
import lxml
import functools
from mwtextextractor import condition_for_lxml
from mwclient.errors import InvalidPageTitle
import urllib
import logging
from .common import t, _
from .contributions import UserContribution

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class Rule(object):

    def __init__(self, key):
        self.key = key

    # def iszero(self, f):
    #     f = float(f)
    #     return (f > -0.1 and f < 0.1)

    # def add_points(self, rev, points, ptype, txt, pmax, include_zero=False):

    #     ab = rev.article().get_points(ptype)
    #     ab_raw = rev.article().get_points(ptype, ignore_max=True)
    #     pts = 0.0

    #     if pmax > 0.0 and self.iszero(ab - pmax):
    #         # we have reached max
    #         if points < 0.0 and ab_raw + points < pmax:
    #             pts = pmax - ab_raw - points
    #         rev.points.append([pts, ptype, txt, points])

    #     elif pmax > 0.0 and ab + points > pmax:
    #         # reaching max
    #         pts = pmax - ab
    #         rev.points.append([pts, ptype, txt + ' &gt; ' + _('max'), points])

    #     #elif not self.iszero(revpoints):
    #     else:
    #         if self.iszero(points) and not include_zero:
    #             return False
    #         pts = points
    #         rev.points.append([points, ptype, txt, points])
    #     if pts > 0.0:
    #         return True


class NewPageRule(Rule):

    def __init__(self, key, points):
        Rule.__init__(self, key)
        self.points = float(points)

    def test(self, rev):
        if rev.new and not rev.redirect:
            yield UserContribution(rev=rev, points=self.points, rule=self, description=_('new page'))


class RedirectRule(Rule):

    def __init__(self, key, points):
        Rule.__init__(self, key)
        self.points = float(points)

    def test(self, rev):
        if rev.new and rev.redirect:
            yield UserContribution(rev=rev, points=self.points, rule=self, description=_('redirect'))


# class StubRule(Rule):

#     def __init__(self, points):
#         Rule.__init__(self)
#         self.points = float(points)

#     def is_stub(self, text):
#         """ Checks if a given text is a stub """

#         dp = DanmicholoParser(text)
#         for tname, templ in dp.templates.iteritems():
#             if tname.find('stubb') != -1 or tname.find('spire') != -1:
#                 return True
#         return False

#     def test(self, rev):
#         try:
#             if self.is_stub(rev.parenttext) and not self.is_stub(rev.text):
#                 rev.points.append([self.points, 'stub', 'avstubbing'])
#         except DanmicholoParseError as e:
#             rev.article().errors.append(_('Encountered a problem while parsing [%(url)s rev. %(revid)d] : %(error)s' % { 'url': rev.get_link(), 'revid': rev.revid, 'error': e.msg })


class TemplateRemovalRule(Rule):

    def __init__(self, key, points, templates):
        Rule.__init__(self, key)
        self.points = float(points)

        # Make page_name -> [aliases] map
        self.templates = []
        logger.info('Initializing TemplateRemovalRule with %d templates:', len(templates))
        for page in templates:
            tpl = {
                'site': page.site,
                'name': page.page_title,
                'values': [page.page_title.lower()],
                'total': 0,
            }
            if page.exists:
                for alias in page.backlinks(filterredir='redirects'):
                    tpl['values'].append(alias.page_title.lower())
            self.templates.append(tpl)

            logger.info('  - Template site="%s" name="%s", aliases="%s"',
                        tpl['site'].host, tpl['name'], ','.join(tpl['values']))

    def matches_template(self, template, text):
        """Check if the text matches the template name or any of its aliases. Supports wildcards."""
        text = text.lower()
        for tpl_name in template['values']:
            if tpl_name[0] == '*' and tpl_name[-1] == '*' and text.find(tpl_name[1:-1]) != -1:
                return True
            elif tpl_name[0] == '*' and text.endswith(tpl_name[1:]):
                return True
            elif tpl_name[-1] == '*' and text.startswith(tpl_name[:-1]):
                return True
            elif text == tpl_name:
                return True
        return False

    def count_instances(self, template, parsed_text):
        """Count the number of instances of a template in a given text."""
        tc = 0
        for node in parsed_text.templates.doc.findall('.//template'):
            for elem in node:
                if (elem.tag == 'title') and (elem.text is not None):
                    if self.matches_template(template, elem.text):
                        tc += 1
        return tc

    def get_templates_removed(self, template, rev):
        pt = self.count_instances(template, rev.te_parenttext())
        ct = self.count_instances(template, rev.te_text())
        return pt - ct

    def test(self, rev):
        if rev.redirect or rev.parentredirect:
            # skip redirects
            return

        for template in self.templates:
            if template['site'] != rev.article().site():
                continue
            removed = self.get_templates_removed(template, rev)
            if removed > 0:
                template['total'] += removed
                yield UserContribution(rev=rev, rule=self, points=removed * self.points,
                                       description=_('removal of {{tl|%(template)s}}') % {'template': template['name']})


class QualiRule(Rule):

    def __init__(self, key, points):
        Rule.__init__(self, key)
        self.points = float(points)

    def test(self, rev):
        if self.iszero(rev.article().get_points('quali')):
            yield UserContribution(rev=rev, points=self.points, rule=self,
                                   description=_('qualified'))


class ContribRule(Rule):

    def __init__(self, key, points):
        Rule.__init__(self, key)
        self.points = float(points)

    def test(self, rev):
        yield UserContribution(rev=rev, points=self.points, rule=self.rule, description=_('contribution'))


class ByteRule(Rule):

    def __init__(self, key, points, maxpoints=-1):
        Rule.__init__(self, key)
        self.points = float(points)
        self.maxpoints = float(maxpoints)

    @capped(include_zero=True)
    def test(self, rev):
        points = rev.bytes * self.points
        yield UserContribution(rev=rev, points=points, rule=self, description=_('%(bytes).f bytes') % {'bytes': rev.bytes})
        # self.add_points(rev, revpoints, 'byte',
        #                 _('%(bytes).f bytes') % {'bytes': rev.bytes},
        #                 self.maxpoints, include_zero=True)


class WordRule(Rule):

    def __init__(self, key, points, maxpoints=-1):
        Rule.__init__(self, key)
        self.points = float(points)
        self.maxpoints = float(maxpoints)

    def test(self, rev):
        words = rev.words
        points = words * self.points
        yield UserContribution(rev=rev, points=points, rule=self, description=_('%(words).f words') % {'words': words})


class ImageRule(Rule):

    def __init__(self, key, points, maxpoints=-1, own=-1, ownwork=-1, maxinitialcount=9999, file_prefixes=None):
        Rule.__init__(self, key)
        self.points = float(points)
        self.maxpoints = float(maxpoints)
        self.total = 0  # statistic
        self.file_prefixes = file_prefixes or set()

        if own == -1:
            self.own = float(points)
        else:
            self.own = float(own)
        if ownwork == -1:
            self.ownwork = self.own
        else:
            self.ownwork = float(ownwork)
        self.maxinitialcount = int(maxinitialcount)

        prefixes = r'(?:%s)' % '|'.join(['%s:' % x for x in self.file_prefixes])
        suffixes = r'\.(?:svg|png|jpe?g|gif|tiff)'
        self.extlinkmatcher = re.compile(r'https?://[^ \n]*?' + suffixes, flags=re.IGNORECASE)
        imagematcher = r"""
            (?:
                (?:=|\||^)%(prefixes)s?   # "=File:", "=", "|File:", "|", ...
                | %(prefixes)s
            )
            (  # start capture
                [^\}\]\[=\|$\n]*?
                %(suffixes)s
            )  # end capture
        """ % {'prefixes': prefixes, 'suffixes': suffixes}
        logger.debug('ImageFilter regexp:')
        logger.debug(imagematcher)
        self.imagematcher = re.compile(imagematcher, flags=re.IGNORECASE | re.MULTILINE | re.VERBOSE)

    def get_images(self, txt):
        txt = self.extlinkmatcher.sub('', txt)  # remove external links to images
        # return len(re.findall(imagematcher, txt, flags=re.IGNORECASE))
        for img in self.imagematcher.finditer(txt):
            yield img.group(1).strip()

    def test(self, rev):
        imgs0 = list(self.get_images(rev.parenttext))
        imgs1 = list(self.get_images(rev.text))
        added = set(imgs1).difference(set(imgs0))

        if len(added) == 0:
            return

        counters = {'ownwork': [], 'own': [], 'other': []}
        for filename in added:
            filename = urllib.parse.unquote(filename)
            try:
                image = rev.article().site().images[filename]
            except InvalidPageTitle:
                logger.error('Image filename "%s" is invalid, ignoring this file', filename)
                continue
            imageinfo = image.imageinfo
            if len(imageinfo) > 0:   # seems like image.exists only checks locally
                try:
                    uploader = imageinfo['user']
                except KeyError:
                    logger.error("Could not locate user for file '%s' in rev. %s ",
                                 filename, rev.revid)
                    continue

                logger.debug("File '%s' uploaded by '%s', revision made by '%s'",
                             filename, uploader, rev.username)
                if uploader == rev.username:
                    credit = ''
                    extrainfo = rev.article().site().api('query', prop='imageinfo', titles=u'File:{}'.format(filename), iiprop='extmetadata')
                    try:
                        for pageid, page  in extrainfo['query']['pages'].items():
                            credit = page['imageinfo'][0]['extmetadata']['Credit']['value']
                    except KeyError:
                        logger.debug("Could not read credit info for file '%s'", filename)

                    if 'int-own-work' in credit or 'Itse otettu valokuva' in credit:
                        logger.debug("File '%s' identified as own work.", filename)
                        counters['ownwork'].append(filename)
                    else:
                        logger.debug("File '%s' identified as own upload, but not own work.", filename)
                        counters['own'].append(filename)
                else:
                    logger.debug("File '%s' not identified as own upload or own work.", filename)
                    counters['other'].append(filename)
            else:
                logger.warning("File '%s' does not exist", filename)

        # Update statistic
        self.total += len(counters['own']) + len(counters['ownwork']) + len(counters['other'])

        # If maxinitialcount is 0, only the first image counts.
        # If an user adds both an own image and an image by someone else,
        # we should make sure to credit the own image, not the other.
        # We therefore process the own images first.
        points = 0
        for n, img in enumerate(added):
            if len(imgs0) + n <= self.maxinitialcount:
                if img in counters['ownwork']:
                    points += self.ownwork
                elif img in counters['own']:
                    points += self.own
                else:
                    points += self.points

        yield UserContribution(rev=rev, rule=self, points=points,
                               description=_('images') % {'images': len(added)})


class ExternalLinkRule(Rule):

    def __init__(self, key, points, maxpoints=-1):
        Rule.__init__(self, key)
        self.points = float(points)
        self.maxpoints = float(maxpoints)

    def get_linkcount(self, txt):
        txt = re.sub(r'<ref[^>]*>.*?</ref>', '', txt, flags=re.MULTILINE)  # fjern referanser først, så vi ikke teller lenker i referanser
        return len(re.findall(r'(?<!\[)\[[^\[\] ]+ [^\[\]]+\](?!])', txt))

    def test(self, rev):

        nlinks = self.get_linkcount(rev.text)
        nlinks_p = self.get_linkcount(rev.parenttext)
        added = nlinks - nlinks_p

        if added <= 0:
            return

        points = added * self.points
        yield UserContribution(rev=rev, points=points, rule=self, description=_('links') % {'links': added})


class RefRule(Rule):

    def __init__(self, key, sourcepoints, refpoints):
        """
        sourcepoints: points for adding new sources
        refpoints: points for referring to existing sources
        """
        Rule.__init__(self, key)
        self.sourcepoints = float(sourcepoints)
        self.refpoints = float(refpoints)
        self.totalsources = 0

    def get_sourcecount(self, txt):

        s1 = 0  # kilder
        r1 = 0  # kildehenvisninger

        # Count all <ref> tags
        try:
            if txt == '':
                return 0, 0
            xml = fromstring(condition_for_lxml(re.sub(r'<!--.*?-->', '', txt, flags=re.I)))
            allref1 = xml.findall('.//ref')
            for tag in allref1:
                if tag.text is None:
                    r1 += 1
                else:
                    s1 += 1
            del xml
        except lxml.etree.XMLSyntaxError:
            s1 = 0
            r1 = 0

        # Count list item under section heading "Kilder" or "Kjelder"
        refsection = False
        for line in txt.split('\n'):
            if refsection:
                if re.match(r'==', line):
                    refsection = False
                    continue
                if re.match(r'\*', line):
                    s1 += 1
            elif re.match(r'==[\s]*(Kilder|Kjelder|Gáldut)[\s]*==', line):
                refsection = True

        return s1, r1

    def test(self, rev):

        s1, r1 = self.get_sourcecount(rev.parenttext)
        s2, r2 = self.get_sourcecount(rev.text)

        #print rev.article().name,len(allref1), len(allref2)

        sources_added = s2 - s1
        refs_added = r2 - r1

        self.totalsources += sources_added

        if sources_added <= 0 and refs_added <= 0:
            return

        p = 0.
        s = []
        if sources_added > 0:
            p += sources_added * self.sourcepoints
            s.append(_('references') % {'num': sources_added})
        if refs_added > 0:
            p += refs_added * self.refpoints
            s.append(_('reference pointers') % {'num': refs_added})
        txt = ', '.join(s)
        yield UserContribution(rev=rev, points=p, rule=self, description=txt)


class RefSectionFiRule(Rule):
    # @TODO: Generalize to "AddSectionRule"

    def __init__(self, key, points, maxpoints=-1, pattern='Lähteet|Viitteet'):
        Rule.__init__(self, key)
        self.points = float(points)
        self.maxpoints = float(maxpoints)
        self.total = 0
        self.pattern = pattern

    def has_section(self, txt):
        # Count list item under section heading "Kilder" or "Kjelder"
        refsection = False
        for line in txt.split('\n'):
            if re.match(r'==(=)?[\s]*(%s)[\s]*(=?)==' % self.pattern, line):
                refsection = True

        return refsection

    def test(self, rev):
        had_section = self.has_section(rev.parenttext)
        has_section = self.has_section(rev.text)

        if has_section and not had_section:
            self.total += 1
            yield UserContribution(rev=rev, points=self.points, rule=self, description=_('added reference section'))


class ByteBonusRule(Rule):

    def __init__(self, key, points, limit):
        Rule.__init__(self, key)
        self.points = float(points)
        self.limit = int(limit)

    def test(self, rev):
        abytes = 0
        thisrev = False
        passedlimit = False
        for r in rev.article().revisions.values():
            if r.bytes > 0:
                abytes += r.bytes
            if passedlimit is False and abytes >= self.limit:
                passedlimit = True
                if r == rev:
                    thisrev = True

        if abytes >= self.limit and thisrev is True:
            yield UserContribution(rev=rev, points=self.points, rule=self,
                                   description=_('bonus %(bytes).f bytes') % {'bytes': self.limit})


class WordBonusRule(Rule):

    def __init__(self, key, points, limit):
        Rule.__init__(self, key)
        self.points = float(points)
        self.limit = int(limit)

    def test(self, rev):

        # First check all revisions
        awords = 0
        thisrev = False
        passedlimit = False
        for r in rev.article().revisions.values():
            if r.words > 0:
                awords += r.words

            if passedlimit is False and awords >= self.limit:
                passedlimit = True
                if r == rev:
                    thisrev = True

        if awords >= self.limit and thisrev is True:
            yield UserContribution(rev=rev, points=self.points, rule=self,
                                   description=_('bonus %(words)d words') % {'words': self.limit})
