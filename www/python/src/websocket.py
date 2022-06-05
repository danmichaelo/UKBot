import uwsgi
import os
import re
import time
import logging
from pathlib import Path

logging.basicConfig(format='%(asctime)s %(levelname)-8s %(message)s', level=logging.INFO)
logger = logging.getLogger('websockets')

project_dir = Path(__file__).parent.parent.parent.parent.resolve()


def app(env, start_response):
    uwsgi.websocket_handshake(env['HTTP_SEC_WEBSOCKET_KEY'], env.get('HTTP_ORIGIN', ''))
    logger.info(f"New websocket connection: {env['PATH_INFO']}")
    job_id = env['PATH_INFO'].split("/").pop()

    contest_id, job_id = job_id.rsplit('_', 1)
    contest_id = re.sub('[^0-9a-z_-]', '', contest_id)
    job_id = re.sub('[^0-9a-zA-Z-]', '', job_id)
    log_file = project_dir.joinpath('logs', f'{contest_id}_{job_id}.log')

    if not os.path.isfile(log_file):
        logger.error(f"Log not found: {log_file}")
        uwsgi.websocket_send('The requested log does not exist')
        return

    status_file = project_dir.joinpath('logs', f'{contest_id}.status.json')
    logger.info(f"Opened websocket for {log_file}")

    # Use line-buffering (buffering=1) so that we never send incomplete lines
    close_next_time = False
    with open(log_file, buffering=1, encoding='utf-8') as stream:
        n = 0
        while True:
            try:
                # Handle ping/pong, but don't block
                uwsgi.websocket_recv_nb()

                new_data = stream.read()
                if new_data != '':
                    uwsgi.websocket_send(new_data)
                    if 'finished with exit' in new_data:
                        logger.info(f"Completed streaming log: {log_file}")
                        return
                
                if close_next_time:
                    logger.info(f"Completed streaming log: {log_file}")
                    return
            except IOError as err:
                logger.info('WebSocket connection closed by client')
                print(err)
                return
            if n % 10 == 0:
                try:
                    with open(status_file) as fp:
                        status = json.load(fp)
                        if int(status['job_id']) == job_id and status['status'] != 'running':
                            close_next_time = True
                except:
                    pass
            n += 1
            time.sleep(1)

