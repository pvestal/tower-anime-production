#!/bin/bash
# Complete the FramePack setup - download remaining models and create symlinks

set -euo pipefail
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'

COMFYUI_DIR="/mnt/1TB-storage/ComfyUI"
MODELS_DIR="/mnt/1TB-storage/models"

echo -e "${CYAN}Completing FramePack Setup...${NC}"

# --- Text Encoders ---
echo -e "${CYAN}Checking text encoders...${NC}"
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
echo -e "${CYAN}Checking CLIP vision...${NC}"
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
echo -e "${CYAN}Checking VAE...${NC}"
HY_VAE="${MODELS_DIR}/vae/hunyuan_video_vae_bf16.safetensors"
if [ -f "$HY_VAE" ]; then
    echo -e "  ${GREEN}✅ hunyuan_video_vae_bf16.safetensors exists${NC}"
else
    echo "  📥 Downloading hunyuan_video_vae_bf16.safetensors..."
    wget -c -q --show-progress \
        "https://huggingface.co/Comfy-Org/HunyuanVideo_repackaged/resolve/main/split_files/vae/hunyuan_video_vae_bf16.safetensors" \
        -O "$HY_VAE"
fi

# Create symlinks
echo ""
echo -e "${CYAN}Creating symlinks to ComfyUI...${NC}"

# Diffusion models
for f in "${MODELS_DIR}/diffusion_models"/FramePack*.safetensors; do
    if [ -f "$f" ]; then
        basename=$(basename "$f")
        ln -sf "$f" "${COMFYUI_DIR}/models/diffusion_models/$basename" 2>/dev/null && \
        echo -e "  ✅ Linked $basename"
    fi
done

# Text encoders
for f in "${MODELS_DIR}/text_encoders"/*.safetensors; do
    if [ -f "$f" ]; then
        basename=$(basename "$f")
        ln -sf "$f" "${COMFYUI_DIR}/models/text_encoders/$basename" 2>/dev/null && \
        echo -e "  ✅ Linked $basename"
    fi
done

# CLIP vision
for f in "${MODELS_DIR}/clip_vision"/*.safetensors; do
    if [ -f "$f" ]; then
        basename=$(basename "$f")
        ln -sf "$f" "${COMFYUI_DIR}/models/clip_vision/$basename" 2>/dev/null && \
        echo -e "  ✅ Linked $basename"
    fi
done

# VAE
for f in "${MODELS_DIR}/vae"/*.safetensors; do
    if [ -f "$f" ]; then
        basename=$(basename "$f")
        ln -sf "$f" "${COMFYUI_DIR}/models/vae/$basename" 2>/dev/null && \
        echo -e "  ✅ Linked $basename"
    fi
done

echo ""
echo -e "${CYAN}Final Verification${NC}"
echo ""
echo "  Diffusion models:"
ls -lh "${COMFYUI_DIR}/models/diffusion_models"/FramePack* 2>/dev/null | awk '{print "    "$(NF-3), $(NF)}' || echo "    None found"
echo ""
echo "  Text encoders:"
ls -lh "${COMFYUI_DIR}/models/text_encoders"/{clip_l,llava_llama3_fp16}.safetensors 2>/dev/null | awk '{print "    "$(NF-3), $(NF)}' || echo "    None found"
echo ""
echo "  CLIP vision:"
ls -lh "${COMFYUI_DIR}/models/clip_vision"/sigclip*.safetensors 2>/dev/null | awk '{print "    "$(NF-3), $(NF)}' || echo "    None found"
echo ""
echo "  VAE:"
ls -lh "${COMFYUI_DIR}/models/vae"/hunyuan*.safetensors 2>/dev/null | awk '{print "    "$(NF-3), $(NF)}' || echo "    None found"

echo ""
echo -e "${GREEN}✅ FramePack setup complete!${NC}"
echo ""
echo "Next steps:"
echo "  1. Restart ComfyUI to load new nodes"
echo "  2. Example workflows: ${COMFYUI_DIR}/custom_nodes/ComfyUI-FramePackWrapper/example_workflows/"
echo ""
echo "RTX 3060 12GB optimal settings:"
echo "  - Model: FramePackI2V_HY_fp8_e4m3fn.safetensors (FP8)"
echo "  - GPU Memory Preservation: 4-6 GB"
echo "  - Start with 544x704 resolution, 5-second videos"
echo "  - Scale up to 60 seconds once working"