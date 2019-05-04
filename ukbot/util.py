import re
import sys
import unicodedata
import logging
import os
import yaml

logger = logging.getLogger(__name__)
control_char_re = None  # lazy-load


def cleanup_input(value):
    global control_char_re

    if not isinstance(value, str):
        return value

    if control_char_re is None:
        logger.info('Preparing control char regexp...')
        all_chars = (chr(i) for i in range(sys.maxunicode))
        control_chars = ''.join(c for c in all_chars if unicodedata.category(c) in set(['Cc','Cf']))
        control_char_re = re.compile('[%s]' % re.escape(control_chars))
        logger.info('Control char regexp is ready')

    value = value.strip()
    value = re.sub(r'<\!--.+?-->', r'', value)
    value = control_char_re.sub('', value)

    return value


class YamlLoader(yaml.SafeLoader):

    def __init__(self, stream):

        self._root = os.path.split(stream.name)[0]

        super(YamlLoader, self).__init__(stream)

    def include(self, node):

        filename = os.path.join(self._root, self.construct_scalar(node))

        with open(filename, encoding='utf-8') as fp:
            return yaml.load(fp, YamlLoader)

YamlLoader.add_constructor('!include', YamlLoader.include)

def load_config(fp):
    return yaml.load(fp, YamlLoader)
