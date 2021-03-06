#!/bin/bash

# Set some UTF-8 locale to get the UTF-8 in logs and filenames.
export LANG=en_US.utf8
export LC_ALL=en_US.utf8

export CONTEST=$(echo "$JOB_NAME")  #  | cut -c7-20)
projectdir=/data/project/ukbot
logfile=logs/${CONTEST}_${JOB_ID}.log
statusfile=logs/${CONTEST}.status.json

echo "-----------------------------------------------------------------"
cd "${projectdir}"
echo "$(date) : Starting '$CONTEST' job ($JOB_ID) on $HOSTNAME." | tee $logfile

START=$(date +%s)
printf '{"status": "running", "update_date": "%s", "job_id": "%s"}' "${START}" "${JOB_ID}" >| $statusfile

# Start mem logger
./mem_logger.sh &

. www/python/venv/bin/activate

# set -o pipefail  # doesn't work when run through the task schedueler
stdbuf -oL -eL ukbot config/config.${CONTEST}.yml "$@" --job_id ${JOB_ID} 2>&1 | tee -a ${logfile}
status="${PIPESTATUS[0]}"

echo "$(date) : Job $JOB_NAME ($JOB_ID) on $HOSTNAME finished with exit code $status" | tee -a $logfile
NOW=$(date +%s)
DIFF=$(( $NOW - $START ))
printf '{"status": "%s", "update_date": "%s", "job_id": "%s", "runtime": %s}' "${status}" "${NOW}" "${JOB_ID}" "${DIFF}" >| $statusfile
