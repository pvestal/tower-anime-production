#!/bin/bash
# Sequential batch generation: Rosa → Fury → TDD → CGS → rest
set -e
cd /opt/anime-studio
LOG_DIR=/opt/anime-studio/logs
TS=$(date +%Y%m%d_%H%M%S)

echo "=== Batch generation started at $(date) ==="

# Rosa (project 59) — 9 pending, test with content LoRAs
echo "=== Starting Rosa (project 59) at $(date) ==="
python3 -m jobs.overnight_batch --project 59 --skip-keyframes --max-regens 1 \
    > "$LOG_DIR/rosa_batch_${TS}.log" 2>&1
echo "Rosa done."

# Fury (project 57) — 53 pending, has content LoRAs
echo "=== Starting Fury (project 57) at $(date) ==="
python3 -m jobs.overnight_batch --project 57 --skip-keyframes --max-regens 1 \
    > "$LOG_DIR/fury_batch_${TS}.log" 2>&1
echo "Fury done."

# TDD (project 24) — 141 pending
echo "=== Starting TDD (project 24) at $(date) ==="
python3 -m jobs.overnight_batch --project 24 --skip-keyframes --max-regens 1 \
    > "$LOG_DIR/tdd_batch_${TS}.log" 2>&1
echo "TDD done."

# CGS (project 42) — 119 pending
echo "=== Starting CGS (project 42) at $(date) ==="
python3 -m jobs.overnight_batch --project 42 --skip-keyframes --max-regens 1 \
    > "$LOG_DIR/cgs_batch_${TS}.log" 2>&1
echo "CGS done."

# Echo Chamber (project 43) — 202 pending
echo "=== Starting Echo Chamber (project 43) at $(date) ==="
python3 -m jobs.overnight_batch --project 43 --skip-keyframes --max-regens 1 \
    > "$LOG_DIR/echo_chamber_batch_${TS}.log" 2>&1
echo "Echo Chamber done."

# Scramble City (project 61) — 125 pending
echo "=== Starting Scramble City (project 61) at $(date) ==="
python3 -m jobs.overnight_batch --project 61 --skip-keyframes --max-regens 1 \
    > "$LOG_DIR/scramble_city_batch_${TS}.log" 2>&1
echo "Scramble City done."

# Small Wonders (project 58) — 40 pending
echo "=== Starting Small Wonders (project 58) at $(date) ==="
python3 -m jobs.overnight_batch --project 58 --skip-keyframes --max-regens 1 \
    > "$LOG_DIR/small_wonders_batch_${TS}.log" 2>&1
echo "Small Wonders done."

# Mira (project 60) — 26 pending
echo "=== Starting Mira (project 60) at $(date) ==="
python3 -m jobs.overnight_batch --project 60 --skip-keyframes --max-regens 1 \
    > "$LOG_DIR/mira_batch_${TS}.log" 2>&1
echo "Mira done."

echo "=== All projects complete at $(date) ==="
