#!/bin/bash
# Civitai Model Download Script
# Run this script to download NSFW models for Tower Anime Production

LORA_DIR="/mnt/1TB-storage/ComfyUI/models/loras"
CHECKPOINT_DIR="/mnt/1TB-storage/ComfyUI/models/checkpoints"

echo "🚀 Tower Anime Production - Model Downloader"
echo "==========================================="

# Check if directories exist
if [ ! -d "$LORA_DIR" ]; then
    echo "❌ LoRA directory not found: $LORA_DIR"
    exit 1
fi

echo "📁 LoRA directory: $LORA_DIR"
echo "📁 Checkpoint directory: $CHECKPOINT_DIR"

# Function to download with wget
download_model() {
    local url=$1
    local output=$2
    local name=$3

    echo ""
    echo "📥 Downloading: $name"
    echo "   URL: $url"
    echo "   Output: $output"

    if [ -f "$output" ]; then
        echo "   ✅ Already exists, skipping..."
    else
        wget -c "$url" -O "$output"
        if [ $? -eq 0 ]; then
            echo "   ✅ Downloaded successfully!"
        else
            echo "   ❌ Download failed!"
        fi
    fi
}

# LTX NSFW LoRAs
echo ""
echo "📥 Downloading LTX NSFW LoRAs..."
echo "NOTE: These require Civitai authentication"
echo ""

# LTX Orgasm LoRA (786.5 MB)
# https://civitai.com/models/2176039/orgasm
echo "1. LTX Orgasm LoRA - Requires manual download from:"
echo "   https://civitai.com/models/2176039/orgasm"
echo "   Save as: $LORA_DIR/ltx_orgasm.safetensors"
echo ""

# LTX-2-I2V NSFW LoRA
# https://civitai.com/models/2310920/ltx-2-i2v-nsfw-furry-multi-purpose-sex-lora
echo "2. LTX-2-I2V NSFW Multi-Purpose LoRA - Requires manual download from:"
echo "   https://civitai.com/models/2310920/ltx-2-i2v-nsfw-furry-multi-purpose-sex-lora"
echo "   Save as: $LORA_DIR/ltx_nsfw_multipurpose.safetensors"
echo ""

# WAN-DR34ML4Y All-in-One NSFW
# https://civitai.com/models/1811313/wan-dr34ml4y-all-in-one-nsfw
echo "3. WAN-DR34ML4Y All-in-One NSFW - Requires manual download from:"
echo "   https://civitai.com/models/1811313/wan-dr34ml4y-all-in-one-nsfw"
echo "   Save as: $LORA_DIR/wan_dr34ml4y_nsfw.safetensors"

echo ""
echo "✅ Download script complete!"
echo ""
echo "NOTE: You need to add actual download URLs from Civitai"
echo "      1. Go to the model page"
echo "      2. Click download button"
echo "      3. Copy the actual download link"
echo "      4. Add to this script"
