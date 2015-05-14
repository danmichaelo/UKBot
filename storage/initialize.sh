#!/bin/bash

USER=s51083

mysql --defaults-file="${HOME}"/replica.my.cnf -h tools-db << END

DROP DATABASE IF EXISTS ${USER}__ukbot ;
CREATE DATABASE ${USER}__ukbot ;

END

mysql --defaults-file="${HOME}"/replica.my.cnf -h tools-db ${USER}__ukbot < baseline.sql

