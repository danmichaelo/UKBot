# encoding=utf-8
# vim: fenc=utf-8 et sw=4 ts=4 sts=4 ai
from .rule import BonusRule


class ByteBonusRule(BonusRule):

    rule_name = 'bytebonus'

    def get_metric(self, rev):
        if rev.bytes > 0:
            return rev.bytes
        return 0.
