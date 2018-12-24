import re
import sys
import unicodedata
import logging

logger = logging.getLogger(__name__)
all_chars = (chr(i) for i in range(sys.maxunicode))
control_chars = ''.join(c for c in all_chars if unicodedata.category(c) in set(['Cc','Cf']))
control_char_re = re.compile('[%s]' % re.escape(control_chars))
logger.info('Control char regexp is ready')


def cleanup_input(value):
    if not isinstance(value, str):
        return value

    value = value.strip()
    value = re.sub(r'<\!--.+?-->', r'', value)
    value = control_char_re.sub('', value)

    return value
