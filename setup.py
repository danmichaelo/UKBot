#!/usr/bin/env python
# encoding=utf-8
from setuptools import setup
import os, sys

needs_pytest = set(['pytest', 'test', 'ptr']).intersection(sys.argv)
pytest_runner = ['pytest-runner'] if needs_pytest else []

setup(name='ukbot',
      version='1.0.0',
      description='Wikipedia writing contest bot',
      keywords='wikipedia',
      author='Dan Michael O. Heggø',
      author_email='danmichaelo@gmail.com',
      url='https://github.com/danmichaelo/ukbot',
      license='MIT',
      packages=['ukbot'],
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
        'odict',
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
      ],
      setup_requires=pytest_runner,
      tests_require=['pytest', 'pytest-pep8', 'pytest-cache', 'pytest-cov',
                     'responses>=0.3.0', 'responses!=0.6.0', 'mock'],
      zip_safe=True
      )
