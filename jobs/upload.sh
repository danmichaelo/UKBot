#!/bin/bash

export CONTEST=$(echo "$JOB_NAME")  #  | cut -c7-20)
projectdir=/data/project/ukbot
logfile=${projectdir}/logs/${CONTEST}.upload.log
statusfile=${projectdir}/logs/${CONTEST}.status

echo "-----------------------------------------------------------------"
cd ${projectdir}
echo "$(date) : Starting '$CONTEST' job ($JOB_ID) on $HOSTNAME" | tee $logfile
START=$(date +%s)

. ${projectdir}/ENV/bin/activate

cd ${projectdir}/bot
# set -o pipefail  # doesn't work when run through the task schedueler
python ukbot.py --contest "${CONTEST}" --action "uploadplot" "$@" 2>&1 | tee -a $logfile
status="${PIPESTATUS[0]}"

echo "$(date) : Job $JOB_NAME ($JOB_ID) on $HOSTNAME finished with exit code $status" | tee -a $logfile

