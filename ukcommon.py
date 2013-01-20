#encoding=utf-8
from __future__ import unicode_literals
import sys
import locale
import gettext
import yaml

logfile = sys.stdout
def log(msg, newline = True):
    if newline:
        msg = msg + '\n'
    logfile.write(msg.encode('utf-8'))
    logfile.flush()

def init_localization(cl = ''):
    '''prepare i18n'''
    if cl != '':
        if type(cl) != list:
            cl = [cl]
            #['nb_NO.UTF-8', 'nb_NO.utf8', 'no_NO']:
        for loc in cl:
            try:
                print "Trying (", loc.encode('utf-8'), 'utf-8',")"
                locale.setlocale(locale.LC_ALL, (loc.encode('utf-8'), 'utf-8'))
                log('Using locale %s' % loc)
                #logger.info('Locale set to %s' % loc)
                break
            except locale.Error:
                try:
                    locstr = (loc + '.UTF-8').encode('utf-8')
                    print "Trying",locstr
                    locale.setlocale(locale.LC_ALL, locstr )
                    log('Using locale %s' % loc)
                    break
                except locale.Error:
                    pass
    lang, charset = locale.getlocale()
    if lang == None:
        raise StandardError("Failed to set locale!")
    trans = gettext.translation('messages', 'locale', fallback=True, languages=[lang])
    return trans.ugettext
