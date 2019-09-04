# encoding=utf-8
# vim: fenc=utf-8 et sw=4 ts=4 sts=4 ai
import re
import json
import logging
from jsonpath_rw import parse
from ..common import _, ngettext
from ..contributions import UserContribution
from .rule import Rule
from .decorators import family

logger = logging.getLogger(__name__)


class WikidataRule(Rule):

    rule_name = 'wikidata'

    def __init__(self, sites, params, trans=None):
        """
        sourcepoints: points for adding new sources
        refpoints: points for referring to existing sources
        """

        Rule.__init__(self, sites, params, trans)

        self.properties = self.get_param('properties', datatype=list, default=[])
        self.properties = [re.sub('[^P0-9]', '', property.upper()) for property in self.properties]
        self.require_reference = self.get_param('require_reference', datatype=bool, default=False)

        self.jps = {}
        for prop in self.properties:
            if self.require_reference:
                self.jps[prop] = [parse('claims.%s[*].references[0]' % prop)]
            else:
                self.jps[prop] = [
                    parse('claims.%s' % prop),
                    parse('claims.*.qualifiers.%s' % prop),
                ]

    def count_statements(self, txt):
        data = json.loads(txt)
        out = {}
        for prop, jps in self.jps.items():
            n = 0
            for jp in jps:
                matches = jp.find(data)
                n += len(matches)
            out[prop] = n

        return out

    @family('wikidata.org')
    def test(self, rev):
        try:
            statements_before = self.count_statements(rev.parenttext)
            statements_after = self.count_statements(rev.text)
        except json.decoder.JSONDecodeError:
            logger.error('Failed to parse Wikidata revision %s' % rev.revid)

            return
        statements_added = {}
        report = {}

        for prop in self.jps.keys():
            statements_added[prop] = statements_after[prop] - statements_before[prop]
            if statements_added[prop] > 0:
                report[prop] = statements_added[prop]

        if len(report.keys()) > 0:
            points = 0
            description = []

            for prop, n in report.items():
                points += n * self.points
                description.append(
                    ngettext(
                        '%(count)d %(property)s statement',
                        '%(count)d %(property)s statements',
                        n
                    ) % {
                        'count': n,
                        'property': prop,
                    }
                )

            yield UserContribution(rev=rev, points=points, rule=self,
                                   description=', '.join(description))
