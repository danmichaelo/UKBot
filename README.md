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

    10 * * * * jsub -j y -cwd -N ukbot_no -mem 384m -o logs/no.log jobs/update.sh
    15 * * * * jsub -j y -cwd -N ukbot_no -mem 384m -o logs/no.log jobs/close.sh
    30 21 * * * jsub -j y -cwd -N ukbot_no -mem 384m -o logs/no.log jobs/upload.sh
    20 * * * * jsub -j y -cwd -N ukbot_fi -mem 384m -o logs/fi.log jobs/update.sh
    25 * * * * jsub -j y -cwd -N ukbot_fi -mem 384m -o logs/fi.log jobs/close.sh
    35 21 * * * jsub -j y -cwd -N ukbot_fi -mem 384m -o logs/no.log jobs/upload.sh

Forenklet flytkart:
![Flowchart](https://github.com/danmichaelo/UKBot/raw/master/flowchart.png)


