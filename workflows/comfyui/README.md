# ComfyUI Workflows for 30-Second Anime Generation

This directory contains the critical workflow files for generating 30-second anime videos using ComfyUI with RIFE interpolation.

## Files

### Core Workflows
- **`anime_30sec_working_workflow.json`** - Tested and verified working workflow for 30-second anime generation
- **`anime_30sec_rife_workflow.json`** - RIFE interpolation workflow for frame interpolation
- **`anime_30sec_fixed_workflow.json`** - Fixed version with optimized settings

### Generation Script
- **`generate_30sec_anime.py`** - Python script to trigger the 30-second anime generation workflow

## Usage

1. Load the workflow JSON file into ComfyUI interface at http://192.168.50.135:8188
2. Alternatively, use the Python script to automate generation:
   ```bash
   python3 generate_30sec_anime.py
   ```

## Technical Details

### FramePack Video Generation (Primary - as of 2026-02-14)
- **Wrapper**: `ComfyUI-FramePackWrapper_Plus` only (old wrapper disabled)
- **gpu_memory_preservation**: **6.0** required for RTX 3060 at 544x704+ (3.5 causes GPU OOM)
- **Resolution**: 544x704 or nearest bucket (FramePackFindNearestBucket selects optimal)
- **Output**: 30fps h264 MP4
- **Generation Time**: ~20min for 2s, ~13min for 3s, ~25-30min for 5s at 544x704

### Legacy AnimateDiff Workflows
- **Frame Count**: 120 frames for 30 seconds at 4fps
- **Resolution**: 1024x1024
- **Interpolation**: RIFE algorithm for smooth frame transitions
- **Context Window**: Looped uniform context for temporal consistency

### ComfyUI Service Configuration
- **systemd MemoryMax**: 64G (raised from 16G on 2026-02-14)
- **systemd MemoryHigh**: 48G (raised from 12G)
- **CPUQuota**: 200%
- FramePack offload mode uses ~30-40GB CPU RAM for model tensors

## Requirements

- ComfyUI running on Tower (192.168.50.135:8188)
- NVIDIA RTX 3060 with 12GB VRAM
- ComfyUI-FramePackWrapper_Plus for video generation
- Required models loaded in ComfyUI

## Output

Generated videos are saved to `/opt/ComfyUI/output/` (FramePack: `framepack_*.mp4`).