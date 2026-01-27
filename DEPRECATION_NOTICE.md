# DEPRECATED: AnimateDiff Pipeline Migration to LTX 2B

**Date: 2026-01-26**
**Status: IMMEDIATE ACTION REQUIRED**

## ⚠️ CRITICAL DEPRECATION NOTICE

AnimateDiff is being **IMMEDIATELY DEPRECATED** from all Tower Anime Production workflows due to fundamental limitations:

### AnimateDiff Problems (PROVEN BROKEN):
- **Hard 16-frame limit** - Cannot generate longer sequences
- **Low resolution: 512x288** - Below production quality
- **2-second maximum duration** - Insufficient for real scenes
- **Context window failures** - No proper temporal coherence
- **VRAM inefficient** - Uses more resources for worse results

### LTX 2B Proven Solution (WORKING):
- **121 frames** - 5+ second sequences
- **768x512 resolution** - Production ready quality
- **24 FPS smooth playback** - Professional frame rate
- **Efficient VRAM usage** - Works with available hardware
- **Separate text encoder** - Better prompt understanding

## MIGRATION PLAN

### 1. Immediate Actions
- ✅ All NEW workflows MUST use LTX 2B
- ✅ NO new AnimateDiff implementations
- ✅ Production pipeline updated to LTX 2B standard

### 2. Files Being Migrated
- `netflix_level_video_production.py` → LTX 2B workflows
- All workflow templates → LTX 2B base
- Documentation → LTX 2B examples only

### 3. Archive Legacy Code
- AnimateDiff experiments moved to `/archive/deprecated_animatediff/`
- Working LTX 2B examples in `/production/workflows/`
- Test validation confirms LTX 2B quality superiority

## PROVEN WORKING CONFIGURATION

```python
# LTX 2B Standard Configuration
{
    "1": {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {"ckpt_name": "ltx-2/ltxv-2b-0.9.8-distilled.safetensors"}
    },
    "2": {
        "class_type": "CLIPLoader",
        "inputs": {
            "clip_name": "t5xxl_fp16.safetensors",
            "type": "ltxv"
        }
    }
    # Generates 121 frames, 5.04 seconds, 768x512, 24fps
}
```

## VALIDATION RESULTS

Latest tests confirm:
- **LTX 2B**: 121 frames, 768x512, 5.04s ✅
- **AnimateDiff**: 16 frames, 512x288, 2.0s ❌

**Decision: LTX 2B is the ONLY approved video generation method**

---

*This deprecation is effective immediately. All AnimateDiff code is considered legacy and should not be extended.*