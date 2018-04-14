from contextlib import contextmanager
import mysql.connector
import yaml

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


class SQL(object):

    def __init__(self, config):
        self.config = config
        self.open_conn()

    def open_conn(self):
        self.conn = mysql.connector.connect(converter_class=MyConverter, **self.config)

    def cursor(self, **kwargs):
        try:
            return self.conn.cursor(**kwargs)
        except mysql.connector.errors.OperationalError:
            # Seems like this can happen if the db connection times out
            self.open_conn()
            return self.conn.cursor(**kwargs)

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()


@contextmanager
def db_cursor(config_file):
    with open(config_file, encoding='utf-8') as fp:
        config = yaml.load(fp)
    db = SQL(config['db'])
    cur = db.cursor()
    yield cur
    cur.close()
    db.close()
