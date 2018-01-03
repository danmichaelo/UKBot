# vim: fenc=utf-8 et sw=4 ts=4 sts=4 ai
from flask import Flask
from flask import request
from flask import render_template
from flask_socketio import SocketIO
from time import time
from mwclient import Site
from requests import ConnectionError
from mwtextextractor import get_body_text
import mysql.connector
from contextlib import contextmanager
import yaml
import sqlite3
from copy import copy

configs = [
    {
        "id": "no",
        "name": "Ukens konkurranse",
    },
    {
        "id": "fi",
        "name": "Viikon kilpailu",
    },
    {
        "id": "fi-100",
        "name": "Suomi 100",
    },
]


class MyConverter(mysql.connector.conversion.MySQLConverter):

    def row_to_python(self, row, fields):
        row = super(MyConverter, self).row_to_python(row, fields)

        def to_unicode(col):
            if type(col) == bytearray:
                return col.decode('utf-8')
            return col

        return[to_unicode(col) for col in row]

@contextmanager
def db_cursor():
    config = yaml.load(open('/data/project/ukbot/config/config.no.yml', 'r'))
    db = mysql.connector.connect(converter_class=MyConverter, **config['db'])
    cur = db.cursor()
    yield cur
    cur.close()
    db.close()


app = Flask(__name__)
socketio = SocketIO(app)

def error_404():
    return '404'
    response = render_template('404.html')
    response.status_code = 404
    return response

def read_status(fname):
    stat = open(fname).read().decode('utf-8')
    statspl = stat.split()

    if statspl[0] == 'running':
        stat = 'Updating now... started %d secs ago.' % (int(time()) - int(statspl[1])) 
    elif statspl[0] == '0':
        stat = 'Last successful run: ' + ' '.join(statspl[2:]) + '. Runtime was ' + statspl[1] + ' seconds.'
    else:
        stat = '<em>Failed</em>'
    return stat

@app.route('/')
def show_index():

    cf = copy(configs)
    for c in cf:
        c['status'] = read_status('/data/project/ukbot/logs/%s.status' % c['id'])

    return render_template('main.html',
        configs=cf
    )

@app.route('/<conf>/')
def show_uk_list(conf):
    if conf not in [c['id'] for c in configs]:
        return error_404()
    konk = []
    points = []

    with db_cursor() as cur:
        cur.execute(u'SELECT C.name, U.user, U.points, T.summedPoints FROM (SELECT users.contest, users.user, MAX(users.points) usersPoints, SUM(users.points) summedPoints FROM users GROUP BY users.contest) as T JOIN users as U ON U.points=T.usersPoints JOIN contests as C on C.name=U.contest WHERE U.lang = %s', [conf])
        for row in cur.fetchall():
            s = row[0].split()[-1]
            konk.append({'id': s, 'name': row[0], 'winner': {'name': row[1], 'points': row[2]}, 'sum': {'points': row[3]}})
            points.append('%s' % row[3])

    return render_template('uk.html',
            lang=conf,
            points=','.join(points),
            contests=konk
        )

@sockets.route('/<conf>/status.sock')
def show_uk_log_sock(ws, conf):
    if conf not in [c['id'] for c in configs]:
        return error_404()
    
    data = open('/data/project/ukbot/logs/%s.run.log' % conf).read().decode('utf-8')
    while not ws.closed:
        # message = ws.receive()
        ws.send(data)


@app.route('/<conf>/status')
def show_uk_log(conf):
    if conf not in [c['id'] for c in configs]:
        return error_404()

    return render_template('status.html',
            data=''
        )


@app.route('/<lang>/contest/<week>/')
def show_uk_contest_details(lang, week):
    if lang not in ['no', 'fi']:
        return error_404()
    sql = sqlite3.connect('/data/project/ukbot/storage/%s.db' % lang)
    cur = sql.cursor()
    konk = []
    cur.execute(u'SELECT name FROM contests WHERE name LIKE ?', ['%' + week])

    row = cur.fetchone()
    if row:
        name = row[0]
        users = []
        for row2 in cur.execute(u'select user, points, bytes, newpages from users where contest=? ORDER BY points DESC', [name]):
            users.append({ 'name': row2[0], 'points': row2[1], 'bytes': row2[2], 'newpages': row2[3]})
        return render_template('uk_contest_details.html',
                               lang=lang, name=name, users=users)
    else:
        return error_404()

@app.route('/<lang>/user/<user>/')
def show_uk_user_details(lang, user):
    if lang not in ['no', 'fi']:
        return error_404()
    sql = sqlite3.connect('/data/project/ukbot/storage/%s.db' % lang)
    cur = sql.cursor()
    konk = []
    for row in cur.execute(u'SELECT U.contest, U.points, U.bytes, U.newpages, (SELECT COUNT(DISTINCT(users.points)) FROM users WHERE users.contest=U.contest AND users.points >= U.points) AS place, (SELECT COUNT(DISTINCT(points)) FROM users WHERE users.contest=U.contest) AS npart FROM users AS U WHERE U.user=?', [user]):
        s = row[0].split()[-1]
        konk.append({'id': s, 'name': row[0], 'points': row[1], 'bytes': row[2], 'newpages': row[3], 'pos': row[4], 'cnt': row[5] })

    return render_template('uk_user_details.html',
        lang=lang,
        name=user,
        contests=konk
        )

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


@app.route('/wordcount')
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
            word_count=len(body.split()),
            **args
    )

if __name__ == "__main__":
    # app.run()
    socketio.run(app)
