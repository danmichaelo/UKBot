set term png small size 400,300
set output "plots/`echo $CONTEST`.mem.png"

set ylabel "VSZ"
set y2label "%MEM"

set ytics nomirror
set y2tics nomirror in

set yrange [0:*]
set y2range [0:*]

plot "logs/`echo $CONTEST`.mem.log" using 1 with lines axes x1y1 title "VSZ", \
     "logs/`echo $CONTEST`.mem.log" using 2 with lines axes x1y2 title "%MEM"
