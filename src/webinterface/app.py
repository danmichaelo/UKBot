from __future__ import absolute_import
from __future__ import division
from __future__ import unicode_literals

from flask import Flask
from flask import render_template
from time import time

import sqlite3

app = Flask(__name__)

def error_404():
    return '404'
    response = render_template('404.html')
    response.status_code = 404
    return response

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

@app.route('/')
def show_index():
    return render_template('main.html',
        status_no=read_status('/data/project/ukbot/logs/no.status'),
        status_fi=read_status('/data/project/ukbot/logs/fi.status')
    )

@app.route('/<lang>/')
def show_uk_list(lang):
    if lang not in ['no', 'fi']:
        return error_404()
    sql = sqlite3.connect('/data/project/ukbot/storage/%s.db' % lang)
    cur = sql.cursor()
    konk = []
    points = []
    for row in cur.execute(u'SELECT C.name, U.user, U.points, T.summedPoints FROM (SELECT users.contest, users.user, MAX(users.points) usersPoints, SUM(users.points) summedPoints FROM users GROUP BY users.contest) as T JOIN users as U ON U.points=T.usersPoints JOIN contests as C on C.name=U.contest'):
        s = row[0].split()[-1]
        konk.append({'id': s, 'name': row[0], 'winner': {'name': row[1], 'points': row[2]}, 'sum': {'points': row[3]}})
        points.append('%s' % row[3])
    return render_template('uk.html',
            lang=lang,
            points=','.join(points),
            contests=konk
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

if __name__ == "__main__":
    app.run()
