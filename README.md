# Tower Anime Production

Anime video production system with Echo Brain AI integration and FramePack segment chaining for movie-length content.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Set up database
psql -U patrick -d anime_production < database/anime_schema.sql
psql -U patrick -d anime_production < database/framepack_schema.sql

# Run API server
python api/main.py
```

API: `http://localhost:8328/api/anime/docs`

## Architecture

```
tower-anime-production/
├── api/
│   ├── main.py                 # FastAPI entry point
│   ├── echo_brain/             # Echo Brain AI integration
│   │   ├── assist.py           # AI assistance endpoints
│   │   ├── routes.py           # Echo Brain routes
│   │   └── workflow_orchestrator.py
│   ├── auth_middleware.py
│   └── websocket_*.py          # Real-time updates
├── services/
│   ├── framepack/              # FramePack video generation
│   │   ├── echo_brain_memory.py    # Character/story/visual persistence
│   │   ├── scene_generator.py      # Segment generation & chaining
│   │   └── quality_analyzer.py     # SSIM & optical flow analysis
│   └── generation/             # Image/video generation
├── config/
│   └── settings.py             # Environment-based config
├── database/
│   ├── anime_schema.sql
│   ├── framepack_schema.sql
│   └── migrations/
├── frontend/                   # Vue.js UI
│   └── src/components/
│       └── EchoBrainChat.vue   # AI chat interface
├── workflows/                  # ComfyUI templates
└── docs/
    └── archive/                # Historical docs
```

## Features

### Echo Brain Integration
- AI-powered creative assistance
- Workflow orchestration
- Chat interface for generation control

### FramePack Pipeline
Chain 30-60 second segments into movie-length content:

```
Movie → Episodes → Scenes → Segments
                              ↓
                    Echo Brain Memory
                    - Character state per scene
                    - Story context per scene
                    - Visual style per scene
                    - Quality feedback (learning)
                              ↓
                    FramePack Generation
                    - First/last frame anchoring
                    - Anti-drift technology
                    - 6GB VRAM requirement
                              ↓
                    Quality Analysis
                    - Frame consistency (SSIM)
                    - Motion smoothness (optical flow)
```

### Learning Loop
After each segment:
1. Quality analyzer scores frame consistency + motion smoothness
2. Score > 0.7 → prompt elements marked "successful"
3. Score < 0.4 → prompt elements marked "failed"
4. Next generation uses feedback to enhance prompts

## Configuration

```bash
# Database
DB_HOST=localhost
DB_NAME=anime_production
DB_USER=patrick
DB_PASSWORD=<from-env>

# ComfyUI
COMFYUI_HOST=localhost
COMFYUI_PORT=8188

# API
API_PORT=8328
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/anime/health` | GET | System health |
| `/api/anime/generate` | POST | Generate image |
| `/api/anime/orchestrate` | POST | Full pipeline |
| `/api/anime/generation/{id}/status` | GET | Job status |
| `/api/echo-brain/assist` | POST | AI assistance |
| `/api/echo-brain/chat` | WebSocket | Real-time chat |

## Hardware

Optimized for Tower server:
- **GPU**: RTX 3060 12GB (FramePack ~6GB)
- **CPU**: AMD Ryzen 9 24-core
- **RAM**: 96GB DDR6
- **Storage**: 1TB NVMe

## Development

```bash
# Tests
pytest tests/ -v

# Lint
black api/ services/ config/
isort api/ services/ config/

# Type check
mypy api/ services/ config/
```

## FramePack v2 Video Generation

### Quick Start

```bash
# System check
cd /opt/tower-anime-production/workflows/framepack
python3 tower_framepack_v2.py --check

# Generate with project scene
python3 tower_framepack_v2.py --project tdd --scene mei_office --seconds 5

# Generate with custom prompt
python3 tower_framepack_v2.py --prompt "anime girl walking in Tokyo rain" --seconds 3

# Use F1 model (newer/better)
python3 tower_framepack_v2.py --prompt "forest scene" --f1 --seconds 5

# Image-to-video mode
python3 tower_framepack_v2.py --image /path/to/image.png --prompt "gentle movement" --seconds 5
```

### Available Project Scenes

| Project | Scene | Description |
|---------|-------|-------------|
| `tdd` | `mei_office` | Mei in Tokyo office with city view |
| `tdd` | `kai_rooftop` | Kai on rooftop at night |
| `tdd` | `tokyo_night_walk` | Rain-slicked Shinjuku streets |
| `cgs` | `neon_alley` | Cyberpunk hooded figure |
| `smg` | `galaxy_flight` | Cosmic flight scene |

### Models Available

- **FramePackI2V** (original): `FramePackI2V_HY_fp8_e4m3fn.safetensors`
- **FramePack F1** (recommended): `FramePack_F1_I2V_HY_20250503_fp8_e4m3fn.safetensors`

### Key Features

- **HunyuanVideo Architecture**: Uses dual text encoders (LLAMA 4096d + CLIP-L 768d)
- **FP8 Quantization**: Optimized for RTX 3060 12GB VRAM
- **Both T2V and I2V**: Text-to-video and image-to-video modes
- **Verified Output**: Validates generated content quality
- **Automatic Assembly**: Handles VHS MP4 output or ffmpeg fallback

### Installation

```bash
# Install ComfyUI node (already done)
cd /opt/ComfyUI/custom_nodes
git clone https://github.com/kijai/ComfyUI-FramePackWrapper.git

# Models installed at /mnt/1TB-storage/models/:
# ✅ diffusion_models/FramePackI2V_HY_fp8_e4m3fn.safetensors (15GB)
# ✅ diffusion_models/FramePack_F1_I2V_HY_20250503_fp8_e4m3fn.safetensors (15GB)
# ✅ text_encoders/clip_l.safetensors (235MB)
# ✅ text_encoders/llava_llama3_fp16.safetensors (15GB)
# ✅ clip_vision/sigclip_vision_patch14_384.safetensors (817MB)
# ✅ vae/hunyuan_video_vae_bf16.safetensors (471MB)
```

### Technical Details

- **GPU Memory**: 6GB preservation setting for RTX 3060
- **Frame Rate**: 30fps output
- **Resolution**: 544x704 default (anime portrait)
- **Sampling**: 20-30 steps recommended
- **CFG**: 1.0 (FramePack optimized value)
