#!/bin/bash

# Remove files not modified in the last 10 days
find /data/project/ukbot/logs -mtime +10 -type f -delete
find /data/project/ukbot/plots -mtime +10 -type f -delete
