# vim: fenc=utf-8 et sw=4 ts=4 sts=4 ai
from flask import Flask
from flask import request
from flask import render_template
from flask_sockets import Sockets
from time import time
from mwclient import Site
from requests import ConnectionError
from mwtextextractor import get_body_text
import mysql.connector
from contextlib import contextmanager
import yaml
import sqlite3
from copy import copy
import os
import gevent
from gevent import Timeout
import logging

logger = logging.getLogger('app')

project_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
base_href = os.environ.get('APP_BASE_HREF', 'http://localhost:5000/')

contests = [
    {
        "id": "no",
        "name": "Ukens konkurranse",
        "url": "https://no.wikipedia.org/wiki/WP:UK",
    },
    {
        "id": "fi",
        "name": "Viikon kilpailu",
        "url": "https://fi.wikipedia.org/wiki/WP:VK",
    },
    {
        "id": "fi-pln",
        "name": "Punaisten linkkien naiset",
        "url": "https://fi.wikipedia.org/wiki/Wikiprojekti:Punaisten linkkien naiset",
    },
    {
        "id": "eu",
        "name": "Atari:Hezkuntza/Lehiaketak",
        "url": "https://eu.wikipedia.org/wiki/Atari:Hezkuntza/Lehiaketak",
    },
]


class MyConverter(mysql.connector.conversion.MySQLConverter):

    def row_to_python(self, row, fields):
        row = super(MyConverter, self).row_to_python(row, fields)

        def to_unicode(col):
            if isinstance(col, bytearray):
                return col.decode('utf-8')
            elif isinstance(col, bytes):
                return col.decode('utf-8')
            return col

        return[to_unicode(col) for col in row]


@contextmanager
def db_cursor():
    config_file = os.path.join(project_dir, 'config', 'config.no.yml')
    config = yaml.load(open(config_file, encoding='utf-8'))
    db = mysql.connector.connect(converter_class=MyConverter, **config['db'])
    cur = db.cursor()
    yield cur
    cur.close()
    db.close()


app = Flask(__name__, static_url_path='/ukbot/static')
sockets = Sockets(app)

def error_404():
    return '404'
    response = render_template('404.html')
    response.status_code = 404
    return response

def read_status(fname):
    stat = open(fname, encoding='utf-8').read()
    statspl = stat.split()

    if statspl[0] == 'running':
        stat = 'Updating now... started %d secs ago.' % (int(time()) - int(statspl[1]))
    elif statspl[0] == '0':
        stat = 'Last successful run: ' + ' '.join(statspl[2:]) + '. Runtime was ' + statspl[1] + ' seconds.'
    else:
        stat = '<em>Failed</em>'
    return stat

@app.route('/ukbot/')
def show_index():

    cf = copy(contests)
    for c in cf:
        status_file = os.path.join(project_dir, 'logs', '%s.status' % c['id'])
        c['status'] = read_status(status_file)

    return render_template('main.html',
        contests=cf,
        base_href=base_href
    )

# @app.route('/<contest>/')
# def show_contest(contest):
#     if contest not in [c['id'] for c in contests]:
#         return error_404()
#     konk = []
#     points = []

#     with db_cursor() as cur:
#         cur.execute(u'SELECT C.name, U.user, U.points, T.summedPoints FROM (SELECT users.contest, users.user, MAX(users.points) usersPoints, SUM(users.points) summedPoints FROM users GROUP BY users.contest) as T JOIN users as U ON U.points=T.usersPoints JOIN contests as C on C.name=U.contest WHERE U.lang = %s', [contest])
#         for row in cur.fetchall():
#             s = row[0].split()[-1]
#             konk.append({'id': s, 'name': row[0], 'winner': {'name': row[1], 'points': row[2]}, 'sum': {'points': row[3]}})
#             points.append('%s' % row[3])

#     return render_template('uk.html',
#             lang=contest,
#             points=','.join(points),
#             contests=konk
#         )


@app.route('/ukbot/<contest>/status')
def show_uk_log(contest):
    if contest not in [c['id'] for c in contests]:
        return error_404()

    return render_template('status.html', base_href=base_href, contest=contest)


