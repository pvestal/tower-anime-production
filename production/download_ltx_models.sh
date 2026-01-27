#!/bin/bash
# Download LTX-2B Video Model and Requirements
# Run this script to download all required LTX models in background

echo "🚀 Starting LTX-2B Model Downloads"
echo "=================================="
echo ""

# Create directories if they don't exist
mkdir -p /mnt/1TB-storage/ComfyUI/models/checkpoints
mkdir -p /mnt/1TB-storage/ComfyUI/models/text_encoders
mkdir -p /mnt/1TB-storage/ComfyUI/models/vae

# Download LTX-2B Model (~19GB)
echo "📥 Downloading LTX-2B Model (19GB)..."
wget -c -b \
  https://huggingface.co/Lightricks/LTX-Video/resolve/main/ltx-video-2b-v1.safetensors \
  -O /mnt/1TB-storage/ComfyUI/models/checkpoints/ltx_v2_2b.safetensors \
  2>&1 | tee ltx_download.log &

LTX_PID=$!
echo "   ✅ Started download (PID: $LTX_PID)"
echo "   📄 Log file: ltx_download.log"
echo ""

# Download T5XXL Text Encoder (~10GB)
echo "📥 Downloading T5XXL Text Encoder (10GB)..."
wget -c -b \
  https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp16.safetensors \
  -O /mnt/1TB-storage/ComfyUI/models/text_encoders/t5xxl_fp16.safetensors \
  2>&1 | tee t5xxl_download.log &

T5_PID=$!
echo "   ✅ Started download (PID: $T5_PID)"
echo "   📄 Log file: t5xxl_download.log"
echo ""

# Download LTX VAE (~400MB)
echo "📥 Downloading LTX VAE (400MB)..."
wget -c -b \
  https://huggingface.co/Lightricks/LTX-Video/resolve/main/vae/diffusion_pytorch_model.safetensors \
  -O /mnt/1TB-storage/ComfyUI/models/vae/ltx_vae.safetensors \
  2>&1 | tee vae_download.log &

VAE_PID=$!
echo "   ✅ Started download (PID: $VAE_PID)"
echo "   📄 Log file: vae_download.log"
echo ""

echo "=================================="
echo "✅ All downloads started in background!"
echo ""
echo "📊 Monitor progress with:"
echo "   tail -f ltx_download.log"
echo "   tail -f t5xxl_download.log"
echo "   tail -f vae_download.log"
echo ""
echo "Or check download status:"
echo "   ps aux | grep wget"
echo ""
echo "⏱️ Estimated download time: 30-60 minutes (depending on connection)"
echo ""
echo "Process IDs:"
echo "   LTX Model: $LTX_PID"
echo "   T5XXL: $T5_PID"
echo "   VAE: $VAE_PID"