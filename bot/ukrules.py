#encoding=utf-8
from __future__ import unicode_literals
import re
from lxml.html import fromstring
import lxml
from mwtemplates import TemplateEditor
from mwtextextractor import condition_for_lxml
from ukcommon import init_localization

t, _ = init_localization()


class Rule(object):

    def __init__(self, key):
        self.key = key

    def iszero(self, f):
        f = float(f)
        return (f > -0.1 and f < 0.1)

    def add_points(self, rev, points, ptype, txt, pmax, include_zero=False):

        ab = rev.article.get_points(ptype)
        ab_raw = rev.article.get_points(ptype, ignore_max=True)

        if pmax > 0.0 and self.iszero(ab - pmax):
            # we have reached max
            if points < 0.0 and ab_raw + points < pmax:
                rev.points.append([pmax - ab_raw - points, ptype, txt, points])
            else:
                rev.points.append([0.0, ptype, txt, points])

        elif pmax > 0.0 and ab + points > pmax:
            # reaching max
            rev.points.append([pmax - ab, ptype, txt + ' &gt; ' + _('max'), points])

        #elif not self.iszero(revpoints):
        else:
            if self.iszero(points) and not include_zero:
                return
            rev.points.append([points, ptype, txt, points])


class NewPageRule(Rule):

    def __init__(self, key, points):
        Rule.__init__(self, key)
        self.points = float(points)

    def test(self, rev):
        if rev.new and not rev.redirect:
            rev.points.append([self.points, 'newpage', _('new page')])


class RedirectRule(Rule):

    def __init__(self, key, points):
        Rule.__init__(self, key)
        self.points = float(points)

    def test(self, rev):
        if rev.new and rev.redirect:
            rev.points.append([self.points, 'redirect', _('redirect')])

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
#             rev.article.errors.append(_('Encountered a problem while parsing [%(url)s rev. %(revid)d] : %(error)s' % { 'url': rev.get_link(), 'revid': rev.revid, 'error': e.msg })


class TemplateRemovalRule(Rule):

    def __init__(self, key, points, template, aliases=[]):
        Rule.__init__(self, key)
        self.points = float(points)
        self.template = template.lower()
        self.aliases = [a.lower() for a in aliases]
        self.total = 0

    def testtpl(self, name):
        name = name.lower()
        for tpl in self.aliases + [self.template]:
            if tpl[0] == '*' and tpl[-1] == '*' and name.find(tpl[1:-1]) != -1:
                return True
            elif tpl[0] == '*' and name.endswith(tpl[1:]):
                return True
            elif tpl[-1] == '*' and name.startswith(tpl[:-1]):
                return True
            elif name == tpl:
                return True
        return False

    def templatecount(self, text):
        """ Checks if a given text has the template"""

        dp = TemplateEditor(text)
        tc = 0
        for node in dp.templates.doc.findall('.//template'):
            for elem in node:
                if elem.tag == 'title':
                    if self.testtpl(elem.text):
                        tc += 1
 #       for tpl in dp.templates._templates():
            #if self.testtpl(tpl.name) or tpl.name in self.aliases:
#            tc += 1
        #for tpl in dp.templates:
            #tc += len(tpl)
        #    pass
        #     if self.testtpl(tname) or tname in self.aliases:
        #         tc += len(templ)
        # del dp
        return tc

    def test(self, rev):
        if rev.redirect or rev.parentredirect:
            # skip redirects
            return
        pt = self.templatecount(rev.parenttext)
        ct = self.templatecount(rev.text)
        if ct < pt:
            rev.points.append([(pt - ct) * self.points, 'templateremoval',
                              _('removal of {{tl|%(template)s}}') % {'template': self.template}])
            self.total += (pt - ct)


class QualiRule(Rule):

    def __init__(self, key, points):
        Rule.__init__(self, key)
        self.points = float(points)

    def test(self, rev):
        if self.iszero(rev.article.get_points('quali')):
            rev.points.append([self.points, 'quali', _('qualified')])


class ByteRule(Rule):

    def __init__(self, key, points, maxpoints=-1):
        Rule.__init__(self, key)
        self.points = float(points)
        self.maxpoints = float(maxpoints)

    def test(self, rev):
        revpoints = rev.bytes * self.points
        if revpoints > 0.:
            self.add_points(rev, revpoints, 'byte',
                            _('%(bytes).f bytes') % {'bytes': rev.bytes},
                            self.maxpoints, include_zero=True)


