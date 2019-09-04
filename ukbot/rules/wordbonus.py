# encoding=utf-8
# vim: fenc=utf-8 et sw=4 ts=4 sts=4 ai
from .rule import BonusRule


class WordBonusRule(BonusRule):

    rule_name = 'wordbonus'

    def get_metric(self, rev):
        if rev.words > 0:
            return rev.words
        return 0.
