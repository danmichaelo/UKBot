#!/bin/bash

rm plots/$CONTEST.mem.png
rm logs/$CONTEST.mem.log

echo "Plotting memory usage for contest: $CONTEST" | tee mem_plotter.log
sleep 1
while true; do

  # Collect data
  process_id=$(pgrep -f bin/ukbot)
  if [[ -z "$process_id" ]]; then
    # Process not found
    echo "Process not found, aborting memory usage plot"
    break
  fi
  
  # Get Virtual Memory Size (VSZ)
  ps -p $process_id -o vsz -o pmem | grep -v VSZ >> logs/$CONTEST.mem.log

  # Plot
  echo "gnuplot now"
  gnuplot mem_plotter.gnuplot 2>&1 | tee -a mem_plotter.log
  sleep 1
done &
