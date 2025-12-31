# SSOT Workflow Documentation

## Overview
This directory contains Single Source of Truth (SSOT) workflows that have been **verified to work** for the Tokyo Debt Desire project.

## Workflows

### 1. workflow_tokyo_debt_base.json
**Purpose**: Generate photorealistic base images of Mei

**Verified Settings**:
- Checkpoint: `realisticVision_v51.safetensors` (NOT anime style)
- LoRA: `mei_working_v1.safetensors` @ strength 1.0
- Resolution: 512x768
- Sampler: dpmpp_2m, 25 steps, CFG 7.0
- Scheduler: karras

**Parameter Injection Points**:
- `{{seed}}` - Random seed for variation
- `{{pose_modifier}}` - Additional pose description
- `{{output_prefix}}` - Output filename prefix

### 2. workflow_svd_video.json
**Purpose**: Generate smooth video from base image

**Verified Settings**:
- Model: `svd_xt.safetensors` (NOT AnimateDiff)
- Frames: 25 @ 8fps
- Motion bucket: 127
- Sampler: euler, 20 steps, CFG 2.5
- Output: H.264 MP4

**Parameter Injection Points**:
- `{{source_image}}` - Input image filename
- `{{seed}}` - Random seed
- `{{output_prefix}}` - Output filename prefix

## Usage

### Quick Start
```bash
python execute_ssot_workflow.py
```

### Programmatic Usage
```python
from execute_ssot_workflow import SSOTWorkflowExecutor

executor = SSOTWorkflowExecutor()

# Generate base image
base_image = executor.execute_base_generation(
    seed=12345,
    pose_modifier="facing camera, professional",
    output_prefix="mei_base"
)

# Generate video from base
video = executor.execute_svd_video(
    source_image=base_image,
    seed=42,
    output_prefix="mei_video"
)
```

## Important Notes

### DO USE:
- `realisticVision_v51.safetensors` for photorealistic output
- `svd_xt.safetensors` for video generation
- The exact settings documented above

### DO NOT USE:
- `AOM3A1B.safetensors` (anime style - wrong for Tokyo Debt)
- AnimateDiff nodes (produces morphing/artifacts)
- Experimental settings that haven't been verified

## Verification

These workflows produce:
1. **Photorealistic** Mei (not anime style)
2. **Consistent** facial features (74%+ similarity to reference)
3. **Smooth** video without morphing artifacts
4. **Correct** anatomical proportions (C-cup as specified)

## File Structure
```
ssot/
├── workflow_tokyo_debt_base.json   # Base image generation
├── workflow_svd_video.json         # SVD video generation
├── execute_ssot_workflow.py        # Execution script
└── README.md                        # This file
```

## Next Steps

For Phase 3 (Frontend Integration):
1. Connect to ComfyUI WebSocket at `ws://localhost:8188/ws`
2. Submit workflows via `/prompt` endpoint
3. Monitor progress via WebSocket messages
4. Display results in frontend at `/opt/tower-anime-production/frontend/`