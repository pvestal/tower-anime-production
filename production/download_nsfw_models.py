#!/usr/bin/env python3
"""
Download NSFW models from Civitai with API authentication
"""

import os
import sys
import requests
from pathlib import Path
import json

# Model directory
LORA_DIR = "/mnt/1TB-storage/ComfyUI/models/loras"

def download_civitai_model(api_token, model_version_id, output_path, model_name):
    """Download a model from Civitai using API token"""

    # Check if already exists
    if Path(output_path).exists():
        print(f"✅ {model_name} already exists at {output_path}")
        return True

    print(f"📥 Downloading {model_name}...")
    print(f"   Model Version ID: {model_version_id}")
    print(f"   Output: {output_path}")

    # Civitai API download URL with token as query parameter
    url = f"https://civitai.com/api/download/models/{model_version_id}?token={api_token}"

    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
    }

    try:
        response = requests.get(url, headers=headers, stream=True)
        response.raise_for_status()

        # Get total size
        total_size = int(response.headers.get('content-length', 0))

        # Download with progress
        with open(output_path, 'wb') as f:
            downloaded = 0
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        percent = (downloaded / total_size) * 100
                        print(f"\r   Progress: {percent:.1f}%", end='')

        print(f"\n✅ Successfully downloaded {model_name}")
        return True

    except Exception as e:
        print(f"\n❌ Error downloading {model_name}: {e}")
        return False

def main():
    """Main download function"""

    print("🔞 NSFW Model Downloader for Tower Anime Production")
    print("=" * 60)

    # Get API token from environment or input
    api_token = os.environ.get('CIVITAI_API_TOKEN')
    if not api_token:
        api_token = input("Enter your Civitai API token: ").strip()

    if not api_token:
        print("❌ No API token provided")
        sys.exit(1)

    # Models to download (with correct version IDs from API)
    models = [
        {
            "name": "LTX Orgasm LoRA",
            "version_id": "2597222",  # Latest version from API
            "filename": "ltx_orgasm.safetensors",
            "url": "https://civitai.com/models/2176039/orgasm"
        },
        {
            "name": "WAN-DR34ML4Y All-in-One NSFW",
            "version_id": "2553271",  # Latest version from API
            "filename": "wan_dr34ml4y_nsfw.safetensors",
            "url": "https://civitai.com/models/1811313/wan-dr34ml4y-all-in-one-nsfw"
        }
    ]

    print(f"\n📁 Download directory: {LORA_DIR}")
    print(f"📦 Models to download: {len(models)}\n")

    success_count = 0
    for model in models:
        output_path = os.path.join(LORA_DIR, model['filename'])
        if download_civitai_model(api_token, model['version_id'], output_path, model['name']):
            success_count += 1
        print()

    print("=" * 60)
    print(f"✅ Downloaded {success_count}/{len(models)} models successfully")

    if success_count == len(models):
        print("\n🎉 All NSFW models downloaded successfully!")
        print("You can now use these LoRAs in your pipelines:")
        for model in models:
            print(f"   - {model['filename']}")
    else:
        print("\n⚠️ Some downloads failed. Check your API token and try again.")

if __name__ == "__main__":
    main()