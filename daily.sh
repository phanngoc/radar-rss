#!/bin/bash
# Daily runner cho Radar RSS Chính Trị
# Dùng cho cron: 0 7 * * * /Users/ngocp/goterm-workspace/radar-rss/daily.sh

cd "$(dirname "$0")"
python3 radar.py >> output/radar.log 2>&1
