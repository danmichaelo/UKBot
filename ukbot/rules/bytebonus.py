from .rule import BonusRule


class ByteBonusRule(BonusRule):

    rule_name = 'bytebonus'

    def get_metric(self, rev):
        if rev.bytes > 0:
            return rev.bytes
        return 0.
