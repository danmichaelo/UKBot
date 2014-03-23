#encoding=utf-8
# run twice a day, at 12.30 and 00.30

from __future__ import unicode_literals

import sys, os 
import re
from datetime import datetime, timedelta
from datetime import time as dt_time
from isoweek import Week  # Sort-of necessary until datetime supports %V, see http://bugs.python.org/issue12006
                          # and See http://stackoverflow.com/questions/5882405/get-date-from-iso-week-number-in-python
import mwclient
import yaml
import pytz
import locale
from ukcommon import init_localization, log
import argparse
# Read args
from mwtemplates import TemplateEditor

parser = argparse.ArgumentParser( description = 'The UKBot' )
parser.add_argument('--config', nargs='?', default='config.yml', help='Config file')
parser.add_argument('--page', required=False, help='Name of the contest page to work with')
parser.add_argument('--filename', nargs='?', help='Filename to upload, if empty it is found from the current date')
args = parser.parse_args()

config = yaml.load(open(args.config, 'r'))
wiki_tz = pytz.timezone(config['wiki_timezone'])
server_tz = pytz.timezone(config['server_timezone'])


def unix_time(dt):
    """ OS-independent method to get unix time from a datetime object (strftime('%s') does not work on solaris) """
    epoch = pytz.utc.localize(datetime.utcfromtimestamp(0))
    delta = dt - epoch
    return delta.total_seconds()

_ = init_localization(config['locale'])

runstart = server_tz.localize(datetime.now())
#log('UKBot-uploader starting at %s (server time), %s (wiki time)' % (runstart.strftime('%F %T'), runstart.astimezone(wiki_tz).strftime('%F %T')))

host = config['homesite']
homesite = mwclient.Site(host)

now = server_tz.localize(datetime.now())

if args.page is not None:
    ktitle = args.page.decode('utf-8')
else:
    log('  No page specified. Using default page')
    ktitle = config['pages']['default']
    # subtract one hour, so we close last week's contest right after midnight
    #ktitle = (now - timedelta(hours=1)).astimezone(wiki_tz).strftime(ktitle.encode('utf-8')).decode('utf-8')
    ktitle = config['pages']['default']
    w = Week.withdate((now - timedelta(hours=1)).astimezone(wiki_tz).date())
    # subtract one hour, so we close last week's contest right after midnight
    ktitle = ktitle % { 'year': w.year, 'week': w.week }

# Is ktitle redirect? Resolve

log('@ ktitle is %s' % ktitle)
pp = homesite.api('query', prop='pageprops', titles=ktitle, redirects='1')
if 'redirects' in pp['query']:
    ktitle = pp['query']['redirects'][0]['to']
    log('  -> Redirected to:  %s' % ktitle)

kpage = homesite.pages[ktitle]
if not kpage.exists:
    log('  !! kpage does not exist! Exiting')
    sys.exit(0)

ibcfg = config['templates']['infobox']
commonargs = config['templates']['commonargs']

dp = TemplateEditor(kpage.edit(readonly=True))
try:
    infoboks = dp.templates[ibcfg['name']][0]
except:
    log(' !! Fant ikke infoboks!')
    sys.exit(0)

if infoboks.has_param(commonargs['year']) and infoboks.has_param(commonargs['week']):
    year = int(re.sub(ur'<\!--.+?-->', ur'', unicode(infoboks.parameters[commonargs['year']])).strip())
    startweek = int(re.sub(ur'<\!--.+?-->', ur'', unicode(infoboks.parameters[commonargs['week']])).strip())
    if infoboks.has_param(commonargs['week2']):
        endweek = re.sub(ur'<\!--.+?-->', ur'', unicode(infoboks.parameters[commonargs['week2']])).strip()
        if endweek == '':
            endweek = startweek
    else:
        endweek = startweek
    endweek = int(endweek)

    startweek = Week(year, startweek)
    endweek = Week(year, endweek)
    start = wiki_tz.localize(datetime.combine(startweek.monday(), dt_time(0, 0, 0)))
    end = wiki_tz.localize(datetime.combine(endweek.sunday(), dt_time(23, 59, 59)))
elif infoboks.has_param(ibcfg['start']) and infoboks.has_param(ibcfg['end']):
    startdt = infoboks.parameters[ibcfg['start']].value
    enddt = infoboks.parameters[ibcfg['end']].value
    start = wiki_tz.localize(datetime.strptime(startdt + ' 00 00 00', '%Y-%m-%d %H %M %S'))
    end = wiki_tz.localize(datetime.strptime(enddt + ' 23 59 59', '%Y-%m-%d %H %M %S'))
else:
    log('!! fant ikke datoer')
    sys.exit(0)

year = start.isocalendar()[0]
startweek = start.isocalendar()[1]
endweek = end.isocalendar()[1]

figname = config['plot']['figname'] % {'year': year, 'week': startweek}

log('Filename is ' + figname)


remote_filename = figname.replace(' ', '_')
filename = '../plots/' + figname

if not os.path.isfile(filename.encode('utf-8')):
    sys.stderr.write('File "%s" was not found\n' % filename.encode('utf-8'))
    sys.exit(1)

weeks = '%d' % startweek
if startweek != endweek:
    weeks += "-%s" % endweek
pagetext = config['plot']['description'] % { 'pagename': ktitle, 'week': weeks, 'year': year, 'start': start.strftime('%F') }

commons = mwclient.Site('commons.wikimedia.org')
commons.login(config['account']['user'], config['account']['pass'])

p = commons.pages['File:' + remote_filename]
f = open(filename.encode('utf-8'), 'rb')

if p.exists:
    print "updating plot"
    print commons.upload(f, remote_filename, comment='Bot: Updating plot', ignore=True)
else:
    print "adding plot"
    print commons.upload(f, remote_filename, comment='Bot: Uploading new "Ukens konkurranse" plot at week-start', description=pagetext, ignore=True)
f.close()

