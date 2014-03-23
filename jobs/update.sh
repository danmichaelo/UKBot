#!/bin/sh
cd /data/project/ukbot
echo "-----------------------------------------------------------------"
echo "$(date) : Starting UPDATE job $JOB_NAME ($JOB_ID) on $HOSTNAME"
export UKLANG=$(echo "$JOB_NAME" | cut -c7-20)
START=$(date +%s)
echo "running $START" >| logs/$UKLANG.status
./mem_logger.sh &
. /data/project/ukbot/ENV/bin/activate
cd /data/project/ukbot/bot

python ukbot.py --config ../config/config.$UKLANG.yml

status=$?
cd /data/project/ukbot
echo "$(date) : Job $JOB_NAME ($JOB_ID) on $HOSTNAME finished with exit code $status"
END=$(date +%s)
DIFF=$(( $END - $START ))
echo "$status $DIFF $(date)" >| logs/$UKLANG.status
