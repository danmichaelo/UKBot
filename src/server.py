#!/data/project/ukbot/ENV/bin/python
import os, sys
sys.path.insert(0, '/data/project/ukbot/ENV/lib/python3.4/site-packages')

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
    from gevent import pywsgi, socket
    from geventwebsocket.handler import WebSocketHandler

    PORT=int(os.environ.get('PORT'))  # Tool Forge tells us what port we can use
    listener = ('', PORT)

    server = pywsgi.WSGIServer(listener, app, handler_class=WebSocketHandler)
    server.serve_forever()



