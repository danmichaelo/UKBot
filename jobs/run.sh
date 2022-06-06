#!/bin/bash

# Set some UTF-8 locale to get the UTF-8 in logs and filenames.
export LANG=en_US.utf8
export LC_ALL=en_US.utf8

CONTEST=$1
JOB_ID=$(cat /proc/sys/kernel/random/uuid)

logfile=logs/${CONTEST}_${JOB_ID}.log
statusfile=logs/${CONTEST}.status.json

echo "$(date) Starting ukbot - contest=$CONTEST job=$JOB_ID pwd=$(pwd)"
echo "-----------------------------------------------------------------"
echo "$(date) : Starting job contest=$CONTEST id=$JOB_ID host=$HOSTNAME" > $logfile

START=$(date +%s)
printf '{"status": "running", "update_date": "%s", "job_id": "%s"}' "${START}" "${JOB_ID}" >| $statusfile

cleanup() {
    echo "Cleaning up..."
    # Stop mem logger
    kill 0  # https://unix.stackexchange.com/a/67552/275042
    exit
}
trap cleanup INT TERM

# Start mem logger
JOB_ID=$JOB_ID ./mem_logger.sh &

. www/python/venv/bin/activate

# set -o pipefail  # doesn't work when run through the task schedueler
stdbuf -oL -eL ukbot config/config.${CONTEST}.yml --job_id ${JOB_ID} >> $logfile 2>&1
status="${PIPESTATUS[0]}"

echo "$(date) : Job finished contest=$CONTEST id=$JOB_ID host=$HOSTNAME exit_code=$status" >> $logfile
NOW=$(date +%s)
DIFF=$(( $NOW - $START ))
printf '{"status": "%s", "update_date": "%s", "job_id": "%s", "runtime": %s}' "${status}" "${NOW}" "${JOB_ID}" "${DIFF}" >| $statusfile
