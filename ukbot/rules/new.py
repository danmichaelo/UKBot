from ..common import _
from ..contributions import UserContribution
from .rule import Rule


class NewPageRule(Rule):

    rule_name = 'new'

    def test(self, rev):
        if rev.new and not rev.redirect:
            yield UserContribution(rev=rev, points=self.points, rule=self, description=_('new page'))
