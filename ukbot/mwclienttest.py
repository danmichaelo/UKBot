# encoding=utf-8
import mwclient

mysite = mwclient.Site('no.wikipedia.org')
print(mysite.host.split('.'))