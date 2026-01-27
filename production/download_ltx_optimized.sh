#!/bin/bash
# Optimized LTX Model Downloads for 12GB VRAM
# Using distilled and FP8 models for better performance on RTX 3060

echo "🚀 LTX Optimized Model Downloads for 12GB VRAM"
echo "=============================================="
echo ""

# Model directories
MODEL_DIR="/mnt/1TB-storage/ComfyUI/models"
CHECKPOINT_DIR="$MODEL_DIR/checkpoints"
VAE_DIR="$MODEL_DIR/vae"
LORA_DIR="$MODEL_DIR/loras"
CLIP_DIR="$MODEL_DIR/clip"

# Create directories if they don't exist
mkdir -p $CHECKPOINT_DIR $VAE_DIR $LORA_DIR $CLIP_DIR

echo "📋 Downloading optimized models for 12GB VRAM..."
echo ""

# 1. FP8 Distilled Model (25GB - most efficient for low VRAM)
echo "📥 [1/5] LTX-2 19B Distilled FP8 (25GB - Optimized for low VRAM)"
if [ -f "$CHECKPOINT_DIR/ltx-2-19b-distilled-fp8.safetensors" ]; then
    echo "   ✅ Already downloading/exists"
else
    wget -b -c \
        "https://huggingface.co/Lightricks/LTX-2/resolve/main/ltx-2-19b-distilled-fp8.safetensors" \
        -O "$CHECKPOINT_DIR/ltx-2-19b-distilled-fp8.safetensors" 2>&1 &
    echo "   ⏳ Started download (check wget-log)"
fi
echo ""

# 2. Distilled LoRA (for efficiency)
echo "📥 [2/5] LTX-2 Distilled LoRA 384 (for efficiency)"
if [ -f "$LORA_DIR/ltx-2-19b-distilled-lora-384.safetensors" ]; then
    echo "   ✅ Already downloading/exists"
else
    wget -b -c \
        "https://huggingface.co/Lightricks/LTX-2/resolve/main/ltx-2-19b-distilled-lora-384.safetensors" \
        -O "$LORA_DIR/ltx-2-19b-distilled-lora-384.safetensors" 2>&1 &
    echo "   ⏳ Started download"
fi
echo ""

# 3. VAE (Required for decoding)
echo "📥 [3/5] LTX VAE (1.6GB)"
if [ -f "$VAE_DIR/ltx_vae.safetensors" ]; then
    echo "   ✅ Already exists"
else
    wget -b -c \
        "https://huggingface.co/Lightricks/LTX-Video/resolve/main/vae/diffusion_pytorch_model.safetensors" \
        -O "$VAE_DIR/ltx_vae.safetensors" 2>&1 &
    echo "   ⏳ Started download"
fi
echo ""

# 4. T5XXL FP8 (Smaller text encoder)
echo "📥 [4/5] T5XXL FP8 Text Encoder (4.9GB - Smaller version)"
if [ -f "$CLIP_DIR/t5xxl_fp8_e4m3fn.safetensors" ]; then
    echo "   ✅ Already exists"
else
    wget -b -c \
        "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp8_e4m3fn.safetensors" \
        -O "$CLIP_DIR/t5xxl_fp8_e4m3fn.safetensors" 2>&1 &
    echo "   ⏳ Started download"
fi
echo ""

# 5. CLIP-L (Required for dual encoding)
echo "📥 [5/5] CLIP-L Encoder (246MB)"
if [ -f "$CLIP_DIR/clip_l.safetensors" ]; then
    echo "   ✅ Already exists"
else
    wget -b -c \
        "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors" \
        -O "$CLIP_DIR/clip_l.safetensors" 2>&1 &
    echo "   ⏳ Started download"
fi
echo ""

# Show existing models that can be used
echo "=============================================="
echo "📦 Available Models for Use:"
echo ""

if [ -f "$CHECKPOINT_DIR/ltx-2-19b-distilled.safetensors" ]; then
    echo "✅ ltx-2-19b-distilled.safetensors (23GB) - Can use now!"
fi

if [ -f "$VAE_DIR/ltx2_vae.safetensors" ]; then
    echo "✅ ltx2_vae.safetensors (1.6GB) - Ready!"
fi

if [ -f "$CLIP_DIR/t5xxl_fp16.safetensors" ]; then
    echo "✅ t5xxl_fp16.safetensors (9.2GB) - Ready!"
fi

echo ""
echo "🔥 NSFW LoRAs Available:"
ls -1 $LORA_DIR/*LTX*.safetensors $LORA_DIR/*ltx*.safetensors 2>/dev/null | xargs -n1 basename | head -10

echo ""
echo "=============================================="
echo "💡 Tips for 12GB VRAM:"
echo ""
echo "1. Use --lowvram or --medvram flags when starting ComfyUI:"
echo "   python main.py --lowvram"
echo ""
echo "2. Use FP8 models instead of FP16 when available"
echo ""
echo "3. Reduce resolution to 512x384 or 768x512 for generation"
echo ""
echo "4. Use shorter video lengths (2-3 seconds / 48-72 frames)"
echo ""
echo "5. Clear VRAM between generations with ComfyUI Manager"
echo ""
echo "Monitor downloads: tail -f wget-log*"
echo ""