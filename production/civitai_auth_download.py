#!/usr/bin/env python3
"""
Civitai authenticated downloader using API token
Works with login-required models
"""

import os
import requests
import json
from pathlib import Path

API_TOKEN = "b49c4e3f5c0d4a23b8f1e3d2a7c9b5e6"
OUTPUT_DIR = "/mnt/1TB-storage/ComfyUI/models/loras"

def download_model(model_version_id, output_filename):
    """Download model using API token with proper headers"""

    print(f"\n📥 Downloading model version {model_version_id}")

    # Try multiple authentication methods
    methods = [
        {
            "name": "Method 1: Token in URL + Headers",
            "url": f"https://civitai.com/api/download/models/{model_version_id}?token={API_TOKEN}",
            "headers": {
                "Authorization": f"Bearer {API_TOKEN}",
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
                "Accept": "*/*",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive"
            }
        },
        {
            "name": "Method 2: API Key Header",
            "url": f"https://civitai.com/api/download/models/{model_version_id}",
            "headers": {
                "API-Key": API_TOKEN,
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
                "Accept": "*/*"
            }
        },
        {
            "name": "Method 3: Token as Cookie",
            "url": f"https://civitai.com/api/download/models/{model_version_id}",
            "headers": {
                "Cookie": f"civitai-token={API_TOKEN}",
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
                "Accept": "*/*"
            }
        }
    ]

    output_path = os.path.join(OUTPUT_DIR, output_filename)

    for method in methods:
        print(f"\nTrying {method['name']}...")

        try:
            # Use session for better cookie/auth handling
            session = requests.Session()
            session.headers.update(method['headers'])

            response = session.get(method['url'], stream=True, allow_redirects=True)

            # Check if we got actual model data
            content_type = response.headers.get('content-type', '')
            content_length = int(response.headers.get('content-length', 0))

            print(f"  Status: {response.status_code}")
            print(f"  Content-Type: {content_type}")
            print(f"  Content-Length: {content_length}")

            if response.status_code == 200:
                # Check if it's actual model data (should be large)
                if content_length > 1000000:  # > 1MB
                    print(f"  ✅ Downloading to {output_path}")

                    with open(output_path, 'wb') as f:
                        downloaded = 0
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                progress = (downloaded / content_length) * 100
                                print(f"\r  Progress: {progress:.1f}%", end='', flush=True)

                    print(f"\n  ✅ Successfully downloaded: {output_filename}")
                    return True
                else:
                    # Probably got an error page or redirect
                    print(f"  ❌ Response too small, likely an error")
                    if content_length < 10000:  # Check error message if small
                        print(f"  Response: {response.text[:200]}")
            else:
                print(f"  ❌ Failed with status {response.status_code}")
                if response.status_code == 401:
                    try:
                        error = response.json()
                        print(f"  Error: {error.get('message', error)}")
                    except:
                        print(f"  Response: {response.text[:200]}")

        except Exception as e:
            print(f"  ❌ Error: {e}")

    print(f"\n❌ All methods failed for model {model_version_id}")
    return False

def main():
    print("🔞 Civitai NSFW Model Downloader")
    print("=" * 60)
    print(f"API Token: {API_TOKEN}")
    print(f"Output Directory: {OUTPUT_DIR}")

    models = [
        {
            "name": "LTX Orgasm LoRA",
            "version_id": "2597222",
            "filename": "ltx_orgasm.safetensors"
        },
        {
            "name": "WAN-DR34ML4Y All-in-One NSFW",
            "version_id": "2553271",
            "filename": "wan_dr34ml4y_nsfw.safetensors"
        }
    ]

    success_count = 0

    for model in models:
        print(f"\n{'='*60}")
        print(f"Model: {model['name']}")
        print(f"Version ID: {model['version_id']}")

        if download_model(model['version_id'], model['filename']):
            success_count += 1

    print(f"\n{'='*60}")
    print(f"✅ Downloaded {success_count}/{len(models)} models")

    if success_count < len(models):
        print("\n⚠️  Some models require browser session authentication")
        print("These models have creator restrictions that require actual login")
        print("\nTo download these models:")
        print("1. Login to https://civitai.com in your browser")
        print("2. Navigate to the model page")
        print("3. Click the download button")
        print(f"4. Save to {OUTPUT_DIR}")

if __name__ == "__main__":
    main()