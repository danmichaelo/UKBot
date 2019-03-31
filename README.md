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

Webinterface
------------

At Tool Forge:
```
python3 -m venv www/python/venv
. www/python/venv/bin/activate
webservice --backend=kubernetes python shell
pip install -e .
exit
webservice --backend=kubernetes python start
```

To test the webinterface locally:

```
export FLASK_DEBUG=1
export FLASK_APP=ukbot/server.py
flask run
```
