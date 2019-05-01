from .rule import BonusRule


class WordBonusRule(BonusRule):

    rule_name = 'wordbonus'

    def get_metric(self, rev):
        if rev.words > 0:
            return rev.words
        return 0.
