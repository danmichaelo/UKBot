#!/bin/sh
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
if [ ! -f "$DIR/uk.db" ]; then
    echo "Creating uk.db from baseline.sql"
    sqlite3 "$DIR/uk.db" < "$DIR/baseline.sql"
else
    echo "uk.db already exists"
fi
