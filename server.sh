#!/bin/sh
export APP_BASE_HREF=https://tools.wmflabs.org/ukbot/
. ENV/bin/activate
python -m ukbot.server
