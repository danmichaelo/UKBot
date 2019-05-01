from ..common import _
from ..contributions import UserContribution
from .rule import Rule


class RedirectRule(Rule):

    rule_name = 'redirect'

    def test(self, rev):
        if rev.new and rev.redirect:
            yield UserContribution(rev=rev, points=self.points, rule=self, description=_('redirect'))
