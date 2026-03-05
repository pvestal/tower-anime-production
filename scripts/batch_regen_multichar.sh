#!/usr/bin/env bash
# Batch regenerate all CGS multi-char shots via simple keyframe → wan22_14b I2V
# Run: bash /opt/anime-studio/scripts/batch_regen_multichar.sh
# Monitor: tail -f /tmp/cgs_batch_regen.log

set -euo pipefail

API="http://localhost:8401"
LOG="/tmp/cgs_batch_regen.log"
PGPASSWORD="RP78eIrW7cI2jYvL5akt1yurE"
export PGPASSWORD

echo "=== CGS Multi-Char Batch Regeneration ===" | tee "$LOG"
echo "Started: $(date)" | tee -a "$LOG"

# Get all pending multi-char shots for project 42
SHOTS=$(psql -h localhost -U patrick -d anime_production -t -A -c "
SELECT s.id || '|' || s.scene_id || '|' || sc.scene_number || '|' || s.shot_number || '|' || array_to_string(s.characters_present, ',')
FROM shots s
JOIN scenes sc ON s.scene_id = sc.id
WHERE sc.project_id = 42
  AND array_length(s.characters_present, 1) >= 2
  AND s.status IN ('pending', 'failed')
  AND s.video_engine = 'wan'
ORDER BY sc.scene_number, s.shot_number;
")

TOTAL=$(echo "$SHOTS" | grep -c '|' || true)
echo "Total shots to regenerate: $TOTAL" | tee -a "$LOG"

if [ "$TOTAL" -eq 0 ]; then
  echo "No shots to regenerate. Exiting." | tee -a "$LOG"
  exit 0
fi

DONE=0
FAILED=0
SKIPPED=0

for LINE in $SHOTS; do
  SHOT_ID=$(echo "$LINE" | cut -d'|' -f1)
  SCENE_ID=$(echo "$LINE" | cut -d'|' -f2)
  SCENE_NUM=$(echo "$LINE" | cut -d'|' -f3)
  SHOT_NUM=$(echo "$LINE" | cut -d'|' -f4)
  CHARS=$(echo "$LINE" | cut -d'|' -f5)

  DONE=$((DONE + 1))
  echo "" | tee -a "$LOG"
  echo "[$DONE/$TOTAL] Scene $SCENE_NUM Shot $SHOT_NUM ($CHARS)" | tee -a "$LOG"
  echo "  Shot: $SHOT_ID" | tee -a "$LOG"
  echo "  Time: $(date '+%H:%M:%S')" | tee -a "$LOG"

  # Wait for ComfyUI queue to be empty before submitting next
  for i in $(seq 1 120); do
    QUEUE=$(curl -s "http://localhost:8188/queue" 2>/dev/null || echo '{"queue_running":[],"queue_pending":[]}')
    RUNNING=$(echo "$QUEUE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('queue_running',[])))" 2>/dev/null || echo "0")
    PENDING=$(echo "$QUEUE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('queue_pending',[])))" 2>/dev/null || echo "0")
    if [ "$RUNNING" = "0" ] && [ "$PENDING" = "0" ]; then
      break
    fi
    if [ "$i" -eq 1 ]; then
      echo "  Waiting for ComfyUI queue (running=$RUNNING, pending=$PENDING)..." | tee -a "$LOG"
    fi
    sleep 5
  done

  # Call regenerate endpoint
  RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
    "$API/api/scenes/$SCENE_ID/shots/$SHOT_ID/regenerate" \
    -H "Content-Type: application/json" \
    -H "X-User-Id: 1" \
    --max-time 180 2>&1)

  HTTP_CODE=$(echo "$RESPONSE" | tail -1)
  BODY=$(echo "$RESPONSE" | head -n -1)

  if [ "$HTTP_CODE" = "200" ]; then
    PROMPT_ID=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('comfyui_prompt_id','?'))" 2>/dev/null || echo "?")
    echo "  OK → ComfyUI prompt: $PROMPT_ID" | tee -a "$LOG"

    # Wait for video generation to complete (poll ComfyUI queue)
    echo "  Waiting for video render..." | tee -a "$LOG"
    RENDER_START=$(date +%s)
    for j in $(seq 1 120); do
      QUEUE=$(curl -s "http://localhost:8188/queue" 2>/dev/null || echo '{"queue_running":[],"queue_pending":[]}')
      RUNNING=$(echo "$QUEUE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('queue_running',[])))" 2>/dev/null || echo "0")
      PENDING=$(echo "$QUEUE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('queue_pending',[])))" 2>/dev/null || echo "0")
      if [ "$RUNNING" = "0" ] && [ "$PENDING" = "0" ]; then
        RENDER_END=$(date +%s)
        RENDER_TIME=$((RENDER_END - RENDER_START))
        echo "  Video rendered in ${RENDER_TIME}s" | tee -a "$LOG"
        break
      fi
      sleep 5
    done

    # Wait a moment for async DB update from backend
    sleep 5
    # Verify shot status
    STATUS=$(psql -h localhost -U patrick -d anime_production -t -A -c \
      "SELECT status || '|' || COALESCE(video_engine,'?') || '|' || COALESCE(LEFT(output_video_path,60),'none') FROM shots WHERE id = '$SHOT_ID';" 2>/dev/null)
    echo "  Result: $STATUS" | tee -a "$LOG"

    SHOT_STATUS=$(echo "$STATUS" | cut -d'|' -f1)
    if [ "$SHOT_STATUS" = "completed" ]; then
      echo "  SUCCESS" | tee -a "$LOG"
    else
      echo "  INCOMPLETE (status=$SHOT_STATUS)" | tee -a "$LOG"
      FAILED=$((FAILED + 1))
    fi
  else
    echo "  FAILED (HTTP $HTTP_CODE): $BODY" | tee -a "$LOG"
    FAILED=$((FAILED + 1))
  fi

  # Brief pause to let GPU cool
  sleep 2
done

echo "" | tee -a "$LOG"
echo "=== Batch Complete ===" | tee -a "$LOG"
echo "Finished: $(date)" | tee -a "$LOG"
echo "Total: $TOTAL, Failed: $FAILED, Skipped: $SKIPPED" | tee -a "$LOG"

# Summary of results
echo "" | tee -a "$LOG"
echo "=== Final Status ===" | tee -a "$LOG"
psql -h localhost -U patrick -d anime_production -c "
SELECT s.video_engine, s.status, count(*)
FROM shots s
JOIN scenes sc ON s.scene_id = sc.id
WHERE sc.project_id = 42
  AND array_length(s.characters_present, 1) >= 2
GROUP BY s.video_engine, s.status
ORDER BY s.video_engine, s.status;
" 2>/dev/null | tee -a "$LOG"
