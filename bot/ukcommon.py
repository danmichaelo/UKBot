# encoding=utf-8
from __future__ import unicode_literals
import sys
import locale
import gettext
import yaml
import os
import psutil

import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


# Singleton
class Localization:
    class __Localization:
        def __init__(self):
            self.t = lambda x: x
            self._ = lambda x: x

        def init(self, cl, project_dir):
            '''prepare i18n'''
            if not isinstance(cl, list):
                cl = [cl]
                #['nb_NO.UTF-8', 'nb_NO.utf8', 'no_NO']:
            for loc in cl:
                try:
                    # print "Trying (", loc.encode('utf-8'), 'utf-8',")"
                    locale.setlocale(locale.LC_ALL, (loc, 'utf-8'))
                    logger.info('Using locale %s', loc)
                    #logger.info('Locale set to %s' % loc)
                    break
                except locale.Error:
                    try:
                        locstr = loc + '.UTF-8'
                        # print "Trying",locstr
                        locale.setlocale(locale.LC_ALL, locstr )
                        logger.info('Using locale %s', loc)
                        break
                    except locale.Error:
                        pass

            lang, charset = locale.getlocale()
            if lang == None:
                raise StandardError('Failed to set locale!')

            localedir = os.path.join(project_dir, 'locale')
            t = gettext.translation('messages', localedir, fallback=True, languages=[lang])

            self.t = t
            self._ = t.gettext

    instance = None
    def __init__(self):
        if not Localization.instance:
            Localization.instance = Localization.__Localization()
        # else:
        #    Localization.instance.val = arg

    def __getattr__(self, name):
        return getattr(self.instance, name)


localization = Localization()

def t(*args, **kwargs):
    return localization.t(*args, **kwargs)

def _(*args, **kwargs):
    return localization._(*args, **kwargs)

logfile = sys.stdout
def log(msg, newline = True):
    if newline:
        msg = msg + '\n'
    logfile.write(msg.encode('utf-8'))
    logfile.flush()


process = psutil.Process(os.getpid())

def get_mem_usage():
    """ Returns memory usage in MBs """
    return process.memory_info().rss / 1024.**2
