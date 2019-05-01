from ..common import _
from ..contributions import UserContribution
from .rule import Rule


class ContribRule(Rule):

    rule_name = 'contrib'

    def test(self, rev):
        yield UserContribution(rev=rev, points=self.points, rule=self.rule,
                               description=_('contribution'))
