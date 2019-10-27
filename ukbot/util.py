from datetime import datetime
import re
import sys
import unicodedata
import logging
import os

import pytz
import yaml

logger = logging.getLogger(__name__)
control_char_re = None  # lazy-load


def unix_time(dt):
    """ OS-independent method to get unix time from a datetime object (strftime('%s') does not work on solaris) """
    epoch = pytz.utc.localize(datetime.utcfromtimestamp(0))
    delta = dt - epoch
    return delta.total_seconds()


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


def merge(source, destination):
    """
    Simple dict merge

    >>> a = { 'first' : { 'all_rows' : { 'pass' : 'dog', 'number' : '1' } } }
    >>> b = { 'first' : { 'all_rows' : { 'fail' : 'cat', 'number' : '5' } } }
    >>> merge(b, a) == { 'first' : { 'all_rows' : { 'pass' : 'dog', 'fail' : 'cat', 'number' : '5' } } }
    True
    """
    for key, value in source.items():
        if isinstance(value, dict):
            # get node or create one
            node = destination.setdefault(key, {})
            merge(value, node)
        else:
            destination[key] = value

    return destination


def load_config(fp):
    folder = os.path.split(fp.name)[0]

    main_config = yaml.safe_load(fp)
    if '_extends' in main_config:
        filename = os.path.join(folder, main_config['_extends'])
        with open(filename, encoding='utf-8') as fp2:
            base_config = yaml.safe_load(fp2)
    else:
        base_config = {}

    return merge(base_config, main_config)
