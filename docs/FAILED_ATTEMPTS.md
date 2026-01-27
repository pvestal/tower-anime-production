# Failed Attempts - Tower Anime Production

This document records attempts that DO NOT WORK and should not be tried again.
All failures are documented with specific error messages and reasons.

## ❌ FAILED APPROACHES

### LTX Video 19B Model
**Status**: ❌ FAILED
**Error**: `Error while deserializing header: incomplete metadata, file not fully covered`
**File**: `/mnt/1TB-storage/models/checkpoints/ltx-2-19b-distilled.safetensors`
**Reason**: Corrupted safetensors file (24GB file appears incomplete)
**Fix Attempted**: None (file corruption at source)
**Do Not Retry**: File needs to be re-downloaded from source

### LTX Video 2B with Gemma Text Encoder
**Status**: ❌ FAILED
**Node**: `LTXVGemmaCLIPModelLoader`
**Error**:
```
size mismatch for mm_input_projection_weight:
copying param with shape torch.Size([1152, 3840]) from checkpoint,
shape in current model is torch.Size([768, 2304])
```
**Reason**: Incompatible tensor shapes between Gemma encoder and LTX model
**Do Not Retry**: Architecture incompatibility, not fixable

### LTX Video 2B via UNETLoader
**Status**: ❌ FAILED
**Error**: `unet_name: 'ltx-2/ltxv-2b-0.9.8-distilled.safetensors' not in allowed list`
**Reason**: UNETLoader only accepts FramePack models, not LTX models
**Do Not Retry**: Wrong loader type for LTX models

### FramePack I2V Model
**Status**: ❌ FAILED
**Node**: UNETLoader with `FramePackI2V_HY_fp8_e4m3fn.safetensors`
**Error**: `Could not detect model type of: FramePackI2V_HY_fp8_e4m3fn.safetensors`
**Reason**: Model type detection failure in ComfyUI
**Do Not Retry**: Model format incompatibility

### AnimateDiff Extended Frame Generation
**Status**: ❌ FAILED (ARCHITECTURAL LIMIT)
**Attempts**: 32, 64, 121 frame generation
**Result**: All attempts resulted in exactly 16 frames
**Reason**: Hard-coded architectural constraint in AnimateDiff models
**Models Tested**:
- `mm_sd_v15_v2.ckpt`
- `v3_sd15_mm.ckpt`
**VRAM Available**: 10.7GB (not a VRAM issue)
**Do Not Retry**: Fundamental architecture limitation

### LTX Video 2B without Text Encoder
**Status**: ❌ FAILED
**Error**: `clip input is invalid: None`
**Reason**: LTX 2B model does not include embedded text encoder
**Solution Found**: Use separate CLIPLoader with T5XXL encoder
**Do Not Use**: CheckpointLoaderSimple alone for LTX models

## ❌ FAILED WORKFLOW PATTERNS

### Direct LTX Model Loading
```python
# DO NOT USE
{
    "class_type": "CheckpointLoaderSimple",
    "inputs": {"ckpt_name": "ltx-2/ltxv-2b-0.9.8-distilled.safetensors"}
}
# → Results in "clip input is invalid: None"
```

### UNETLoader for LTX Models
```python
# DO NOT USE
{
    "class_type": "UNETLoader",
    "inputs": {"unet_name": "ltx-2/ltxv-2b-0.9.8-distilled.safetensors"}
}
# → Model not in allowed list
```

### Gemma Text Encoder with LTX 2B
```python
# DO NOT USE
{
    "class_type": "LTXVGemmaCLIPModelLoader",
    "inputs": {
        "gemma_path": "gemma_3_12B_it.safetensors",
        "ltxv_path": "ltx-2/ltxv-2b-0.9.8-distilled.safetensors"
    }
}
# → Tensor size mismatch errors
```

## ❌ FAILED NODE COMBINATIONS

### EmptyLatentVideo (Non-existent)
**Node**: `EmptyLatentVideo`
**Error**: `Cannot execute because node EmptyLatentVideo does not exist`
**Correct Node**: `EmptyLTXVLatentVideo` for LTX models

### Standard VAE with LTX Models
**Issue**: Using standard VAE decode with LTX latents
**Result**: Incorrect output format
**Solution**: Use LTX-specific VAE from checkpoint

## 📊 FAILURE ANALYSIS

| Approach | Failure Type | Root Cause | Retry Worth? |
|----------|--------------|------------|--------------|
| LTX 19B | File corruption | Download issue | Maybe* |
| Gemma + LTX 2B | Architecture mismatch | Incompatible tensors | No |
| UNETLoader LTX | Wrong loader | Loader restrictions | No |
| FramePack I2V | Model detection | Format issue | No |
| AnimateDiff >16 | Hard limit | Architecture | No |

*Only if file can be re-downloaded from reliable source

## 🔄 LESSONS LEARNED

1. **Always check model compatibility** before assuming loaders work
2. **File corruption is common** with large model downloads
3. **Architecture limits are hard constraints**, not configuration issues
4. **Text encoders must match model requirements** exactly
5. **Node names matter** - similar names may be completely different

## 🚨 RED FLAGS TO AVOID

- Any approach claiming >16 frames with AnimateDiff
- Using Gemma text encoder with LTX 2B models
- Expecting UNETLoader to work with LTX models
- Assuming corrupted files will "eventually work"
- Bypassing validation steps in pursuit of speed

## ✅ WHAT ACTUALLY WORKS

See `WORKING_SOLUTIONS.md` for proven approaches.

**Key Working Pattern**:
```
CheckpointLoaderSimple (LTX model) +
CLIPLoader (T5XXL, type=ltxv) +
LTX-specific nodes = SUCCESS
```

---

**Last Updated**: 2026-01-26
**Purpose**: Prevent wasted time on known failed approaches