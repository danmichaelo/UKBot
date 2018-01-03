UKBot
=====

Python bot for updating results in Ukens konkurranse and similar contests at Wikipedia.
* [user page at no.wp](//no.wikipedia.org/wiki/Bruker:UKBot)
* [at tool labs](//tools.wmflabs.org/ukbot/)

Setup
-----

Make a [virtualenv](http://www.virtualenv.org/) with Python 3,
and install dependencies:

	virtualenv ENV --no-site-packages -p /Users/danmichael/.pyenv/shims/python3
	. ENV/bin/activate

	pip install -r requirements.txt

To generate locales:

    make all

And setup crontab:

    crontab ukbot.crontab

Forenklet flytkart:
![Flowchart](https://github.com/danmichaelo/UKBot/raw/master/flowchart.png)


