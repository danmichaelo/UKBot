#!/bin/bash

export CONTEST=$(echo "$JOB_NAME")  #  | cut -c7-20)
projectdir=/data/project/ukbot
logfile=${projectdir}/logs/${CONTEST}.run.log
statusfile=${projectdir}/logs/${CONTEST}.status

echo "-----------------------------------------------------------------"
cd ${projectdir}
echo "$(date) : Starting '$CONTEST' job ($JOB_ID) on $HOSTNAME." | tee $logfile
START=$(date +%s)
echo "running $START" >| $statusfile

# Start mem logger
./mem_logger.sh &

. ${projectdir}/ENV/bin/activate

cd ${projectdir}/bot
# set -o pipefail  # doesn't work when run through the task schedueler
python ukbot.py --contest "${CONTEST}" "$@" 2>&1 | tee -a $logfile
status="${PIPESTATUS[0]}"

echo "$(date) : Job $JOB_NAME ($JOB_ID) on $HOSTNAME finished with exit code $status" | tee -a $logfile
END=$(date +%s)
DIFF=$(( $END - $START ))
echo "$status $DIFF $(date)" >| $statusfile
