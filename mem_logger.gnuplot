set term png small size 400,300
set output "plots/`echo $JOB_ID`.mem.png"

set ylabel "kB"
set ytics nomirror
set yrange [0:*]

plot "logs/`echo $JOB_ID`.mem.log" using 1 with lines axes x1y1 title "Active", \
     "logs/`echo $JOB_ID`.mem.log" using 2 with lines axes x1y1 title "Available"
