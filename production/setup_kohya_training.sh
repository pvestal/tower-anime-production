#!/bin/bash
# Setup Kohya_ss for actual LoRA training

echo "🔧 Setting up Kohya_ss for LTX LoRA training"
echo "============================================"

# Check if already installed
if [ -d "/opt/kohya_ss" ]; then
    echo "✅ Kohya_ss already installed at /opt/kohya_ss"
else
    echo "📥 Installing Kohya_ss..."
    cd /opt
    git clone https://github.com/kohya-ss/sd-scripts.git kohya_ss
    cd kohya_ss

    # Create virtual environment
    python3 -m venv venv
    source venv/bin/activate

    # Install requirements
    pip install --upgrade pip
    pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
    pip install -r requirements.txt
    pip install xformers

    echo "✅ Kohya_ss installed"
fi

# Install additional tools for video processing
echo ""
echo "📦 Installing additional tools..."

# AI-toolkit for easier training
if [ ! -d "/opt/ai-toolkit" ]; then
    cd /opt
    git clone https://github.com/ostris/ai-toolkit.git
    cd ai-toolkit
    git submodule update --init --recursive
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "Available training tools:"
echo "  1. Kohya_ss: /opt/kohya_ss"
echo "  2. AI-toolkit: /opt/ai-toolkit"