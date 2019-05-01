# encoding=utf-8
# vim: fenc=utf-8 et sw=4 ts=4 sts=4 ai
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


#
# class RefSectionFiRule(Rule):
#     # @TODO: Generalize to "AddSectionRule"
#
#     rule_name = 'refsectionfi'
#
#     def __init__(self, sites, template, trans=None):
#         Rule.__init__(self, sites, template, trans)
#         self.total = 0
#         self.pattern = self.get_param('pattern', 'Lähteet|Viitteet')
#
#     def has_section(self, txt):
#         # Count list item under section heading "Kilder" or "Kjelder"
#         refsection = False
#         for line in txt.split('\n'):
#             if re.match(r'==(=)?[\s]*(%s)[\s]*(=?)==' % self.pattern, line):
#                 refsection = True
#
#         return refsection
#
#     def test(self, rev):
#         had_section = self.has_section(rev.parenttext)
#         has_section = self.has_section(rev.text)
#
#         if has_section and not had_section:
#             self.total += 1
#             yield UserContribution(rev=rev, points=self.points, rule=self, description=_('added reference section'))
#
