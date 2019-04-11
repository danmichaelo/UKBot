from contextlib import contextmanager
import pymysql.cursors
from pymysql.err import OperationalError
import os

from dotenv import load_dotenv
load_dotenv()


class SQL(object):

    def __init__(self, config):
        self.config = config
        self.open_conn()

    def open_conn(self):
        self.conn = pymysql.connect(charset='utf8mb4', **self.config)

    def cursor(self, **kwargs):
        try:
            return self.conn.cursor(**kwargs)
        except OperationalError:
            # Can happen if the db connection times out
            self.open_conn()
            return self.conn.cursor(**kwargs)

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()


def db_conn():
    return SQL({
        'host': os.getenv('DB_HOST'),
        'db': os.getenv('DB_DB'),
        'user': os.getenv('DB_USER'),
        'password': os.getenv('DB_PASSWORD'),
    })


@contextmanager
def db_cursor():
    db = db_conn()
    cur = db.cursor()
    yield cur
    cur.close()
    db.close()
