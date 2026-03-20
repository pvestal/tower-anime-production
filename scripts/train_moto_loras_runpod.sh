#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────
# train_moto_loras_runpod.sh
# Package motorcycle camera LoRA training data and train on RunPod A100
# Uses musubi-tuner with WAN 2.2 14B I2V for video LoRA training
#
# Usage:
#   bash train_moto_loras_runpod.sh <lora_name>     # Single LoRA
#   bash train_moto_loras_runpod.sh --all            # All priority-1 LoRAs
#   bash train_moto_loras_runpod.sh --list           # Show available LoRAs
#
# Prerequisites:
#   - RunPod SSH key verified in web UI matching ~/.ssh/id_ed25519.pub
#   - runpodctl installed at ~/.local/bin/runpodctl
#   - Training clips collected in datasets/_motion_loras/<lora_name>/clips/
#   - Captions in datasets/_motion_loras/<lora_name>/captions.json
# ──────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ANIME_STUDIO="/opt/anime-studio"
DATASETS_DIR="${ANIME_STUDIO}/datasets/_motion_loras"
MUSUBI_DIR="/opt/musubi-tuner"
BUNDLE_DIR="/tmp/runpod_moto_lora_bundle"
RUNPODCTL="${HOME}/.local/bin/runpodctl"
OUTPUT_DIR="/opt/ComfyUI/models/loras/wan22_camera"

# RunPod config
RUNPOD_IMAGE="runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04"
RUNPOD_GPU="NVIDIA A100 80GB PCIe"
RUNPOD_VOLUME_SIZE=50  # GB
RUNPOD_POD_NAME="tower-moto-lora-training"

# WAN 2.2 14B model path (will be downloaded on pod if not cached)
WAN_MODEL="Wan-AI/Wan2.2-I2V-14B-480P"

# All motorcycle LoRAs defined in motion_lora_training_specs.yaml
declare -A MOTO_LORAS=(
  [moto_rider_pov]="priority1"
  [moto_low_chase]="priority1"
  [moto_tire_closeup]="priority1"
  [moto_lean_tracking]="priority2"
  [moto_flyby]="priority2"
  [moto_exhaust_detail]="priority2"
  [moto_wheelie_rear]="priority3"
  [moto_garage_orbit]="priority3"
)

# Training hyperparams per LoRA (from training specs)
declare -A LORA_RANK=(
  [moto_rider_pov]=24  [moto_low_chase]=24  [moto_tire_closeup]=16
  [moto_lean_tracking]=24  [moto_flyby]=16  [moto_exhaust_detail]=16
  [moto_wheelie_rear]=16  [moto_garage_orbit]=24
)
declare -A LORA_LR=(
  [moto_rider_pov]="8e-5"  [moto_low_chase]="8e-5"  [moto_tire_closeup]="7e-5"
  [moto_lean_tracking]="8e-5"  [moto_flyby]="7e-5"  [moto_exhaust_detail]="7e-5"
  [moto_wheelie_rear]="7e-5"  [moto_garage_orbit]="8e-5"
)
declare -A LORA_STEPS=(
  [moto_rider_pov]=2500  [moto_low_chase]=2500  [moto_tire_closeup]=2000
  [moto_lean_tracking]=2500  [moto_flyby]=2000  [moto_exhaust_detail]=2000
  [moto_wheelie_rear]=2000  [moto_garage_orbit]=2500
)

# ── Functions ──

show_list() {
    echo "Available motorcycle camera LoRAs:"
    echo ""
    printf "  %-24s %-10s %-6s %-8s %-6s %s\n" "NAME" "PRIORITY" "RANK" "LR" "STEPS" "CLIPS"
    echo "  $(printf '%.0s─' {1..80})"
    for lora in $(echo "${!MOTO_LORAS[@]}" | tr ' ' '\n' | sort); do
        local clip_dir="${DATASETS_DIR}/${lora}/clips"
        local clip_count=0
        [[ -d "$clip_dir" ]] && clip_count=$(find "$clip_dir" -name "*.mp4" 2>/dev/null | wc -l)
        local trained="no"
        [[ -f "${OUTPUT_DIR}/${lora}_HIGH.safetensors" ]] && trained="YES"
        printf "  %-24s %-10s %-6s %-8s %-6s %s (trained: %s)\n" \
            "$lora" "${MOTO_LORAS[$lora]}" "${LORA_RANK[$lora]}" \
            "${LORA_LR[$lora]}" "${LORA_STEPS[$lora]}" "$clip_count" "$trained"
    done
}

