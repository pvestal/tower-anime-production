#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# Tower Anime Production — FramePack Pre-Flight & First Generation
# Based on actual repo state as of 2026-02-06
# ═══════════════════════════════════════════════════════════════
set -euo pipefail
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'

COMFYUI_URL="http://localhost:8188"
COMFYUI_MODELS="/mnt/1TB-storage/ComfyUI/models"
MODELS="/mnt/1TB-storage/models"

echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  Tower Anime — FramePack Pre-Flight Check         ${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"

# ─── FIX 1: Broken FramePackI2V symlink ───
echo ""
echo -e "${CYAN}[1/5] Fixing broken FramePackI2V symlink...${NC}"

BROKEN_LINK="${MODELS}/diffusion_models/FramePackI2V_HY_fp8_e4m3fn.safetensors"
REAL_FILE="${MODELS}/diffusion_models/Hyvid/FramePackI2V_HY_fp8_e4m3fn.safetensors"
COMFYUI_LINK="${COMFYUI_MODELS}/diffusion_models/FramePackI2V_HY_fp8_e4m3fn.safetensors"

if [ -L "$BROKEN_LINK" ] && [ ! -e "$BROKEN_LINK" ]; then
    echo "  Removing self-referencing symlink..."
    rm "$BROKEN_LINK"
fi

if [ -f "$REAL_FILE" ]; then
    REAL_SIZE=$(stat -c%s "$REAL_FILE" 2>/dev/null || echo "0")
    if [ "$REAL_SIZE" -gt 1000000000 ]; then
        # Fix the models/ symlink
        ln -sf "$REAL_FILE" "$BROKEN_LINK"
        echo -e "  ${GREEN}✅ Fixed: models/diffusion_models/FramePackI2V → Hyvid/ ($(numfmt --to=iec $REAL_SIZE))${NC}"

        # Fix the ComfyUI symlink too
        rm -f "$COMFYUI_LINK"
        ln -sf "$REAL_FILE" "$COMFYUI_LINK"
        echo -e "  ${GREEN}✅ Fixed: ComfyUI symlink → Hyvid/ copy${NC}"
    else
        echo -e "  ${RED}❌ Hyvid/ file exists but is too small (${REAL_SIZE} bytes)${NC}"
    fi
else
    echo -e "  ${RED}❌ No real FramePackI2V file found in Hyvid/${NC}"
    echo "  You need to download it:"
    echo "  wget -c https://huggingface.co/Kijai/HunyuanVideo_comfy/resolve/main/FramePackI2V_HY_fp8_e4m3fn.safetensors"
    echo "  -O ${REAL_FILE}"
fi

# ─── CHECK 2: All FramePack models ───
echo ""
echo -e "${CYAN}[2/5] Checking FramePack model inventory...${NC}"
ALL_GOOD=true

check_model() {
    local path="$1" label="$2" min_mb="$3"
    if [ -f "$path" ] || [ -L "$path" -a -e "$path" ]; then
        local size=$(stat -c%s "$(readlink -f "$path")" 2>/dev/null || echo "0")
        local size_mb=$((size / 1048576))
        if [ "$size_mb" -ge "$min_mb" ]; then
            echo -e "  ${GREEN}✅ ${label} (${size_mb}MB)${NC}"
        else
            echo -e "  ${RED}❌ ${label} — too small (${size_mb}MB, need >${min_mb}MB)${NC}"
            ALL_GOOD=false
        fi
    else
        echo -e "  ${RED}❌ ${label} — MISSING${NC}"
        ALL_GOOD=false
    fi
}

echo "  Diffusion models:"
check_model "${COMFYUI_MODELS}/diffusion_models/FramePackI2V_HY_fp8_e4m3fn.safetensors" "FramePackI2V (original)" 10000
check_model "${COMFYUI_MODELS}/diffusion_models/FramePack_F1_I2V_HY_20250503_fp8_e4m3fn.safetensors" "FramePack F1" 10000

echo "  Text encoders:"
check_model "${COMFYUI_MODELS}/text_encoders/clip_l.safetensors" "clip_l" 200
check_model "${COMFYUI_MODELS}/text_encoders/llava_llama3_fp16.safetensors" "llava_llama3_fp16" 10000

echo "  CLIP vision:"
check_model "${COMFYUI_MODELS}/../models/clip_vision/sigclip_vision_patch14_384.safetensors" "sigclip_vision_384" 500
# Also check ComfyUI's own clip_vision dir
check_model "/mnt/1TB-storage/models/clip_vision/sigclip_vision_patch14_384.safetensors" "sigclip_vision_384 (models/)" 500

echo "  VAE:"
check_model "${COMFYUI_MODELS}/vae/hunyuan_video_vae_bf16.safetensors" "hunyuan_video_vae_bf16" 400

# ─── CHECK 3: ComfyUI status ───
echo ""
echo -e "${CYAN}[3/5] ComfyUI status...${NC}"
if curl -sf "${COMFYUI_URL}/system_stats" &>/dev/null; then
    VRAM_FREE=$(curl -sf "${COMFYUI_URL}/system_stats" | python3 -c "
import json,sys
d=json.load(sys.stdin)
devs = d.get('devices',[])
if devs:
    free_gb = devs[0].get('vram_free',0) / (1024**3)
    total_gb = devs[0].get('vram_total',0) / (1024**3)
    name = devs[0].get('name','unknown')
    print(f'{name} — {free_gb:.1f}GB free / {total_gb:.1f}GB total')
")
    echo -e "  ${GREEN}✅ ComfyUI running: ${VRAM_FREE}${NC}"

    # Check FramePack nodes exist
    FP_NODES=$(curl -sf "${COMFYUI_URL}/object_info" | python3 -c "
import json,sys
d=json.load(sys.stdin)
fp = [n for n in d if 'framepack' in n.lower() or 'FramePack' in n]
print(len(fp))
" 2>/dev/null || echo "0")
    if [ "$FP_NODES" -gt 0 ]; then
        echo -e "  ${GREEN}✅ FramePack nodes loaded: ${FP_NODES} nodes${NC}"
    else
        echo -e "  ${RED}❌ No FramePack nodes — restart ComfyUI after fixing models${NC}"
        ALL_GOOD=false
    fi
else
    echo -e "  ${RED}❌ ComfyUI not responding at ${COMFYUI_URL}${NC}"
    ALL_GOOD=false
fi

# ─── CHECK 4: Existing character LoRAs (for future use) ───
echo ""
echo -e "${CYAN}[4/5] Character LoRAs (LTX-based, NOT FramePack-compatible)...${NC}"
echo "  Note: These are SD1.5/LTX LoRAs. FramePack uses HunyuanVideo."
echo "  For FramePack character consistency, use image-to-video (I2V) mode."
echo ""
echo "  Tokyo Debt Desire characters:"
for lora in mei_face mei_body-000005 mei_working_v1 kai_nakamura_optimized_v1 rina_tdd_real_v2; do
    f="/mnt/1TB-storage/models/loras/${lora}.safetensors"
    if [ -f "$f" ]; then
        size=$(ls -lh "$f" | awk '{print $5}')
        echo "    ${lora}: ${size}"
    fi
done
echo ""
echo "  Other characters:"
for lora in ryuu_working_v1 cyberpunk_style_proper; do
    f="/mnt/1TB-storage/models/loras/${lora}.safetensors"
    if [ -f "$f" ]; then
        size=$(ls -lh "$f" | awk '{print $5}')
        echo "    ${lora}: ${size}"
    fi
done

# ─── CHECK 5: Symlink clip_vision into ComfyUI if needed ───
echo ""
echo -e "${CYAN}[5/5] Ensuring clip_vision is accessible to ComfyUI...${NC}"
COMFYUI_CV="${COMFYUI_MODELS}/clip_vision"
mkdir -p "$COMFYUI_CV"
if [ ! -e "${COMFYUI_CV}/sigclip_vision_patch14_384.safetensors" ]; then
    ln -sf "/mnt/1TB-storage/models/clip_vision/sigclip_vision_patch14_384.safetensors" "${COMFYUI_CV}/"
    echo -e "  ${GREEN}✅ Symlinked sigclip into ComfyUI/models/clip_vision/${NC}"
else
    echo -e "  ${GREEN}✅ Already present${NC}"
fi

# ─── SUMMARY ───
echo ""
echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"
if $ALL_GOOD; then
    echo -e "${GREEN}  All checks passed — ready to generate!${NC}"
    echo ""
    echo "  Next: python3 tower_framepack_generate.py --check"
    echo "        python3 tower_framepack_generate.py --project tdd --scene mei_office"
else
    echo -e "${YELLOW}  Some issues found — fix above, then restart ComfyUI${NC}"
    echo ""
    echo "  After fixing: sudo systemctl restart comfyui"
    echo "  (or however you launch ComfyUI)"
fi
echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"