@sockets.route('/ukbot/<contest>/status.sock')
def show_contest_status_sock(socket, contest):
    if contest not in [c['id'] for c in contests]:
        return error_404()

    run_log_file = os.path.join(project_dir, 'logs', '%s.run.log' % contest)
    app.logger.info('Opened websocket for %s', run_log_file)

    with open(run_log_file, encoding='utf-8') as run_file:
        while not socket.closed:
            new_data = run_file.read()
            if new_data:
                socket.send(new_data)
            with Timeout(0.5, False):
                socket.receive()
    app.logger.info('Closed websocket for %s', run_log_file)


# @app.route('/<lang>/contest/<week>/')
# def show_uk_contest_details(lang, week):
#     if lang not in ['no', 'fi']:
#         return error_404()

#     # TODO: Migrate to MYSQL!
#     sql = db.connect()
#     cur = sql.cursor()
#     konk = []
#     cur.execute(u'SELECT name FROM contests WHERE name LIKE ?', ['%' + week])

#     row = cur.fetchone()
#     if row:
#         name = row[0]
#         users = []
#         for row2 in cur.execute(u'select user, points, bytes, newpages from users where contest=? ORDER BY points DESC', [name]):
#             users.append({ 'name': row2[0], 'points': row2[1], 'bytes': row2[2], 'newpages': row2[3]})
#         return render_template('uk_contest_details.html',
#                                lang=lang, name=name, users=users)
#     else:
#         return error_404()

# @app.route('/<lang>/user/<user>/')
# def show_uk_user_details(lang, user):
#     if lang not in ['no', 'fi']:
#         return error_404()
#     sql = db.connect() # TODO: Migrate to MySQL
#     cur = sql.cursor()
#     konk = []
#     for row in cur.execute(u'SELECT U.contest, U.points, U.bytes, U.newpages, (SELECT COUNT(DISTINCT(users.points)) FROM users WHERE users.contest=U.contest AND users.points >= U.points) AS place, (SELECT COUNT(DISTINCT(points)) FROM users WHERE users.contest=U.contest) AS npart FROM users AS U WHERE U.user=?', [user]):
#         s = row[0].split()[-1]
#         konk.append({'id': s, 'name': row[0], 'points': row[1], 'bytes': row[2], 'newpages': row[3], 'pos': row[4], 'cnt': row[5] })

#     return render_template('uk_user_details.html',
#         lang=lang,
#         name=user,
#         contests=konk
#         )

def validate(data):
    errors = []
    if len(data.get('lang', '')) < 2 or len(data.get('lang', '')) > 3:
        errors.append('invalid_lang')
    if len(data.get('page', '')) < 1:
        errors.append('no_page')
    if len(errors) != 0:
        return None, errors
    try:
        site = Site('{}.wikipedia.org'.format(data.get('lang')))
    except ConnectionError:
        return None, ['invalid_lang']
    page = site.pages[data.get('page')]
    if not page.exists:
        return None, ['invalid_page']
    return page, errors


@app.route('/ukbot/wordcount')
def show_wordcount():
    lang = request.args.get('lang', '')
    page = request.args.get('page', '')
    revision = request.args.get('revision', '')
    args = {'lang': lang, 'page': page, 'revision': revision}
    if lang == '' or page == '':
        return render_template('wordcount.html', **args)
    mwpage, errors = validate(request.args)
    if len(errors) != 0:
        return render_template('wordcount.html',
            errors=errors, **args)

    if revision == '':
        revision = mwpage.revision
        args['revision'] = revision

    rev = next(mwpage.revisions(revision, prop='ids|content', limit=1))
    txt = rev['*']
    body = get_body_text(txt)
    return render_template('wordcount.html',
            body=body,
            base_href=base_href,
            word_count=len(body.split()),
            **args
    )

if __name__ == "__main__":
    # app.run()
    from gevent import pywsgi
    from geventwebsocket.handler import WebSocketHandler
    server = pywsgi.WSGIServer(('', 5000), app, handler_class=WebSocketHandler)
    server.serve_forever()
