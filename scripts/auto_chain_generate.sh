#!/bin/bash
# Auto-chain scene generation across projects
# Watches each scene for completion, then kicks off the next
# Usage: ./auto_chain_generate.sh

BASE="http://localhost:8401/api"
LOG="/opt/anime-studio/output/auto_chain.log"

SCENES=(
  "dc05ff04-2514-4a3c-844b-bf97abf46bb7|Fury Trailer"
  "8bb558fd-15ff-411f-8de4-0847a88630eb|Rosa Showcase"
  "9a701f0d-3cee-4c42-b8aa-fb21990b100e|TDD Rina Takes Control"
)

log() { echo "[$(date '+%H:%M:%S')] $1" | tee -a "$LOG"; }

for entry in "${SCENES[@]}"; do
  IFS='|' read -r scene_id scene_name <<< "$entry"

  # Check if scene has pending shots
  pending=$(sudo -u postgres psql -d anime_production -t -A -c \
    "SELECT COUNT(*) FROM shots WHERE scene_id = '$scene_id' AND status = 'pending'" 2>/dev/null)
  generating=$(sudo -u postgres psql -d anime_production -t -A -c \
    "SELECT COUNT(*) FROM shots WHERE scene_id = '$scene_id' AND status = 'generating'" 2>/dev/null)

  if [ "$pending" -eq 0 ] && [ "$generating" -eq 0 ]; then
    log "$scene_name: already done, skipping"
    continue
  fi

  # If not already generating, kick it off
  if [ "$generating" -eq 0 ]; then
    log "$scene_name: starting generation ($pending pending shots)..."
    curl -s -X POST "$BASE/scenes/$scene_id/generate?auto_approve=true" > /dev/null 2>&1
  else
    log "$scene_name: already generating, waiting..."
  fi

  # Wait for completion
  while true; do
    sleep 120  # Check every 2 minutes
    still_pending=$(sudo -u postgres psql -d anime_production -t -A -c \
      "SELECT COUNT(*) FROM shots WHERE scene_id = '$scene_id' AND status IN ('pending', 'generating')" 2>/dev/null)
    completed=$(sudo -u postgres psql -d anime_production -t -A -c \
      "SELECT COUNT(*) FROM shots WHERE scene_id = '$scene_id' AND status = 'completed'" 2>/dev/null)
    total=$(sudo -u postgres psql -d anime_production -t -A -c \
      "SELECT COUNT(*) FROM shots WHERE scene_id = '$scene_id'" 2>/dev/null)

    log "$scene_name: $completed/$total done, $still_pending remaining"

    if [ "$still_pending" -eq 0 ]; then
      log "$scene_name: COMPLETE! Assembling..."
      curl -s -X POST "$BASE/scenes/$scene_id/assemble" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'  Assembled: {d.get(\"duration_seconds\",0):.1f}s')" 2>/dev/null | tee -a "$LOG"
      break
    fi
  done
done

log "All scenes generated and assembled!"
log "Reels at: /opt/anime-studio/output/reels/"
