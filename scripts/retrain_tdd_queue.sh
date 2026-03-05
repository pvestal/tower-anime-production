#!/usr/bin/env bash
# Queue TDD character LoRA retraining (sequential, one at a time)
# Run: bash /opt/anime-studio/scripts/retrain_tdd_queue.sh
# Started: 2026-03-02

set -euo pipefail

API="http://localhost:8401"
CHARS=("Rina Suzuki" "Yuki Tanaka" "Takeshi Sato" "Beth")

wait_for_completion() {
    local job_id="$1"
    local char_name="$2"
    echo "[$(date +%H:%M:%S)] Waiting for $char_name (job: $job_id)..."

    while true; do
        status=$(curl -s "$API/api/training/jobs/$job_id" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','unknown'))" 2>/dev/null)

        if [ "$status" = "completed" ]; then
            loss=$(curl -s "$API/api/training/jobs/$job_id" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'final_loss={d.get(\"final_loss\",\"?\")}, best_loss={d.get(\"best_loss\",\"?\")}')" 2>/dev/null)
            echo "[$(date +%H:%M:%S)] $char_name COMPLETED ($loss)"
            return 0
        elif [ "$status" = "failed" ]; then
            error=$(curl -s "$API/api/training/jobs/$job_id" | python3 -c "import sys,json; print(json.load(sys.stdin).get('error','unknown error'))" 2>/dev/null)
            echo "[$(date +%H:%M:%S)] $char_name FAILED: $error"
            return 1
        fi

        # Show progress
        progress=$(curl -s "$API/api/training/jobs/$job_id" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'epoch={d.get(\"epoch\",\"?\")}/{d.get(\"total_epochs\",\"?\")}, loss={d.get(\"loss\",\"?\")}')" 2>/dev/null)
        echo "[$(date +%H:%M:%S)] $char_name: $progress"
        sleep 30
    done
}

# First wait for Mei if she's still training
mei_job=$(curl -s "$API/api/training/jobs" | python3 -c "
import sys,json
jobs = json.load(sys.stdin).get('training_jobs',[])
for j in jobs:
    if j.get('character_slug') == 'mei_kobayashi' and j.get('status') == 'running':
        print(j['job_id'])
        break
" 2>/dev/null)

if [ -n "$mei_job" ]; then
    echo "=== Mei Kobayashi still training, waiting... ==="
    wait_for_completion "$mei_job" "Mei Kobayashi"
fi

# Now train each remaining character
for char_name in "${CHARS[@]}"; do
    echo ""
    echo "=== Starting: $char_name ==="

    # Free ComfyUI VRAM first
    curl -s -X POST http://localhost:8188/free -H "Content-Type: application/json" -d '{"unload_models": true, "free_memory": true}' > /dev/null 2>&1
    sleep 3

    result=$(curl -s -X POST "$API/api/training/start" \
        -H "Content-Type: application/json" \
        -d "{\"character_name\": \"$char_name\", \"epochs\": 20, \"resolution\": 512, \"lora_rank\": 32}")

    job_id=$(echo "$result" | python3 -c "import sys,json; print(json.load(sys.stdin).get('job_id',''))" 2>/dev/null)

    if [ -z "$job_id" ]; then
        error=$(echo "$result" | python3 -c "import sys,json; print(json.load(sys.stdin).get('detail','unknown'))" 2>/dev/null)
        echo "[$(date +%H:%M:%S)] FAILED to start $char_name: $error"
        continue
    fi

    echo "[$(date +%H:%M:%S)] Started $char_name (job: $job_id)"
    wait_for_completion "$job_id" "$char_name" || true
done

echo ""
echo "=== All TDD retraining complete ==="
echo "Results:"
curl -s "$API/api/training/jobs" | python3 -c "
import sys, json
jobs = json.load(sys.stdin).get('training_jobs', [])
tdd_chars = {'mei_kobayashi', 'rina_suzuki', 'yuki_tanaka', 'takeshi_sato', 'beth'}
for j in sorted(jobs, key=lambda x: x.get('created_at',''), reverse=True):
    if j.get('character_slug') in tdd_chars:
        print(f'  {j[\"character_slug\"]:20s} status={j[\"status\"]:10s} loss={j.get(\"final_loss\",\"?\"):>8s} ckpt={j.get(\"checkpoint\",\"?\")}')
        tdd_chars.discard(j.get('character_slug'))
"
