#!/usr/bin/env bash
# Countdown to 25 Sept 2026, 24:00 Anywhere on Earth (UTC-12)  ==  26 Sept 12:00 UTC
cd "$(dirname "$0")"
exec uv run badge_countdown.py --target "2026-09-25 24:00" --tz AoE "$@"
