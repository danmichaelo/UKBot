from ..common import _
from ..contributions import UserContribution
from .rule import Rule


class WordRule(Rule):

    rule_name = 'word'

    def test(self, rev):
        words_added = rev.words

        if words_added > 0.:
            points = words_added * self.points
            yield UserContribution(rev=rev, points=points, rule=self,
                                   description=_('%(words).f words') % {'words': words_added})
