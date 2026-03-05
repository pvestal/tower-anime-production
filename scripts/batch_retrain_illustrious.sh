#!/bin/bash
# Batch retrain all character LoRAs against WAI Illustrious SDXL
# Each job takes ~7-8 hours on RTX 3060 for SDXL rank 64
# Characters are ordered by priority (main cast first)

API="http://localhost:8401/api/training/start"

# Priority 1: CGS main cast (12 characters)
CGS_CHARS=(
    "Goblin Slayer"
    "Hiroshi"
    "Kai Nakamura"
    "Ryuu"
    "Elena Reyes"
    "Jamal Al-Rashid"
    "Marcus Thompson"
    "Zara Hosseini"
    "Street Goblin"
    "Cyber Goblin Alpha"
    "Corporate Executive"
    "Victim #1"
)

# Priority 2: TDD main cast (4 characters)
TDD_CHARS=(
    "Mei Kobayashi"
    "Rina Suzuki"
    "Takeshi Sato"
    "Yuki Tanaka"
)

# Priority 3: Mario cast (4 characters with enough data)
MARIO_CHARS=(
    "Mario"
    "Bowser"
    "Princess Peach"
    "Luigi"
)

# Priority 4: Rosa Caliente
OTHER_CHARS=(
    "Rosa"
)

ALL_CHARS=("${CGS_CHARS[@]}" "${TDD_CHARS[@]}" "${MARIO_CHARS[@]}" "${OTHER_CHARS[@]}")

TOTAL=${#ALL_CHARS[@]}
CURRENT=0

for char in "${ALL_CHARS[@]}"; do
    CURRENT=$((CURRENT + 1))
    echo ""
    echo "=========================================="
    echo "[$CURRENT/$TOTAL] Training: $char"
    echo "=========================================="
    echo "Started: $(date)"

    RESULT=$(curl -s -X POST "$API" \
        -H "Content-Type: application/json" \
        -d "{\"character_name\": \"$char\", \"epochs\": 20, \"learning_rate\": 0.0001}" 2>&1)

    JOB_ID=$(echo "$RESULT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('job_id','FAILED'))" 2>/dev/null)

    if [ "$JOB_ID" = "FAILED" ] || [ -z "$JOB_ID" ]; then
        echo "SKIP/FAIL: $RESULT"
        continue
    fi

    echo "Job: $JOB_ID"
    echo "$RESULT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'  Checkpoint: {d.get(\"checkpoint\")}')" 2>/dev/null
    echo "$RESULT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'  Images: {d.get(\"approved_images\")}, Rank: {d.get(\"lora_rank\")}, Res: {d.get(\"resolution\")}')" 2>/dev/null

    # Wait for this job to finish before starting next
    # (only one GPU, can't run in parallel)
    LOG=$(echo "$RESULT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('log_file',''))" 2>/dev/null)

    echo "Waiting for completion..."
    while true; do
        sleep 60
        if [ -f "$LOG" ] && grep -q "Training complete\|Error\|FAILED\|Traceback" "$LOG" 2>/dev/null; then
            if grep -q "Training complete" "$LOG" 2>/dev/null; then
                LOSS=$(grep "Best loss" "$LOG" 2>/dev/null | tail -1)
                echo "DONE: $char — $LOSS"
            else
                echo "ERROR: $char — check $LOG"
            fi
            break
        fi
        # Show progress
        STEP=$(grep "Step " "$LOG" 2>/dev/null | tail -1)
        if [ -n "$STEP" ]; then
            echo -ne "\r  $STEP"
        fi
    done

    echo "Finished: $(date)"
done

echo ""
echo "=========================================="
echo "All training complete!"
echo "=========================================="
echo "New LoRAs:"
ls -lh /opt/ComfyUI/models/loras/*_xl_lora.safetensors 2>/dev/null
