#encoding=utf-8
# run twice a day, at 12.30 and 00.30

from __future__ import unicode_literals

import sys, os 
from datetime import datetime, timedelta
import mwclient
import yaml
import pytz
import locale
from ukcommon import init_localization
import argparse
# Read args

parser = argparse.ArgumentParser( description = 'The UKBot' )
parser.add_argument('--config', nargs='?', default='config.yml', help='Config file')
args = parser.parse_args()

config = yaml.load(open(args.config, 'r'))
wiki_tz = pytz.timezone(config['wiki_timezone'])
server_tz = pytz.timezone(config['server_timezone'])

_ = init_localization(config['locale'])

runstart = server_tz.localize(datetime.now())
#log('UKBot-uploader starting at %s (server time), %s (wiki time)' % (runstart.strftime('%F %T'), runstart.astimezone(wiki_tz).strftime('%F %T')))

now = datetime.now()

# If we run at midnight, then upload the results of last day
if now.hour == 0:
    now -= timedelta(hours=1)

year, week, day = now.isocalendar()
weekstart = now - timedelta(days = day-1)

kpage = '%s %s' % (config['pages']['base'], now.strftime('%Y-%V'))
no = mwclient.Site(config['homesite'])
pp = no.api('query', prop = 'pageprops', titles = kpage, redirects = '1')
if 'redirects' in pp['query']:
    kpage = pp['query']['redirects'][0]['to']

yearweek = kpage.split()[-1]
yearweek = yearweek.split('-')
filename = config['plot']['figname'] % {'year': int(yearweek[0]), 'week': int(yearweek[1])}
remote_filename = filename.replace(' ', '_')
filename = '../plots/' + filename

if not os.path.isfile(filename):
    sys.stderr.write('File "%s" was not found\n' % filename)
    sys.exit(1)

pagetext = config['plot']['description'] % { 'yearweek': yearweek, 'week': now.strftime('%V'), 'year': now.strftime('%Y'), 'weekstart': weekstart.strftime('%F') }

commons = mwclient.Site('commons.wikimedia.org')
commons.login(config['account']['user'], config['account']['pass'])

p = commons.pages['File:' + filename]
f = open(filename, 'rb')

if p.exists:
    print "updating plot"
    print commons.upload(f, remote_filename, comment='Bot: Updating plot', ignore=True)
else:
    print "adding plot"
    print commons.upload(f, remote_filename, comment='Bot: Uploading new "Ukens konkurranse" plot at week-start', description=pagetext, ignore=True)
f.close()

