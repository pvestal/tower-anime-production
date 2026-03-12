#!/bin/bash
# Overnight batch — keyframes, video gen, foley verification, video scan processing
# Started: $(date)
set -e

LOG="/opt/anime-studio/output/overnight_batch_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee -a "$LOG") 2>&1

echo "============================================="
echo "OVERNIGHT BATCH START: $(date)"
echo "============================================="

API="http://localhost:8401"
DB="PGPASSWORD=RP78eIrW7cI2jYvL5akt1yurE psql -h localhost -U patrick -d anime_production -t"

# ============================================
# PHASE 1: KEYFRAME GENERATION (~409 shots, ~2hrs)
# ============================================
echo ""
echo "===== PHASE 1: KEYFRAME BLITZ ====="
echo "Getting scenes with missing keyframes..."

SCENES=$(PGPASSWORD=RP78eIrW7cI2jYvL5akt1yurE psql -h localhost -U patrick -d anime_production -t -c "
SELECT DISTINCT sc.id
FROM shots s JOIN scenes sc ON s.scene_id = sc.id
WHERE s.status = 'pending' AND s.source_image_path IS NULL
ORDER BY sc.id;")

SCENE_COUNT=$(echo "$SCENES" | grep -c '[a-f0-9]' || true)
echo "Scenes to blitz: $SCENE_COUNT"

IDX=0
for sid in $SCENES; do
  sid=$(echo "$sid" | tr -d ' ')
  [ -z "$sid" ] && continue
  IDX=$((IDX + 1))
  echo ""
  echo "[$IDX/$SCENE_COUNT] Blitzing scene $sid..."
  RESULT=$(curl -s -X POST "$API/api/scenes/$sid/keyframe-blitz" 2>/dev/null || echo '{"error":"failed"}')
  GEN=$(echo "$RESULT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('generated',0))" 2>/dev/null || echo 0)
  FAIL=$(echo "$RESULT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('failed',0))" 2>/dev/null || echo 0)
  echo "  Generated: $GEN, Failed: $FAIL"
done

echo ""
echo "===== PHASE 1 COMPLETE: $(date) ====="

# ============================================
# PHASE 2: VIDEO GENERATION (priority projects)
# ============================================
echo ""
echo "===== PHASE 2: VIDEO GENERATION ====="
echo "Enabling orchestrator for video gen..."

# Get video-ready scenes ordered by priority
VIDEO_SCENES=$(PGPASSWORD=RP78eIrW7cI2jYvL5akt1yurE psql -h localhost -U patrick -d anime_production -t -c "
SELECT sc.id, p.name, count(*) as cnt
FROM shots s JOIN scenes sc ON s.scene_id = sc.id JOIN projects p ON sc.project_id = p.id
WHERE s.status = 'pending' AND s.source_image_path IS NOT NULL
GROUP BY sc.id, p.name
ORDER BY
  CASE p.name
    WHEN 'Fury' THEN 1
    WHEN 'Love, Sex, and Robots' THEN 2
    WHEN 'Cyberpunk Goblin Slayer: Neon Shadows' THEN 3
    WHEN 'Tokyo Debt Desire' THEN 4
    WHEN 'Rosa Caliente' THEN 5
    WHEN 'Mira the Little Bunny' THEN 6
    ELSE 7
  END, sc.id;")

VIDEO_COUNT=$(echo "$VIDEO_SCENES" | grep -c '[a-f0-9]' || true)
echo "Video-ready scenes: $VIDEO_COUNT"

# Use the orchestrator scene-generate endpoint for each scene
VIDX=0
echo "$VIDEO_SCENES" | while IFS='|' read -r vid_sid vid_project vid_cnt; do
  vid_sid=$(echo "$vid_sid" | tr -d ' ')
  vid_project=$(echo "$vid_project" | tr -d ' ')
  vid_cnt=$(echo "$vid_cnt" | tr -d ' ')
  [ -z "$vid_sid" ] && continue
  VIDX=$((VIDX + 1))
  echo ""
  echo "[VIDEO $VIDX/$VIDEO_COUNT] $vid_project - Scene $vid_sid ($vid_cnt shots)"

  # Generate scene videos one at a time
  RESULT=$(curl -s -X POST "$API/api/scenes/$vid_sid/generate" \
    -H "Content-Type: application/json" \
    -d '{"engine":"wan22_14b","max_shots":5}' 2>/dev/null || echo '{"error":"timeout or failed"}')

  echo "  Result: $(echo "$RESULT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'completed={d.get(\"completed\",0)} failed={d.get(\"failed\",0)}')" 2>/dev/null || echo "parse error")"
done

echo ""
echo "===== PHASE 2 COMPLETE: $(date) ====="

# ============================================
# PHASE 3: FOLEY SFX VERIFICATION
# ============================================
echo ""
echo "===== PHASE 3: FOLEY VERIFICATION ====="

# Quick loudness check on all foley clips
FOLEY_DIR="/opt/anime-studio/output/sfx_library/foley"
SILENT=0
OK=0
for wav in "$FOLEY_DIR"/*/*.wav; do
  [ -f "$wav" ] || continue
  # Check RMS volume with ffmpeg
  RMS=$(ffmpeg -i "$wav" -af "volumedetect" -f null /dev/null 2>&1 | grep "mean_volume" | awk '{print $5}')
  if [ -n "$RMS" ]; then
    # RMS below -40dB is likely silent/useless
    IS_QUIET=$(python3 -c "print(1 if float('$RMS') < -40 else 0)" 2>/dev/null || echo 0)
    if [ "$IS_QUIET" = "1" ]; then
      echo "  QUIET: $wav (${RMS}dB)"
      SILENT=$((SILENT + 1))
    else
      OK=$((OK + 1))
    fi
  fi
done
echo "Foley check: $OK OK, $SILENT quiet/suspect"
echo "===== PHASE 3 COMPLETE: $(date) ====="

# ============================================
# PHASE 4: VIDEO SCAN PROCESSING
# ============================================
echo ""
echo "===== PHASE 4: VIDEO SCAN PROCESSING ====="

# Process the high-scoring video candidates from explicit_video_scan.json
SCAN_FILE="/opt/anime-studio/output/sfx_library/explicit_video_scan.json"
if [ -f "$SCAN_FILE" ]; then
  python3 << 'PYEOF'
import json, subprocess, os
from pathlib import Path

scan = json.load(open("/opt/anime-studio/output/sfx_library/explicit_video_scan.json"))
print(f"Video scan entries: {len(scan)}")

# These are already scored — extract audio from high-score videos
high = [x for x in scan if x.get("score", 0) >= 0.7]
print(f"High score candidates: {len(high)}")

extracted = 0
out_dir = Path("/opt/anime-studio/output/sfx_library/video_extracted")
out_dir.mkdir(exist_ok=True)

for entry in high[:50]:  # Process top 50 overnight
    path = entry.get("path", "")
    if not path or not os.path.exists(path):
        continue

    fname = Path(path).stem
    out_path = out_dir / f"{fname}.wav"
    if out_path.exists():
        continue

    try:
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", path, "-ac", "1", "-ar", "22050", "-t", "30", str(out_path)],
            capture_output=True, timeout=30
        )
        if out_path.exists() and out_path.stat().st_size > 2000:
            extracted += 1
            print(f"  Extracted: {fname}")
    except Exception as e:
        print(f"  Failed: {fname}: {e}")

print(f"Total extracted: {extracted}")
PYEOF
else
  echo "No video scan file found"
fi

echo "===== PHASE 4 COMPLETE: $(date) ====="

echo ""
echo "============================================="
echo "OVERNIGHT BATCH COMPLETE: $(date)"
echo "============================================="
