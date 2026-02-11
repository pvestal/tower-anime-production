# FramePack Old Workflows Archive

## Archive Date: 2026-02-11

These files were archived when deploying FramePack v2 (`tower_framepack_v2.py`), which is the verified working solution.

## Archived Files

### Non-Working/Superseded Scripts

| File | Reason | Replaced By |
|------|--------|-------------|
| `tower_framepack_generate.py` | Earlier version with issues | `workflows/framepack/tower_framepack_v2.py` |
| `framepack_diagnostic.py` | Diagnostic tool no longer needed | Built-in system check in v2 |
| `framepack_preflight.sh` | Setup script superseded | Direct model installation |
| `framepack_simple_test.py` | Basic test superseded | Full workflow in v2 |
| `complete_framepack_setup.sh` | Setup script superseded | Direct model installation |
| `setup_framepack_corrected.sh` | Setup script superseded | Direct model installation |
| `test_framepack_api.py` | Basic API test superseded | Full workflow in v2 |
| `validate_framepack_output.py` | Validation script superseded | Built-in validation in v2 |

## What Works Now

✅ **Current Working Solution**: `/opt/tower-anime-production/workflows/framepack/tower_framepack_v2.py`

Features:
- Verified system check (`--check`)
- Project scenes (`--project tdd --scene mei_office`)
- Custom prompts (`--prompt "text"`)
- Both models (original + F1)
- Built-in output validation
- Proper error handling
- RTX 3060 optimized

## Testing

The v2 script was verified working on 2026-02-11:
- System check: ✅ All nodes available
- Models: ✅ Both FramePackI2V and F1 loaded
- Generation: ✅ TDD Mei office scene successfully processing

## Historical Context

These archived files represent various attempts to get FramePack working correctly. The main issues were:
1. Incorrect text encoder setup (SD CLIP vs HunyuanVideo dual encoders)
2. Missing model files or wrong paths
3. ComfyUI node wiring problems
4. Memory management on RTX 3060

All these issues are resolved in v2.