#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# Tower Anime Production — FramePack Setup for RTX 3060 12GB
# ═══════════════════════════════════════════════════════════════
#
# FramePack generates 60-second, 30fps videos using only 6GB VRAM.
# Built on HunyuanVideo — NOT compatible with LTX LoRAs.
#
# Two FramePack models available:
#   - FramePackI2V (original) — reverse generation, first+last frame anchoring
#   - FramePack-F1 (May 2025) — forward-only, better temporal coherence
#
# For RTX 3060: use FP8 versions of both
#
# Usage: bash setup_framepack_corrected.sh
# ═══════════════════════════════════════════════════════════════

set -euo pipefail
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'

COMFYUI_DIR="/mnt/1TB-storage/ComfyUI"
MODELS_DIR="/mnt/1TB-storage/models"
CUSTOM_NODES="${COMFYUI_DIR}/custom_nodes"

echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  FramePack Setup for Tower Anime Production       ${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"

# ─── STEP 1: Verify ComfyUI ───
echo ""
echo -e "${CYAN}[1/6] Checking ComfyUI...${NC}"
if [ -d "$COMFYUI_DIR" ]; then
    echo -e "  ${GREEN}✅ ComfyUI found at ${COMFYUI_DIR}${NC}"
else
    echo -e "  ${RED}❌ ComfyUI not found at ${COMFYUI_DIR}${NC}"
    echo "  Please set COMFYUI_DIR to your ComfyUI installation path"
    exit 1
fi

# Check if ComfyUI is running
if curl -sf http://localhost:8188/system_stats &>/dev/null; then
    echo -e "  ${GREEN}✅ ComfyUI running on port 8188${NC}"
else
    echo -e "  ${YELLOW}⚠️  ComfyUI not running — will need restart after setup${NC}"
fi

# ─── STEP 2: Install FramePack Wrapper Plus (LoRA + F1 support) ───
echo ""
echo -e "${CYAN}[2/6] Installing ComfyUI-FramePackWrapper_Plus...${NC}"

# Use the Plus wrapper — it has F1 sampler + LoRA + timestamped prompts
if [ -d "${CUSTOM_NODES}/ComfyUI-FramePackWrapper_Plus" ]; then
    echo "  Updating existing installation..."
    cd "${CUSTOM_NODES}/ComfyUI-FramePackWrapper_Plus"
    git pull
else
    echo "  Cloning fresh..."
    cd "${CUSTOM_NODES}"
    git clone https://github.com/ShmuelRonen/ComfyUI-FramePackWrapper_Plus.git
fi

# Also install the original wrapper (more stable, wider community)
if [ -d "${CUSTOM_NODES}/ComfyUI-FramePackWrapper" ]; then
    echo "  Updating ComfyUI-FramePackWrapper..."
    cd "${CUSTOM_NODES}/ComfyUI-FramePackWrapper"
    git pull
else
    echo "  Cloning ComfyUI-FramePackWrapper..."
    cd "${CUSTOM_NODES}"
    git clone https://github.com/kijai/ComfyUI-FramePackWrapper.git
fi

# Install dependencies
echo "  Installing Python dependencies..."
if [ -f "${COMFYUI_DIR}/venv/bin/pip" ]; then
    ${COMFYUI_DIR}/venv/bin/pip install -r "${CUSTOM_NODES}/ComfyUI-FramePackWrapper/requirements.txt" 2>/dev/null || \
    ${COMFYUI_DIR}/venv/bin/pip install -r "${CUSTOM_NODES}/ComfyUI-FramePackWrapper/requirements.txt"
else
    pip install -r "${CUSTOM_NODES}/ComfyUI-FramePackWrapper/requirements.txt" --break-system-packages
fi
echo -e "  ${GREEN}✅ FramePack wrappers installed${NC}"

# ─── STEP 3: Create model directories ───
echo ""
echo -e "${CYAN}[3/6] Setting up model directories...${NC}"

mkdir -p "${MODELS_DIR}/diffusion_models"
mkdir -p "${MODELS_DIR}/text_encoders"
mkdir -p "${MODELS_DIR}/clip_vision"
mkdir -p "${MODELS_DIR}/vae"

# Ensure ComfyUI model dirs exist and are symlinked
for dir in diffusion_models text_encoders clip_vision vae; do
    mkdir -p "${COMFYUI_DIR}/models/${dir}"
done

echo -e "  ${GREEN}✅ Directories ready${NC}"

# ─── STEP 4: Download FramePack models (FP8 for RTX 3060) ───
echo ""
echo -e "${CYAN}[4/6] Downloading FramePack models (FP8 for 12GB VRAM)...${NC}"
echo "  This will download ~25GB total. Downloads resume if interrupted."
echo ""

# --- Diffusion Models ---
# Original FramePack I2V (FP8)
FP_I2V="${MODELS_DIR}/diffusion_models/FramePackI2V_HY_fp8_e4m3fn.safetensors"
if [ -f "$FP_I2V" ] && [ $(stat -c%s "$FP_I2V" 2>/dev/null) -gt 1000000000 ]; then
    echo -e "  ${GREEN}✅ FramePackI2V FP8 already downloaded${NC}"
else
    echo "  📥 Downloading FramePackI2V_HY_fp8_e4m3fn.safetensors (~13GB)..."
    wget -c -q --show-progress \
        "https://huggingface.co/Kijai/HunyuanVideo_comfy/resolve/main/FramePackI2V_HY_fp8_e4m3fn.safetensors" \
        -O "$FP_I2V"
fi

# FramePack F1 (FP8) — newer, forward-only, better coherence
FP_F1="${MODELS_DIR}/diffusion_models/FramePack_F1_I2V_HY_20250503_fp8_e4m3fn.safetensors"
if [ -f "$FP_F1" ] && [ $(stat -c%s "$FP_F1" 2>/dev/null) -gt 1000000000 ]; then
    echo -e "  ${GREEN}✅ FramePack F1 FP8 already downloaded${NC}"
else
    echo "  📥 Downloading FramePack_F1 FP8 (~13GB)..."
    wget -c -q --show-progress \
        "https://huggingface.co/kabachuha/FramePack_F1_I2V_HY_20250503_comfy/resolve/main/FramePack_F1_I2V_HY_20250503_fp8_e4m3fn.safetensors" \
        -O "$FP_F1"
fi

# --- Text Encoders ---
CLIP_L="${MODELS_DIR}/text_encoders/clip_l.safetensors"
if [ -f "$CLIP_L" ]; then
    echo -e "  ${GREEN}✅ clip_l.safetensors exists${NC}"
else
    echo "  📥 Downloading clip_l.safetensors..."
    wget -c -q --show-progress \
        "https://huggingface.co/Comfy-Org/HunyuanVideo_repackaged/resolve/main/split_files/text_encoders/clip_l.safetensors" \
        -O "$CLIP_L"
fi

LLAVA="${MODELS_DIR}/text_encoders/llava_llama3_fp16.safetensors"
if [ -f "$LLAVA" ]; then
    echo -e "  ${GREEN}✅ llava_llama3_fp16.safetensors exists${NC}"
else
    echo "  📥 Downloading llava_llama3_fp16.safetensors (~10GB)..."
    wget -c -q --show-progress \
        "https://huggingface.co/Comfy-Org/HunyuanVideo_repackaged/resolve/main/split_files/text_encoders/llava_llama3_fp16.safetensors" \
        -O "$LLAVA"
fi

# --- CLIP Vision ---
SIGCLIP="${MODELS_DIR}/clip_vision/sigclip_vision_patch14_384.safetensors"
if [ -f "$SIGCLIP" ]; then
    echo -e "  ${GREEN}✅ sigclip_vision_patch14_384.safetensors exists${NC}"
else
    echo "  📥 Downloading sigclip_vision_patch14_384.safetensors..."
    wget -c -q --show-progress \
        "https://huggingface.co/Comfy-Org/sigclip_vision_384/resolve/main/sigclip_vision_patch14_384.safetensors" \
        -O "$SIGCLIP"
fi

# --- VAE ---
HY_VAE="${MODELS_DIR}/vae/hunyuan_video_vae_bf16.safetensors"
if [ -f "$HY_VAE" ]; then
    echo -e "  ${GREEN}✅ hunyuan_video_vae_bf16.safetensors exists${NC}"
else
    echo "  📥 Downloading hunyuan_video_vae_bf16.safetensors..."
    wget -c -q --show-progress \
        "https://huggingface.co/Comfy-Org/HunyuanVideo_repackaged/resolve/main/split_files/vae/hunyuan_video_vae_bf16.safetensors" \
        -O "$HY_VAE"
fi

# ─── STEP 5: Create symlinks into ComfyUI ───
echo ""
echo -e "${CYAN}[5/6] Creating symlinks to ComfyUI model directories...${NC}"

# Diffusion models
for f in "${MODELS_DIR}/diffusion_models"/FramePack*.safetensors; do
    [ -f "$f" ] && ln -sf "$f" "${COMFYUI_DIR}/models/diffusion_models/" 2>/dev/null
done

# Text encoders
for f in "${MODELS_DIR}/text_encoders"/*.safetensors; do
    [ -f "$f" ] && ln -sf "$f" "${COMFYUI_DIR}/models/text_encoders/" 2>/dev/null
done

# CLIP vision
for f in "${MODELS_DIR}/clip_vision"/*.safetensors; do
    [ -f "$f" ] && ln -sf "$f" "${COMFYUI_DIR}/models/clip_vision/" 2>/dev/null
done

# VAE
for f in "${MODELS_DIR}/vae"/*.safetensors; do
    [ -f "$f" ] && ln -sf "$f" "${COMFYUI_DIR}/models/vae/" 2>/dev/null
done

echo -e "  ${GREEN}✅ Symlinks created${NC}"

# ─── STEP 6: Verify ───
echo ""
echo -e "${CYAN}[6/6] Verification${NC}"
echo ""
echo "  Models in diffusion_models/:"
ls -lh "${COMFYUI_DIR}/models/diffusion_models"/FramePack* 2>/dev/null | awk '{print "    "$NF, $5}' || echo "    None found"
echo ""
echo "  Text encoders:"
ls -lh "${COMFYUI_DIR}/models/text_encoders"/*.safetensors 2>/dev/null | awk '{print "    "$NF, $5}' || echo "    None found"
echo ""
echo "  CLIP vision:"
ls -lh "${COMFYUI_DIR}/models/clip_vision"/*.safetensors 2>/dev/null | awk '{print "    "$NF, $5}' || echo "    None found"
echo ""
echo "  VAE:"
ls -lh "${COMFYUI_DIR}/models/vae"/*.safetensors 2>/dev/null | awk '{print "    "$NF, $5}' || echo "    None found"

echo ""
echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Setup complete!${NC}"
echo ""
echo "  Next steps:"
echo "  1. Restart ComfyUI: sudo systemctl restart comfyui"
echo "     (or kill the current process and restart)"
echo "  2. Open ComfyUI at http://localhost:8188"
echo "  3. Load example workflow from:"
echo "     ${CUSTOM_NODES}/ComfyUI-FramePackWrapper/example_workflows/"
echo ""
echo "  For RTX 3060 12GB settings:"
echo "    - Use FP8 model (FramePackI2V_HY_fp8_e4m3fn.safetensors)"
echo "    - Set gpu_memory_preservation: 4-6 GB"
echo "    - Start with 5 second videos, scale up to 60s"
echo "    - Resolution: 544x704 or lower initially"
echo ""
echo "  LoRA note: Only HunyuanVideo LoRAs work with FramePack."
echo "  Your LTX LoRAs are NOT compatible. To train new ones,"
echo "  use finetrainers: github.com/a-r-r-o-w/finetrainers"
echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"