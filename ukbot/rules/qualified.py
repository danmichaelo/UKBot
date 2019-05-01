from ..common import _
from ..contributions import UserContribution
from .rule import Rule


class QualiRule(Rule):

    rule_name = 'qualified'

    def __init__(self, sites, template, trans=None):
        Rule.__init__(self, sites, template, trans)
        self.articles_seen = set()

    def test(self, rev):
        if rev.article().key not in self.articles_seen:
            self.articles_seen.add(rev.article().key)
            yield UserContribution(rev=rev, points=self.points, rule=self,
                                   description=_('qualified'))
