from .byte import ByteRule
from .bytebonus import ByteBonusRule
from .contrib import ContribRule
from .external_link import ExternalLinkRule
from .image import ImageRule
from .new import NewPageRule
from .qualified import QualiRule
from .redirect import RedirectRule
from .ref import RefRule
from .templateremoval import TemplateRemovalRule
from .word import WordRule
from .wordbonus import WordBonusRule

rule_classes = [
    ByteRule,
    ByteBonusRule,
    ContribRule,
    ExternalLinkRule,
    ImageRule,
    NewPageRule,
    QualiRule,
    RedirectRule,
    RefRule,
    # RefSectionFiRule,
    TemplateRemovalRule,
    WordRule,
    WordBonusRule,
]
