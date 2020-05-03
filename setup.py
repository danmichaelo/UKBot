#!/usr/bin/env python
# encoding=utf-8
from setuptools import setup, find_packages
import os, sys

setup(name='ukbot',
      version='1.0.0',
      description='Wikipedia writing contest bot',
      keywords='wikipedia',
      author='Dan Michael O. Heggø',
      author_email='danmichaelo@gmail.com',
      url='https://github.com/danmichaelo/ukbot',
      license='MIT',
      packages=find_packages(),
      include_package_data=True,
      entry_points={
        'console_scripts': [
            'ukbot = ukbot.ukbot:main',
        ],
      },
      classifiers=[
        'Programming Language :: Python',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
      ],
      install_requires=[
        'Jinja2',
        'Werkzeug',
        'pytz',
        'isoweek',
        'pyyaml',
        'jsonpath-rw',
        'lxml',
        'beautifulsoup4',
        'numpy',
        'matplotlib<3.0',
        'mwclient',
        'mwtemplates',
        'mwtextextractor',
        'rollbar',
        'flipflop',
        'flask',
        # 'Flask-uWSGI-WebSocket',  See https://github.com/zeekay/flask-uwsgi-websocket/pull/73
        'requests',
        'pymysql',
        'psutil',
        'python-dotenv',
        'pydash',
        'retry',
        'more-itertools',
      ])