class WordRule(Rule):

    def __init__(self, key, points, maxpoints=-1):
        Rule.__init__(self, key)
        self.points = float(points)
        self.maxpoints = float(maxpoints)

    def test(self, rev):

        words = rev.words
        revpoints = words * self.points
        if revpoints > 0.:
            self.add_points(rev, revpoints, 'word',
                            _('%(words).f words') % {'words': words},
                            self.maxpoints)


class ImageRule(Rule):

    def __init__(self, key, points, maxpoints=-1):
        Rule.__init__(self, key)
        self.points = float(points)
        self.maxpoints = float(maxpoints)

    def get_imagecount(self, txt):
        return len(re.findall(r'(?:\.svg|\.png|\.jpg|\.jpeg|\.gif|\.tiff)', txt, flags=re.IGNORECASE))

    def test(self, rev):

        nimages = self.get_imagecount(rev.text)
        nimages_p = self.get_imagecount(rev.parenttext)
        imgs = nimages - nimages_p

        if imgs > 0:
            revpoints = imgs * self.points
            self.add_points(rev, revpoints, 'image', '%d %s' % (imgs, _('images') if imgs > 1 else _('image')), self.maxpoints)


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
        links = nlinks - nlinks_p

        if links > 0:
            revpoints = links * self.points
            self.add_points(rev, revpoints, 'link', '%d %s' % (links, _('links') if links > 1 else _('link')), self.maxpoints)


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
            xml = fromstring(condition_for_lxml(txt))
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
            elif re.match('==[\s]*(Kilder|Kjelder|Gáldut)[\s]*==', line):
                refsection = True

        return s1, r1

    def test(self, rev):

        s1, r1 = self.get_sourcecount(rev.parenttext)
        s2, r2 = self.get_sourcecount(rev.text)

        #print rev.article.name,len(allref1), len(allref2)

        sources_added = s2 - s1
        refs_added = r2 - r1

        self.totalsources += sources_added

        if sources_added > 0 or refs_added > 0:
            p = 0.
            s = []
            if sources_added > 0:
                p += sources_added * self.sourcepoints
                s.append(t.ungettext('one reference', '%(num)d references', sources_added) % {'num': sources_added})
            if refs_added > 0:
                p += refs_added * self.refpoints
                s.append(t.ungettext('one reference pointer', '%(num)d reference pointers', refs_added) % {'num': refs_added})
            txt = ', '.join(s)

            rev.points.append([p, 'ref', txt])

class RefSectionFiRule(Rule):

    def __init__(self, key, points):
        Rule.__init__(self, key)
        self.points = float(points)
        self.totalrefsectionsadded = 0

    def has_ref_section(self, txt):

        refsec = False

        # Count list item under section heading "Kilder" or "Kjelder"
        refsection = False
        for line in txt.split('\n'):
            if re.match('==(=)?[\s]*(Lähteet|Viitteet)[\s]*(=?)==', line):
                refsection = True

        return refsection

    def test(self, rev):

        r1 = self.has_ref_section(rev.parenttext)
        r2 = self.has_ref_section(rev.text)

        if not r1 and r2:
            rev.points.append([self.points, 'refsection', _('added reference section')])
            self.totalrefsectionsadded += 1


class ByteBonusRule(Rule):

    def __init__(self, key, points, limit):
        Rule.__init__(self, key)
        self.points = float(points)
        self.limit = int(limit)

    def test(self, rev):
        abytes = 0
        thisrev = False
        passedlimit = False
        for r in rev.article.revisions.itervalues():
            if r.bytes > 0:
                abytes += r.bytes
            if passedlimit is False and abytes >= self.limit:
                passedlimit = True
                if r == rev:
                    thisrev = True

        if abytes >= self.limit and thisrev is True:
            rev.points.append([self.points, 'bytebonus', _('bonus %(bytes).f bytes') % {'bytes': self.limit}])


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
        for r in rev.article.revisions.itervalues():
            if r.words > 0:
                awords += r.words

            if passedlimit is False and awords >= self.limit:
                passedlimit = True
                if r == rev:
                    thisrev = True

        if awords >= self.limit and thisrev is True:
            rev.points.append([self.points, 'wordbonus',
                              _('bonus %(words)d words') % {'words': self.limit}])
