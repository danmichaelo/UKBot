#!/usr/bin/python

import cgitb
cgitb.enable()
#print 'Content-type: text/html; charset=utf-8\n'

import sqlite3

import logging
import logging.handlers
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter('[%(asctime)s %(levelname)s] %(message)s')

fh = logging.FileHandler('main.log')
fh.setLevel(logging.DEBUG)
fh.setFormatter(formatter)
logger.addHandler(fh)

import os, sys
sys.path.insert(0, '/data/project/ukbot/ENV/lib/python2.7/site-packages')
#sys.path.insert(0, '/data/project/ukbot/ukbot')

from time import time

from jinja2 import Environment, FileSystemLoader
template_path = os.path.join(os.path.dirname(__file__), 'templates')
jinja_env = Environment(loader=FileSystemLoader(template_path), autoescape=True)

from werkzeug.wrappers import Response
from werkzeug.contrib.fixers import CGIRootFix
from werkzeug.routing import Map, Rule, NotFound, RequestRedirect
from werkzeug.utils import redirect
from werkzeug.contrib.fixers import CGIRootFix
from wsgiref.handlers import CGIHandler
# Note: renamed from LighttpdCGIRootFix

#print "Hello labs\n"
#print "Request: %s" % os.environ['REQUEST_URI']

#for param in os.environ.keys():
#    print "%20s: %s" % (param, os.environ[param])

#os.environ['PYWIKIBOT2_DIR'] = '/path/to/my/config'
#import pywikibot


#print 
#from mwtextextractor import get_body_text
#print get_body_text("Lorem {{ipsum}} dolor")

#p.revisions(startid=12362467, limit=1, prop='content|timestamp').next()['*']

def read_status(fname):
    stat = open(fname).read()
    statspl = stat.split()

    if statspl[0] == 'running':
        stat = 'Updating now... started %d secs ago.' % (int(time()) - int(statspl[1])) 
    elif statspl[0] == '0':
        stat = 'Last successful run: ' + ' '.join(statspl[2:]) + '. Runtime was ' + statspl[1] + ' seconds.'
    else:
        stat = '<em>Failed</em>'
    return stat


def render_template(template_name, **context):
    t = jinja_env.get_template(template_name)
    return Response(t.render(context), mimetype='text/html')


def get_index(args):
    logger.info('GET_INDEX')
    return render_template('main.html',
        status_no=read_status('../logs/no.status'),
        status_fi=read_status('../logs/fi.status'),
        status_fi_ek=read_status('../logs/fi-ek.status')
    )


def get_uk_list(args):
    if args['lang'] not in ['no', 'fi']:
        return error_404()
    sql = sqlite3.connect('../storage/%s.db' % args['lang'])
    cur = sql.cursor()
    konk = []
    points = []
    for row in cur.execute(u'SELECT C.name, U.user, U.points, T.summedPoints FROM (SELECT users.contest, users.user, MAX(users.points) usersPoints, SUM(users.points) summedPoints FROM users GROUP BY users.contest) as T JOIN users as U ON U.points=T.usersPoints JOIN contests as C on C.name=U.contest'):
        s = row[0].split()[-1]
        konk.append({'id': s, 'name': row[0], 'winner': {'name': row[1], 'points': row[2]}, 'sum': {'points': row[3]}})
        points.append('%s' % row[3])
    #logger.info(konk)
    return render_template('uk.html',
                           lang=args['lang'],
                           points=','.join(points),
                           contests=konk
                           )


def get_uk_contest_details(args):
    if args['lang'] not in ['no', 'fi']:
        return error_404()
    sql = sqlite3.connect('../storage/%s.db' % args['lang'])
    cur = sql.cursor()
    konk = []
    if 'week' in args:
        cur.execute(u'SELECT name FROM contests WHERE name LIKE ?', ['%' + args['week']])
    elif 'user' in args:
        cur.execute(u'SELECT contest FROM users WHERE user=?', [args['user']])
    else:
        return error_404()

    row = cur.fetchone()
    if row:
        name = row[0]
        users = []
        for row2 in cur.execute(u'select user, points, bytes, newpages from users where contest=? ORDER BY points DESC', [name]):
            users.append({ 'name': row2[0], 'points': row2[1], 'bytes': row2[2], 'newpages': row2[3]})
        return render_template('uk_contest_details.html',
                               lang=args['lang'], name=name, users=users)
    else:
        return error_404()

def get_uk_user_details(args):
    if args['lang'] not in ['no', 'fi']:
        return error_404()
    sql = sqlite3.connect('../storage/%s.db' % args['lang'])
    cur = sql.cursor()
    konk = []
    for row in cur.execute(u'SELECT U.contest, U.points, U.bytes, U.newpages, (SELECT COUNT(DISTINCT(users.points)) FROM users WHERE users.contest=U.contest AND users.points >= U.points) AS place, (SELECT COUNT(DISTINCT(points)) FROM users WHERE users.contest=U.contest) AS npart FROM users AS U WHERE U.user=?', [args['user']]):
        s = row[0].split()[-1]
        konk.append({'id': s, 'name': row[0], 'points': row[1], 'bytes': row[2], 'newpages': row[3], 'pos': row[4], 'cnt': row[5] })

    return render_template('uk_user_details.html',
        lang=args['lang'],
        name=args['user'],
        contests=konk
        )


def hello_vk():
    return 'Hello World2!'


def error_404():
    response = render_template('404.html')
    response.status_code = 404
    return response

url_map = Map([
    Rule('/', endpoint='get_index'),
    Rule('/<lang>/', endpoint='get_uk_list'),
    Rule('/<lang>/contest/<week>', endpoint='get_uk_contest_details'),
    Rule('/<lang>/user/<user>', endpoint='get_uk_user_details'),
    ], default_subdomain='tools')


def application(environ, start_response):
    #logger.info(environ)
    environ['SCRIPT_NAME'] = '/ukbot'
    try:
        urls = url_map.bind_to_environ(environ, server_name='wmflabs.org', subdomain='tools')
        endpoint, args = urls.match()
        logger.info(args)
        response = globals()[endpoint](args)
        return response(environ, start_response)
    except NotFound, e:
        response = error_404()
        return response(environ, start_response)
    except RequestRedirect, e:
        logger.info('Redir to: %s' % e.new_url)
        response = redirect(e.new_url)
        return response(environ, start_response)

    except HTTPException, e:
        logger.error(e)
        return e(environ, start_response)
    #logger.info(args)
    #return ['Rule points to %r with arguments %r' % (endpoint, args)]


try:
    CGIHandler().run(application)
except Exception as e:
    logger.exception('Unhandled Exception')
