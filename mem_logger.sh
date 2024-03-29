#!/bin/bash

if [ ! -d /proc ]; then
  echo "/proc not found, memory usage will not be monitored"
  exit 0
fi

echo "Monitoring memory usage for contest: $CONTEST"

rm -f "plots/$JOB_ID.mem.png"
rm -f "logs/$JOB_ID.mem.log"

while true; do
  # Collect data
  mem_total=$(awk '( $1 == "MemTotal:" ) { print $2/1024 }' /proc/meminfo)
  mem_active=$(awk '( $1 == "Active:" ) { print $2/1024 }' /proc/meminfo)
  mem_available=$(awk '( $1 == "MemAvailable:" ) { print $2/1024 }' /proc/meminfo)
  echo "$(date +%Y-%m-%dT%H:%M:%S.%3N),$mem_active,$mem_available,$mem_total" >> "logs/$JOB_ID.mem.log"
  sleep 1
done
