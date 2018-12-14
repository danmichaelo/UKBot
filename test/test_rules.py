# encoding=utf-8
import unittest
import time
import mock
from ukbot.rules import RefRule
from ukbot.ukbot import Revision
from ukbot.contributions import Contribution


class TestRefRule(unittest.TestCase):

    @mock.patch('ukbot.ukbot.Revision')
    def test_it_yields_nothing_by_default(self, rev):
        rev.text = '<root>Hello</root>'
        rev.parenttext = '<root>Hello world</root>'
        rule = RefRule('citation', 10, 20)
        contribs = list(rule.test(rev))

        assert len(contribs) == 0

    @mock.patch('ukbot.ukbot.Revision')
    def test_it_recognizes_addition_of_ref_tags(self, rev):
        rev.text = '<root>Hello <ref>world</ref><ref>other</ref></root>'
        rev.parenttext = '<root>Hello</root>'
        rule = RefRule('citation', sourcepoints=100, refpoints=1)
        contribs = list(rule.test(rev))

        assert len(contribs) == 1
        assert isinstance(contribs[0], Contribution)
        assert contribs[0].rev == rev
        assert contribs[0].points == 100 * 2

    @mock.patch('ukbot.ukbot.Revision')
    def test_it_ignores_refs_within_comments(self, rev):
        rev.text = '<root>Hello <!-- <ref>world</ref> --></root>'
        rev.parenttext = '<root>Hello</root>'
        rule = RefRule('citation', sourcepoints=100, refpoints=1)
        contribs = list(rule.test(rev))

        assert len(contribs) == 0


if __name__ == '__main__':
    unittest.main()
