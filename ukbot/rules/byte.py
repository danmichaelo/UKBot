from ..common import _
from ..contributions import UserContribution
from .rule import Rule


class ByteRule(Rule):

    rule_name = 'byte'

    def test(self, rev):
        bytes_added = rev.bytes

        if bytes_added > 0.:
            points = bytes_added * self.points
            yield UserContribution(rev=rev, points=points, rule=self,
                                   description=_('%(bytes).f bytes') % {'bytes': bytes_added})
