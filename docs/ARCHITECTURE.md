# Tower Anime Production System - Architecture Documentation

## Overview

The Tower Anime Production System is a GPU-accelerated anime generation platform that integrates with ComfyUI and Echo Brain for AI orchestration. The system follows a modular architecture with clear separation of concerns.

## Directory Structure

```
tower-anime-production/
├── api/                          # FastAPI backend (current production)
│   └── main.py                   # Main API server
├── anime-system-modular/         # Modular architecture (target)
│   ├── main.py                   # Slim app initialization
│   └── backend/
│       ├── routers/anime.py      # All API endpoints
│       ├── models/schemas.py     # Pydantic models
│       └── services/             # Business logic services
│           ├── character_consistency.py
│           └── quality_metrics.py
├── frontend/                     # Vue.js 3 frontend
│   └── src/
│       ├── config/api.js         # Centralized API configuration
│       ├── types/anime.ts        # TypeScript type definitions
│       ├── stores/               # Pinia state management
│       └── components/           # Vue components
├── database/                     # SQL schema definitions
├── workflows/                    # ComfyUI workflow templates
└── docs/                         # Documentation
```

## Core Components

### Backend API (Port 8328)

The backend provides RESTful API endpoints for:
- **Generation**: Image and video generation via ComfyUI
- **Projects**: Project management with Story Bibles
- **Characters**: Character consistency with face embeddings
- **Quality**: Quality metrics and phase gating
- **Jobs**: Job tracking and progress monitoring
- **Echo Brain**: AI orchestration integration

### Frontend (Vue.js 3)

- **State Management**: Pinia stores for reactive state
- **API Configuration**: Centralized SSOT at `src/config/api.js`
- **Type Safety**: Full TypeScript definitions at `src/types/anime.ts`
- **Real-time Updates**: WebSocket integration for job progress

### External Services

- **ComfyUI (Port 8188)**: GPU-accelerated image/video generation
- **Echo Brain (Port 8309)**: AI orchestration and task coordination
- **PostgreSQL**: Database for projects, characters, and jobs

## API Endpoints

### Generation
- `POST /api/anime/generate` - Submit generation job
- `POST /api/anime/generate-fast` - Fast generation mode
- `POST /api/anime/jobs/{id}/reproduce` - Reproduce previous generation

### Projects
- `GET /api/anime/projects` - List projects
- `POST /api/anime/projects` - Create project
- `GET /api/anime/projects/{id}/story-bible` - Get story bible
- `POST /api/anime/projects/{id}/generate` - Generate for project

### Characters
- `PUT /api/anime/characters/{id}/embedding` - Store face embedding
- `POST /api/anime/characters/{id}/consistency-check` - Check consistency
- `GET /api/anime/characters/{id}/attributes` - Get character attributes
- `POST /api/anime/characters/{id}/variations` - Create variation

### Quality
- `POST /api/anime/quality/evaluate` - Evaluate quality metrics
- `POST /api/anime/quality/phase-gate/{phase}` - Check phase gate

### Jobs
- `GET /api/anime/jobs` - List all jobs
- `GET /api/anime/jobs/{id}/status` - Get job status
- `GET /api/anime/jobs/{id}/progress` - Get detailed progress
- `GET /api/anime/jobs/{id}/quality` - Get quality scores

## Data Models

### Character Consistency

Characters include:
- **Face Embedding**: 512-dimension ArcFace embedding
- **Attributes**: Visual tokens (hair color, eye color, outfit)
- **Variations**: Outfit, expression, pose variants
- **Color Palette**: Primary and accent colors
- **Base Prompt**: Character description for prompts

### Quality Metrics

Quality scoring includes:
- **Face Similarity**: Cosine similarity to reference (threshold: 0.70)
- **Aesthetic Score**: LAION aesthetic score (threshold: 5.5)
- **Temporal LPIPS**: Frame-to-frame consistency (video only)
- **Motion Smoothness**: Animation smoothness (video only)
- **Subject Consistency**: Subject tracking (video only)

### Phase Gates

Development phases:
1. **Phase 1 (Still)**: Single frame generation
2. **Phase 2 (Loop)**: Animation loop generation
3. **Phase 3 (Video)**: Full video generation

Each phase requires 80%+ pass rate before advancement.

## Development

### Running the Backend

```bash
cd /home/user/tower-anime-production
python -m uvicorn api.main:app --host 0.0.0.0 --port 8328
```

### Running the Frontend

```bash
cd frontend
npm install
npm run dev
```

### Building for Production

```bash
cd frontend
npm run build  # Outputs to ../static/dist
```

## Configuration

### API Hosts

Update `frontend/src/config/api.js` for your environment:

```javascript
const API_HOSTS = {
  anime: 'http://192.168.50.135:8328',
  websocket: 'ws://192.168.50.135:8328/ws',
  echo: 'http://192.168.50.135:8309',
  comfyui: 'http://192.168.50.135:8188'
}
```

### Database

Configure in `api/main.py`:

```python
DATABASE_URL = "postgresql://patrick:***@localhost/anime_production"
```

## WebSocket Events

Real-time updates via WebSocket:

- `progress` - Job progress update
- `job_complete` - Job completed successfully
- `job_failed` - Job failed with error
- `quality_evaluation` - Quality scores available

## Project Style Enforcement

Projects enforce style consistency:
- **Tokyo Debt Desire**: Photorealistic (`realisticVision_v51`)
- **Cyberpunk Goblin Slayer**: Stylized anime (`counterfeit_v3`)

Style rules are stored in the database and validated at runtime.

## Episode Production (Long-form Video)

### Architecture

Episodes are structured as:
```
Episode
├── Scene 1
│   ├── Segment 1 (30s video)
│   ├── Segment 2 (30s video)
│   └── ... (stitched with cut/crossfade)
├── Scene 2
│   └── ...
└── Final Output (stitched with transitions)
```

### API Endpoints

```bash
# Create full episode with scenes
POST /api/anime/episodes
{
  "project_id": "tokyo-debt-desire",
  "title": "Episode 1: The Beginning",
  "scenes": [
    {
      "name": "Opening",
      "description": "City at night",
      "prompts": ["neon city skyline, rain, noir atmosphere"],
      "segment_duration": 30
    }
  ]
}

# Quick episode from prompts
POST /api/anime/episodes/quick
{
  "prompts": [
    "anime girl walking through rain, city lights",
    "close up of character looking at phone",
    "wide shot of empty street"
  ],
  "segment_duration": 30
}

# Check episode status
GET /api/anime/episodes/{id}/status
```

### Video Generation Pipeline

1. **AnimateDiff**: Generates 5s of base frames (120 frames @ 24fps)
2. **RIFE Interpolation**: 6x frame interpolation → 30s video
3. **FFmpeg Stitching**: Combines segments with transitions
4. **Quality Check**: Temporal coherence, motion quality

### Configuration

```python
EpisodeConfig(
    segment_duration=30,     # seconds per segment
    fps=24,                  # output frame rate
    width=1024,              # video width
    height=576,              # video height
    use_interpolation=True,  # RIFE 6x interpolation
    parallel_segments=2      # concurrent generations
)
```

### Required ComfyUI Models

For video generation, ensure these are installed:
- `v3_sd15_mm.ckpt` (AnimateDiff motion module)
- `rife4.6.pkl` (RIFE VFI model)
- `clip_l.safetensors` (CLIP text encoder)
- `vae-ft-mse-840000-ema-pruned.safetensors` (VAE)
