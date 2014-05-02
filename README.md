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

    make all

And setup crontab:

    crontab ukbot.crontab

Forenklet flytkart:
![Flowchart](https://github.com/danmichaelo/UKBot/raw/master/flowchart.png)


