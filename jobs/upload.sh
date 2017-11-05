#!/bin/bash

export UKCONF=$(echo "$JOB_NAME")  #  | cut -c7-20)
projectdir=/data/project/ukbot
logfile=${projectdir}/logs/${UKCONF}.upload.log
statusfile=${projectdir}/logs/${UKCONF}.status
configfile=${projectdir}/config/config.${UKCONF}.yml

echo "-----------------------------------------------------------------"
cd ${projectdir}
echo "$(date) : Starting '$UKCONF' job ($JOB_ID) on $HOSTNAME" | tee $logfile
START=$(date +%s)

. ${projectdir}/ENV/bin/activate
cd ${projectdir}/bot

# set -o pipefail  # doesn't work when run through the task schedueler
python uploadplot.py --config "${configfile}" 2>&1 | tee -a $logfile
status="${PIPESTATUS[0]}"

echo "$(date) : Job $JOB_NAME ($JOB_ID) on $HOSTNAME finished with exit code $status" | tee -a $logfile

