#!/bin/bash
# Batch render all pending framepack shots for CGS (project 42)
# Waits for ComfyUI queue to empty between each shot
# Usage: nohup ./batch_framepack_pending.sh &

API="http://localhost:8401"
COMFYUI="http://localhost:8188"
export PGPASSWORD="RP78eIrW7cI2jYvL5akt1yurE"

wait_for_queue() {
    local timeout=${1:-900}
    local elapsed=0
    while [ $elapsed -lt $timeout ]; do
        local running=$(curl -s "$COMFYUI/queue" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('queue_running',[])) + len(d.get('queue_pending',[])))" 2>/dev/null)
        if [ "$running" = "0" ]; then
            return 0
        fi
        sleep 10
        elapsed=$((elapsed + 10))
        echo "  Queue: $running active, ${elapsed}s / ${timeout}s"
    done
    return 1
}

echo "=== Batch FramePack Render - $(date) ==="

# Wait for any current render to finish first
echo "Waiting for current queue to clear..."
wait_for_queue 1200

# Get all pending shots
SHOTS=$(psql -h localhost -U patrick -d anime_production -t -A -c "
SELECT s.id, s.scene_id, sc.scene_number, s.shot_number, s.video_engine
FROM shots s JOIN scenes sc ON s.scene_id = sc.id
WHERE sc.project_id = 42 AND s.status = 'pending'
ORDER BY sc.scene_number, s.shot_number;")

if [ -z "$SHOTS" ]; then
    echo "No pending shots!"
    exit 0
fi

TOTAL=$(echo "$SHOTS" | wc -l)
COUNT=0
SUCCESS=0
FAILED=0

echo "$TOTAL pending shots to render"
echo ""

while IFS='|' read -r shot_id scene_id scene_num shot_num engine; do
    COUNT=$((COUNT + 1))
    echo "--- [$COUNT/$TOTAL] Scene $scene_num Shot $shot_num ($engine) - $(date +%H:%M:%S) ---"

    # Call regenerate endpoint (handles keyframe gen + ComfyUI submission)
    RESULT=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API/api/scenes/$scene_id/shots/$shot_id/regenerate" 2>/dev/null)

    if [ "$RESULT" != "200" ]; then
        echo "  FAILED to submit (HTTP $RESULT)"
        FAILED=$((FAILED + 1))
        continue
    fi

    echo "  Submitted, waiting for render..."
    sleep 5  # Give it time to generate keyframe + submit to ComfyUI

    # Wait for render to complete (20 min timeout for framepack)
    if wait_for_queue 1200; then
        # Check if shot actually completed
        STATUS=$(psql -h localhost -U patrick -d anime_production -t -A -c "
            SELECT status FROM shots WHERE id = '$shot_id';")
        if [ "$STATUS" = "completed" ]; then
            echo "  SUCCESS"
            SUCCESS=$((SUCCESS + 1))
        else
            echo "  Render finished but status=$STATUS"
            FAILED=$((FAILED + 1))
        fi
    else
        echo "  TIMEOUT after 20 min"
        FAILED=$((FAILED + 1))
    fi
    echo ""
done <<< "$SHOTS"

echo "=== BATCH COMPLETE: $SUCCESS success, $FAILED failed out of $TOTAL - $(date) ==="
