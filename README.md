# ukbot

Bot for updating results in writing contests at Wikipedia, deployed at [ukbot.wmflabs.org](https//ukbot.wmflabs.org).
 
## Getting Started

Create a new Python3 virtualenv and activate it:

	python3 -m venv env
	. env/bin/activate

Install dependencies:

	pip install .

If installation fails on Mac, try

	LDFLAGS=-L/opt/homebrew/lib pip install .

Generate locales:

    make all

Start a MariaDB instance with the necesseary database tables:

	docker compose up -d

Create a configuration file:

	cp .env.dist .env

and modify it if needed. The default database credentials should work with the MariaDB instance from Docker, but you may need to add Wikimedia credentials ([Oauth 1.0a consumer-only credentials](https://meta.wikimedia.org/wiki/Special:OAuthConsumerRegistration/propose?wpownerOnly=1&wpoauthVersion=2))
if you want to actually run the bot locally.

Within the virtualenv you should now be able to run the bot. For testing purposes, you can create
a sandbox contest page such as this one: https://no.wikipedia.org/wiki/Bruker:Danmichaelo/Sandkasse5
and test the bot with that page:

	ukbot --page Bruker:Danmichaelo/Sandkasse5 --simulate config/config.no-mk.yml

To test the webinterface locally:

```
export FLASK_DEBUG=1
export FLASK_APP=ukbot.server
flask run
```

## Deployment

At Tool Forge:

```
python3 -m venv www/python/venv
. www/python/venv/bin/activate
webservice --backend=kubernetes python shell
pip install -e .
exit
webservice --backend=kubernetes python start
```

Setup crontab:

    crontab ukbot.crontab

## Other notes

Forenklet flytkart:
![Flowchart](https://github.com/danmichaelo/UKBot/raw/master/flowchart.png)
 