validate_dataset() {
    local lora_name="$1"
    local clip_dir="${DATASETS_DIR}/${lora_name}/clips"
    local caption_file="${DATASETS_DIR}/${lora_name}/captions.json"

    if [[ ! -d "$clip_dir" ]]; then
        echo "ERROR: No clips directory at ${clip_dir}"
        echo "  Collect training clips first. See motion_lora_training_specs.yaml for sources."
        return 1
    fi

    local clip_count
    clip_count=$(find "$clip_dir" -name "*.mp4" | wc -l)
    if [[ "$clip_count" -lt 10 ]]; then
        echo "ERROR: Only ${clip_count} clips for ${lora_name} (minimum 10 required)"
        return 1
    fi

    if [[ ! -f "$caption_file" ]]; then
        echo "WARNING: No captions.json found. Will generate captions on pod."
    fi

    echo "Dataset OK: ${clip_count} clips for ${lora_name}"
    return 0
}

package_bundle() {
    local lora_name="$1"
    echo "Packaging training bundle for ${lora_name}..."

    local bundle="${BUNDLE_DIR}/${lora_name}"
    rm -rf "$bundle"
    mkdir -p "$bundle/clips" "$bundle/scripts"

    # Copy training clips
    cp "${DATASETS_DIR}/${lora_name}/clips/"*.mp4 "$bundle/clips/" 2>/dev/null || true

    # Copy captions if they exist
    [[ -f "${DATASETS_DIR}/${lora_name}/captions.json" ]] && \
        cp "${DATASETS_DIR}/${lora_name}/captions.json" "$bundle/"

    # Copy manifest if exists
    [[ -f "${DATASETS_DIR}/${lora_name}/manifest.json" ]] && \
        cp "${DATASETS_DIR}/${lora_name}/manifest.json" "$bundle/"

    # Generate the training script that runs ON the pod
    cat > "$bundle/scripts/train_on_pod.sh" << TRAIN_SCRIPT
#!/usr/bin/env bash
# Auto-generated training script for ${lora_name}
# Runs on RunPod A100 with musubi-tuner
set -euo pipefail

LORA_NAME="${lora_name}"
RANK=${LORA_RANK[$lora_name]}
LR=${LORA_LR[$lora_name]}
STEPS=${LORA_STEPS[$lora_name]}
CHECKPOINT_EVERY=$((${LORA_STEPS[$lora_name]} / 7))

echo "=== Training \${LORA_NAME} on RunPod ==="
echo "  Rank: \${RANK}, LR: \${LR}, Steps: \${STEPS}"
echo "  GPU: \$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader)"

# Install musubi-tuner if not present
if [[ ! -d /workspace/musubi-tuner ]]; then
    echo "Installing musubi-tuner..."
    cd /workspace
    git clone https://github.com/kohya-ss/musubi-tuner.git
    cd musubi-tuner
    pip install -r requirements.txt
    pip install accelerate transformers sentencepiece protobuf
fi

cd /workspace/musubi-tuner

# Prepare dataset directory structure
DATASET_DIR="/workspace/dataset/\${LORA_NAME}"
mkdir -p "\${DATASET_DIR}"
cp /workspace/bundle/clips/*.mp4 "\${DATASET_DIR}/"

# Create dataset TOML config
cat > /workspace/dataset_config.toml << 'TOML'
[general]
resolution = [480, 720]
caption_extension = ".txt"
batch_size = 1
enable_bucket = true

[[datasets]]
video_directory = "/workspace/dataset/${lora_name}"
TOML

# Generate captions from JSON or create defaults
if [[ -f /workspace/bundle/captions.json ]]; then
    python3 -c "
import json, os
caps = json.load(open('/workspace/bundle/captions.json'))
for fname, caption in caps.items():
    base = os.path.splitext(fname)[0]
    with open(f'/workspace/dataset/${lora_name}/{base}.txt', 'w') as f:
        f.write(caption)
print(f'Wrote {len(caps)} caption files')
"
else
    echo "No captions.json — using default caption for all clips"
    for f in "\${DATASET_DIR}"/*.mp4; do
        base="\$(basename "\$f" .mp4)"
        echo "${lora_name} camera motion" > "\${DATASET_DIR}/\${base}.txt"
    done
fi

# Step 1: Cache text encoder outputs
echo "=== Caching text encoder outputs ==="
python3 wan_cache_text_encoder_outputs.py \
    --dataset_config /workspace/dataset_config.toml \
    --model_id "${WAN_MODEL}" \
    --batch_size 4

# Step 2: Cache video latents
echo "=== Caching video latents ==="
python3 wan_cache_latents.py \
    --dataset_config /workspace/dataset_config.toml \
    --model_id "${WAN_MODEL}" \
    --batch_size 1

# Step 3: Train single-file LoRA (musubi-tuner dual-branch format)
# Musubi-tuner produces ONE .safetensors containing both high+low noise branches.
# This matches how the existing working LoRAs (motorcycle_drift, vehicle_chase) were trained.
echo "=== Training LoRA (single-file dual-branch) ==="
accelerate launch --mixed_precision bf16 wan_train_network.py \
    --task i2v \
    --dataset_config /workspace/dataset_config.toml \
    --model_id "${WAN_MODEL}" \
    --network_module networks.lora_wan \
    --network_dim \${RANK} \
    --network_alpha \${RANK} \
    --learning_rate \${LR} \
    --max_train_steps \${STEPS} \
    --save_every_n_steps \${CHECKPOINT_EVERY} \
    --output_dir /workspace/output \
    --output_name "\${LORA_NAME}" \
    --timestep_sampling sigmoid \
    --optimizer_type adamw8bit \
    --gradient_checkpointing \
    --max_data_loader_n_workers 4 \
    --seed 42 \
    --mixed_precision bf16 \
    --cache_latents \
    --cache_text_encoder_outputs

echo ""
echo "=== Training complete ==="
echo "Output file:"
ls -lh /workspace/output/\${LORA_NAME}*.safetensors
echo ""
echo "Download the final checkpoint (largest step number):"
echo "  scp from pod: /workspace/output/\${LORA_NAME}.safetensors"
TRAIN_SCRIPT
    chmod +x "$bundle/scripts/train_on_pod.sh"

    # Tar the bundle
    local tarball="${BUNDLE_DIR}/${lora_name}_bundle.tar.gz"
    tar -czf "$tarball" -C "$bundle" .
    local size
    size=$(du -sh "$tarball" | cut -f1)
    echo "Bundle ready: ${tarball} (${size})"
}

create_pod() {
    echo "Creating RunPod pod..."

    # Get API key from Vault
    local api_key
    api_key=$(curl -s -H "X-Vault-Token: $(cat /home/patrick/.vault-token 2>/dev/null || echo '')" \
        http://localhost:8200/v1/secret/data/runpod 2>/dev/null | \
        python3 -c "import sys,json; print(json.load(sys.stdin)['data']['data']['api_key'])" 2>/dev/null)

    if [[ -z "$api_key" || "$api_key" == "None" ]]; then
        echo "ERROR: Could not get RunPod API key from Vault (secret/runpod)"
        echo "Set it manually: export RUNPOD_API_KEY=<your key>"
        return 1
    fi

    export RUNPOD_API_KEY="$api_key"

    # Check for existing pod
    local existing
    existing=$("$RUNPODCTL" get pod 2>/dev/null | grep "$RUNPOD_POD_NAME" | head -1)
    if [[ -n "$existing" ]]; then
        local pod_id
        pod_id=$(echo "$existing" | awk '{print $1}')
        local status
        status=$(echo "$existing" | awk '{print $2}')
        echo "Found existing pod: ${pod_id} (${status})"
        if [[ "$status" == "EXITED" ]]; then
            echo "Restarting exited pod..."
            "$RUNPODCTL" start pod "$pod_id"
            sleep 10
        fi
        echo "$pod_id"
        return 0
    fi

    # Create new pod
    "$RUNPODCTL" create pod \
        --name "$RUNPOD_POD_NAME" \
        --gpuType "$RUNPOD_GPU" \
        --imageName "$RUNPOD_IMAGE" \
        --volumeSize "$RUNPOD_VOLUME_SIZE" \
        --ports "22/tcp,8888/http" \
        --startSsh

    echo "Pod created. Wait ~60s for SSH to become available."
}

upload_and_train() {
    local lora_name="$1"
    local tarball="${BUNDLE_DIR}/${lora_name}_bundle.tar.gz"

    if [[ ! -f "$tarball" ]]; then
        echo "ERROR: Bundle not found at ${tarball}. Run package_bundle first."
        return 1
    fi

    echo "=== Uploading bundle to RunPod ==="

    # Get pod SSH info
    local pod_ip pod_port
    pod_ip=$("$RUNPODCTL" get pod 2>/dev/null | grep "$RUNPOD_POD_NAME" | awk '{print $4}' | head -1)
    pod_port=$("$RUNPODCTL" get pod 2>/dev/null | grep "$RUNPOD_POD_NAME" | awk '{print $5}' | head -1)

    if [[ -z "$pod_ip" ]]; then
        echo "ERROR: Cannot find running pod. Create one first with --create-pod"
        return 1
    fi

    local SSH_CMD="ssh -i ${HOME}/.ssh/id_ed25519 -p ${pod_port} -o StrictHostKeyChecking=no root@${pod_ip}"

    # Upload bundle
    echo "Uploading ${tarball}..."
    scp -i "${HOME}/.ssh/id_ed25519" -P "$pod_port" -o StrictHostKeyChecking=no \
        "$tarball" "root@${pod_ip}:/workspace/"

    # Extract and run
    echo "Extracting and starting training..."
    $SSH_CMD << REMOTE_CMD
        mkdir -p /workspace/bundle
        cd /workspace/bundle
        tar -xzf /workspace/${lora_name}_bundle.tar.gz
        nohup bash /workspace/bundle/scripts/train_on_pod.sh > /workspace/training_${lora_name}.log 2>&1 &
        echo "Training started in background. Monitor with:"
        echo "  ssh root@${pod_ip} -p ${pod_port} 'tail -f /workspace/training_${lora_name}.log'"
REMOTE_CMD
}

download_results() {
    local lora_name="$1"
    echo "=== Downloading trained LoRA: ${lora_name} ==="

    local pod_ip pod_port
    pod_ip=$("$RUNPODCTL" get pod 2>/dev/null | grep "$RUNPOD_POD_NAME" | awk '{print $4}' | head -1)
    pod_port=$("$RUNPODCTL" get pod 2>/dev/null | grep "$RUNPOD_POD_NAME" | awk '{print $5}' | head -1)

    mkdir -p "$OUTPUT_DIR"

    # Download the final single-file LoRA (musubi-tuner dual-branch format)
    scp -i "${HOME}/.ssh/id_ed25519" -P "$pod_port" -o StrictHostKeyChecking=no \
        "root@${pod_ip}:/workspace/output/${lora_name}.safetensors" \
        "$OUTPUT_DIR/"

    echo "Downloaded to ${OUTPUT_DIR}/"
    ls -lh "${OUTPUT_DIR}/${lora_name}"* 2>/dev/null
}

# ── Main ──

case "${1:-}" in
    --list)
        show_list
        ;;
    --all)
        echo "Training all priority-1 motorcycle LoRAs..."
        for lora in moto_rider_pov moto_low_chase moto_tire_closeup; do
            if validate_dataset "$lora"; then
                package_bundle "$lora"
            else
                echo "Skipping ${lora} — dataset not ready"
            fi
        done
        ;;
    --create-pod)
        create_pod
        ;;
    --download)
        [[ -z "${2:-}" ]] && { echo "Usage: $0 --download <lora_name>"; exit 1; }
        download_results "$2"
        ;;
    --package)
        [[ -z "${2:-}" ]] && { echo "Usage: $0 --package <lora_name>"; exit 1; }
        validate_dataset "$2" && package_bundle "$2"
        ;;
    --train)
        [[ -z "${2:-}" ]] && { echo "Usage: $0 --train <lora_name>"; exit 1; }
        upload_and_train "$2"
        ;;
    --full)
        # Full pipeline: validate → package → create pod → upload → train
        [[ -z "${2:-}" ]] && { echo "Usage: $0 --full <lora_name>"; exit 1; }
        lora="$2"
        validate_dataset "$lora" || exit 1
        package_bundle "$lora"
        create_pod
        sleep 30  # Wait for pod to boot
        upload_and_train "$lora"
        echo ""
        echo "Training running on RunPod. Monitor and download when done:"
        echo "  $0 --download ${lora}"
        ;;
    "")
        echo "Motorcycle Camera LoRA Training — RunPod A100"
        echo ""
        echo "Usage:"
        echo "  $0 --list                    Show all LoRAs and dataset status"
        echo "  $0 --package <name>          Package training bundle"
        echo "  $0 --create-pod              Create/restart RunPod A100 pod"
        echo "  $0 --train <name>            Upload bundle and start training"
        echo "  $0 --download <name>         Download trained LoRA from pod"
        echo "  $0 --full <name>             Full pipeline: package → pod → train"
        echo "  $0 --all                     Package all priority-1 LoRAs"
        echo ""
        echo "Cost estimate: ~$1.19/hr × 2-3 hrs per LoRA = ~$3-4 per LoRA"
        echo "Full motorcycle pack (8 LoRAs): ~$25-30 total"
        ;;
    *)
        echo "Unknown option: $1"
        echo "Use --list, --package, --create-pod, --train, --download, --full, or --all"
        exit 1
        ;;
esac
