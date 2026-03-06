#!/bin/bash
# Batch: TDD Scene 42 video gen + CGS pending shots
# Usage: nohup bash /opt/anime-studio/scripts/batch_tdd_cgs.sh >> /opt/anime-studio/logs/batch.log 2>&1 &
set -uo pipefail

SCENE_42="9a701f0d-3cee-4c42-b8aa-fb21990b100e"
API="http://localhost:8401"
export PGPASSWORD=RP78eIrW7cI2jYvL5akt1yurE

log() { echo "[$(date '+%H:%M:%S')] $*"; }

dbq() {
    psql -h localhost -U patrick -d anime_production -t -A -c "$1"
}

wait_comfyui() {
    while true; do
        local r
        r=$(curl -s http://localhost:8188/queue 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d.get('queue_running',[])))" 2>/dev/null || echo "1")
        [ "$r" = "0" ] && break
        sleep 15
    done
}

# ====== PHASE 2: TDD Scene 42 full generation ======
log "Starting TDD Scene 42 full generation"

# Wait for last keyframe
sleep 30
kf=$(dbq "SELECT COUNT(*) FROM shots WHERE scene_id = '$SCENE_42' AND source_image_path IS NOT NULL AND source_image_path <> '';")
log "Keyframes ready: $kf/20"

# Kick off scene generation
curl -s -X POST "$API/api/scenes/$SCENE_42/generate" --max-time 10 2>/dev/null || true
log "Scene gen triggered"

# Monitor
last_done=0
stall_count=0
while true; do
    sleep 90
    done=$(dbq "SELECT COUNT(*) FROM shots WHERE scene_id = '$SCENE_42' AND status = 'completed';")
    total=20
    log "TDD Scene 42: $done/$total completed"
    [ "$done" -ge "$total" ] && break

    # Stall detection — only trigger after 3 cycles (4.5 min) with no progress
    if [ "$done" -eq "$last_done" ]; then
        stall_count=$((stall_count + 1))
    else
        stall_count=0
        last_done=$done
    fi

    if [ "$stall_count" -ge 3 ]; then
        comfy_running=$(curl -s http://localhost:8188/queue 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d.get('queue_running',[])))" 2>/dev/null || echo "1")
        if [ "$comfy_running" = "0" ]; then
            log "WARN: stalled at $done/$total for ${stall_count} cycles — re-triggering"
            curl -s -X POST "$API/api/scenes/$SCENE_42/generate" --max-time 10 2>/dev/null || true
            stall_count=0
            sleep 30
        fi
    fi
done

log "TDD Scene 42 DONE"

# ====== PHASE 3: CGS pending shots ======
log "Starting CGS pending shots"

cgs_pending=$(dbq "
    SELECT sh.scene_id || '|' || sh.id
    FROM shots sh
    JOIN scenes s ON sh.scene_id = s.id
    JOIN projects p ON s.project_id = p.id
    WHERE p.name = 'Cyberpunk Goblin Slayer: Neon Shadows'
    AND sh.status <> 'completed'
    ORDER BY s.scene_number, sh.shot_number;
")

n=0
for line in $cgs_pending; do
    scene_id="${line%%|*}"
    shot_id="${line##*|}"
    n=$((n+1))
    log "CGS shot $n: $shot_id"
    curl -s -X POST "$API/api/scenes/$scene_id/shots/$shot_id/regenerate" --max-time 10 2>/dev/null || true
    wait_comfyui
    sleep 5
done

log "CGS: $n shots processed"

# ====== SUMMARY ======
log "=== DONE ==="
dbq "
    SELECT p.name || ': ' || COUNT(*) FILTER (WHERE sh.status = 'completed') || '/' || COUNT(*) || ' completed'
    FROM shots sh
    JOIN scenes s ON sh.scene_id = s.id
    JOIN projects p ON s.project_id = p.id
    WHERE p.name IN ('Tokyo Debt Desire', 'Cyberpunk Goblin Slayer: Neon Shadows')
    GROUP BY p.name;
"
