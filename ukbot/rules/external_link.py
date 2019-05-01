import re

from ..common import _
from ..contributions import UserContribution
from .rule import Rule


class ExternalLinkRule(Rule):

    rule_name = 'external_link'

    @staticmethod
    def count_links(txt):
        # We don't want to include links in references as these are covered by the RefRule
        txt = re.sub(r'<ref[^>]*>.*?</ref>', '', txt, flags=re.MULTILINE)
        return len(re.findall(r'(?<!\[)\[[^\[\] ]+ [^\[\]]+\](?!])', txt))

    def test(self, rev):
        links_before = self.count_links(rev.parenttext)
        links_after = self.count_links(rev.text)
        links_added = links_after - links_before

        if links_added > 0:
            points = links_added * self.points
            yield UserContribution(rev=rev, points=points, rule=self,
                                   description=_('links') % {'links': links_added})
