#!/bin/bash

# Set some UTF-8 locale to get the UTF-8 in logs and filenames.
export LANG=en_US.utf8
export LC_ALL=en_US.utf8

export CONTEST=$(echo "$JOB_NAME")  #  | cut -c7-20)
projectdir=/data/project/ukbot
logfile=logs/${CONTEST}.upload.log

echo "-----------------------------------------------------------------"
cd "${projectdir}"
echo "$(date) : Starting '$CONTEST' job ($JOB_ID) on $HOSTNAME" | tee $logfile
START=$(date +%s)

. ENV/bin/activate

# set -o pipefail  # doesn't work when run through the task schedueler
ukbot config/config.${CONTEST}.yml --action "uploadplot" "$@" 2>&1 | tee -a $logfile
status="${PIPESTATUS[0]}"

echo "$(date) : Job $JOB_NAME ($JOB_ID) on $HOSTNAME finished with exit code $status" | tee -a $logfile

