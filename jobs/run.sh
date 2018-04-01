#!/bin/bash

export CONTEST=$(echo "$JOB_NAME")  #  | cut -c7-20)
projectdir=/data/project/ukbot
logfile=logs/${CONTEST}.run.log
statusfile=logs/${CONTEST}.status

echo "-----------------------------------------------------------------"
cd "${projectdir}"
echo "$(date) : Starting '$CONTEST' job ($JOB_ID) on $HOSTNAME." | tee $logfile
START=$(date +%s)
echo "running $START" >| $statusfile

# Start mem logger
./mem_logger.sh &

. ENV/bin/activate

# set -o pipefail  # doesn't work when run through the task schedueler
ukbot config/config.${CONTEST}.yml "$@" 2>&1 | tee -a $logfile
status="${PIPESTATUS[0]}"

echo "$(date) : Job $JOB_NAME ($JOB_ID) on $HOSTNAME finished with exit code $status" | tee -a $logfile
END=$(date +%s)
DIFF=$(( $END - $START ))
echo "$status $DIFF $(date)" >| $statusfile
