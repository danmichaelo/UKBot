#!/data/project/ukbot/ENV/bin/python
import os, sys
sys.path.insert(0, '/data/project/ukbot/ENV/lib/python3.4/site-packages')

from flipflop import WSGIServer
from .webinterface.app import app

import logging
import logging.handlers

logging.basicConfig()

logger = logging.getLogger()
logger.setLevel(logging.INFO)
formatter = logging.Formatter('[%(asctime)s %(levelname)s] %(message)s')

logger.info('Flask server started')

fh = logging.StreamHandler()
fh.setLevel(logging.DEBUG)
fh.setFormatter(formatter)
app.logger.addHandler(fh)

#app.debug = True  # reload on each code change

if __name__ == '__main__':
    from gevent import pywsgi
    from geventwebsocket.handler import WebSocketHandler
    server = pywsgi.WSGIServer(('', 5000), app, handler_class=WebSocketHandler)
    server.serve_forever()

