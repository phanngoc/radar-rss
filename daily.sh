#!/bin/bash
# Daily runner cho Radar RSS Chính Trị
# Dùng cho cron: 0 7 * * * /Users/ngocp/goterm-workspace/radar-rss/daily.sh

cd "$(dirname "$0")"

# Phase 1: fetch news, filter, generate HTML, cache articles
python3 radar.py >> output/radar.log 2>&1

# Phase 2: AI agent reviews classification, proposes filter improvements
# (Skipped silently if ANTHROPIC_API_KEY not set or anthropic not installed)
mkdir -p data/audit
if [ -n "$ANTHROPIC_API_KEY" ]; then
    python3 -m agent evaluate >> data/audit/agent.log 2>&1
    python3 -m agent review >> data/audit/agent.log 2>&1
fi
