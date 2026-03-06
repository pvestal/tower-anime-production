#!/bin/bash
# Batch train LoRAs for all priority characters
# Trains sequentially (GPU lock allows only one at a time)
# Usage: ./scripts/batch_train_loras.sh

API="http://localhost:8401/api/training"
LOG_DIR="/opt/anime-studio/logs"

# Characters to train in priority order
# Format: "Character Name" (must match DB exactly)
CHARACTERS=(
    # --- Priority: Newly generated datasets (100 images each) ---
    "Buck"
    "Lilith"
    "Zara"
    "Beth"
    # --- TDD main cast (350-758 images each) ---
    "Rina Suzuki"
    "Mei Kobayashi"
    "Yuki Tanaka"
    "Takeshi Sato"
    # --- CGS (100-190 images each) ---
    "Goblin Slayer"
    "Kai Nakamura"
    "Hiroshi"
    "Marcus Thompson"
    "Jamal Al-Rashid"
    "Ryuu"
    "Street Goblin"
    "Cyber Goblin Alpha"
    "Corporate Executive"
    "Victim #1"
    # --- Fury (400+ images) ---
    "Roxy"
)

train_character() {
    local name="$1"
    echo "=========================================="
    echo "Training: $name"
    echo "=========================================="

    # Wait for any running training to finish
    while true; do
        status=$(curl -s "$API/jobs" | python3 -c "
import json, sys
jobs = json.load(sys.stdin).get('training_jobs', [])
running = [j for j in jobs if j.get('status') == 'running']
if running:
    print(f\"BUSY:{running[0]['character_name']}\")
else:
    print('READY')
" 2>/dev/null)

        if [[ "$status" == "READY" ]]; then
            break
        fi
        echo "  Waiting... ($status)"
        sleep 60
    done

    # Start training
    result=$(curl -s -X POST "$API/start" \
        -H "Content-Type: application/json" \
        -d "{\"character_name\": \"$name\"}")

    job_id=$(echo "$result" | python3 -c "import json,sys; print(json.load(sys.stdin).get('job_id','FAILED'))" 2>/dev/null)

    if [[ "$job_id" == "FAILED" ]] || [[ -z "$job_id" ]]; then
        echo "  FAILED to start: $result"
        return 1
    fi

    echo "  Started: $job_id"

    # Wait for completion
    while true; do
        sleep 120
        job_status=$(curl -s "$API/jobs/$job_id" | python3 -c "
import json, sys
j = json.load(sys.stdin)
status = j.get('status', 'unknown')
progress = j.get('progress', '')
print(f'{status}:{progress}')
" 2>/dev/null)

        status="${job_status%%:*}"
        progress="${job_status#*:}"

        case "$status" in
            completed)
                echo "  COMPLETED: $name"
                return 0
                ;;
            failed)
                echo "  FAILED: $name"
                return 1
                ;;
            running)
                echo "  Progress: $progress"
                ;;
            *)
                echo "  Status: $job_status"
                ;;
        esac
    done
}

echo "Batch LoRA Training — $(date)"
echo "Characters to train: ${#CHARACTERS[@]}"
echo ""

completed=0
failed=0

for char in "${CHARACTERS[@]}"; do
    if train_character "$char"; then
        ((completed++))
    else
        ((failed++))
    fi
    echo ""
done

echo "=========================================="
echo "DONE: $completed completed, $failed failed out of ${#CHARACTERS[@]}"
echo "=========================================="
