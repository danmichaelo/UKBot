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
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
      ],
      install_requires=[
        'Jinja2',
        'Werkzeug',
        'pytz',
        'isoweek',
        'odict',
        'pyyaml',
        'lxml',
        'beautifulsoup4',
        'numpy',
        'matplotlib<3.0',
        'mwclient',
        'mwtemplates',
        'mwtextextractor',
        'datetime',
        'rollbar',
        'flipflop',
        'flask',
        'flask-sockets',
        'requests',
        'mysql-connector==2.1.6',
        'psutil',
        'python-dotenv',
      ],
      setup_requires=pytest_runner,
      tests_require=['pytest', 'pytest-pep8', 'pytest-cache', 'pytest-cov',
                     'responses>=0.3.0', 'responses!=0.6.0', 'mock'],
      zip_safe=True
      )
