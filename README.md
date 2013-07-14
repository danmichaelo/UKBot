UKBot
=====

Python bot for updating results in Ukens konkurranse and similar contests at Wikipedia.
* [user page at no.wp](//no.wikipedia.org/wiki/Bruker:UKBot)
* [at tool labs](//tools.wmflabs.org/ukbot/)

Setup
-----
Making a [virtualenv](http://www.virtualenv.org/) and installing dependencies (numpy should be installed first, then the rest in no particular order):

	virtualenv ENV
	source ENV/bin/activate

	pip install numpy 
	pip install -r requirements.txt
	pip install 

To generate locales:
````
make all
```` 

Current crontab:

	PPATH="/data/project/ukbot"
	STDOPTS="-q task -hard -j yes"
	10 * * * * qsub -N ukbot_no $STDOPTS -l h_vmem=384m -o $PPATH/logs/no.log $PPATH/jobs/update.sh
	15 * * * * qsub -N ukbot_no $STDOPTS -l h_vmem=384m -o $PPATH/logs/no.log $PPATH/jobs/close.sh
	20 * * * * qsub -N ukbot_fi $STDOPTS -l h_vmem=384m -o $PPATH/logs/fi.log $PPATH/jobs/update.sh
	25 * * * * qsub -N ukbot_fi $STDOPTS -l h_vmem=384m -o $PPATH/logs/fi.log $PPATH/jobs/close.sh
	45 */2 * * * qsub -N ukbot_fi-hl $STDOPTS -l h_vmem=1024m -o $PPATH/logs/fi-hl.log $PPATH/jobs/update.sh
	03 21 * * * qsub -N ukbot_fi-hl $STDOPTS -l h_vmem=256m -o $PPATH/logs/fi-hl.log $PPATH/jobs/upload.sh


Forenklet flytkart:
![Flowchart](https://github.com/danmichaelo/UKBot/raw/master/flowchart.png)


