#!/bin/bash

rm plots/$UKCONF.mem.png
rm logs/$UKCONF.mem.log

echo "Plotting $UKCONF..." | tee mem_plotter.log
while true; do  

  # Collect data
  process_id=`id -u | xargs ps -u | grep python | awk '{print $1}'`
  if [[ -z "$process_id" ]]; then
    # Process not found
    break
  fi
  
  # Get Virtual Memory Size (VSZ)
  ps -p $process_id -o vsz -o pmem | grep -v VSZ >> logs/$UKCONF.mem.log

  # Plot
  gnuplot mem_plotter.gnuplot 2>&1 | tee -a mem_plotter.log
  sleep 1
done &
