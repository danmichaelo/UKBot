#encoding=utf-8
# run twice a day, at 12.30 and 00.30

from __future__ import unicode_literals

import sys, os, datetime
import mwclient
import locale
for loc in ['nb_NO.UTF-8', 'nb_NO.utf8', 'no_NO']:
    try:
        locale.setlocale(locale.LC_TIME, loc.encode('utf-8'))
        #logger.info('Locale set to %s' % loc)
        break
    except locale.Error:
        pass

now = datetime.datetime.now()

# If we run at midnight, then upload the results of last day
if now.hour == 0:
    now -= datetime.timedelta(hours=1)

year, week, day = now.isocalendar()
weekstart = now - datetime.timedelta(days = day-1)

kpage = 'Wikipedia:Ukens konkurranse/Ukens konkurranse %s' % now.strftime('%Y-%V')
no = mwclient.Site('no.wikipedia.org')
pp = no.api('query', prop = 'pageprops', titles = kpage, redirects = '1')
if 'redirects' in pp['query']:
    kpage = pp['query']['redirects'][0]['to']

yearweek = kpage.split()[-1]
filename = 'Nowp Ukens konkurranse %s.svg' % yearweek

if not os.path.isfile(filename):
    sys.stderr.write('File "%s" was not found\n' % filename)
    sys.exit(1)

pagetext = """== {{int:filedesc}} ==
{{Information
|Description    = {{no|1=Resultater for [[:no:Wikipedia:Ukens konkurranse/Ukens konkurranse %(yearweek)s|Ukens konkurranse uke %(week)s, %(year)s]]}}
{{en|1=Results from the weekly article writing contest at Norwegian Bokmål/Nynorsk Wikipedia [[:no:Wikipedia:Ukens konkurranse/Ukens konkurranse %(yearweek)s|week %(week)s, %(year)s]]}}
|Source         = {{own}}
|Date           = %(weekstart)s
|Author         = [[User:UKBot|UKBot]]
}}

== {{int:license-header}} ==
{{PD-self}}

[[Category:Ukens konkurranse]]""" % { 'yearweek': yearweek, 'week': now.strftime('%V'), 'year': now.strftime('%Y'), 'weekstart' : weekstart.strftime('%F') }

from wp_private import ukbotlogin
commons = mwclient.Site('commons.wikimedia.org')
commons.login(*ukbotlogin)

p = commons.pages['File:' + filename]
f = open(filename, 'rb')
if p.exists:
    commons.upload(f, filename, comment = 'Bot: Updating plot', ignore = True)
else:
    commons.upload(f, filename, comment = 'Bot: Uploading new "Ukens konkurranse" plot at week-start', description = pagetext)
f.close()

