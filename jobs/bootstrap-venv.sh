#!/bin/bash

set -euo pipefail

# create the venv
if [ -d www/python/venv ]; then
    echo "Removing old venv"
    rm -r www/python/venv
fi

echo "Creating new venv ($(python3 --version))"
mkdir -p www/python/venv
python3 -m venv www/python/venv

# activate it
source www/python/venv/bin/activate

# upgrade pip inside the venv and add support for the wheel package format
pip install -U pip wheel

# install packages
pip install -e . --upgrade
