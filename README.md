# Anime Studio v3.6

End-to-end anime production pipeline: project management, character design, dataset approval, LoRA training, image/video generation, scene assembly, episode composition, production orchestration, and Jellyfin publishing.

**Stack**: FastAPI (Python) + Vue 3 (TypeScript) + PostgreSQL + Apache AGE + ComfyUI + Qdrant + Ollama
**Port**: 8401 (systemd: `tower-anime-studio.service`)
**URL**: `http://192.168.50.135/anime-studio/`
**API**: 127+ endpoints across 8 packages + core + graph + orchestrator
**Entry**: `server/app.py` (modular router mounts)

---

## User Guide — How This System Works

### The Concepts (Movie Studio Analogy)

| Movie Studio            | This System                  | What It Does                              |
|-------------------------|------------------------------|-------------------------------------------|
| Film stock / camera     | **Checkpoint** model         | Determines the visual look of everything  |
| Casting photos          | **LoRA** files               | Teaches the system what each actor looks like |
| The script              | **Prompts**                  | Describes what happens in each shot       |
| The director            | **Sampler + CFG + Steps**    | Controls pacing, mood, interpretation     |
| Film format (35mm/IMAX) | **Architecture** (SD1.5/SDXL)| Resolution and quality ceiling            |
| The editing room        | **Scenes + Shots**           | Assembles everything into sequences       |
| Reference footage       | **Uploaded videos**          | Shows the system "make it look like this" |

**The key rule**: Your film stock and casting photos must be the same format.
SD1.5 LoRAs only work with SD1.5 checkpoints. SDXL LoRAs only work with SDXL
checkpoints. They cannot cross architectures.

### Architecture Quick Reference

| Architecture | Resolution | VRAM (generate) | VRAM (train) | Speed | LoRA size |
|-------------|-----------|-----------------|--------------|-------|-----------|
| **SD 1.5**  | 512x768   | ~3-4 GB         | ~6-8 GB      | ~22s/image | ~12 MB |
| **SDXL**    | 832x1216  | ~6-8 GB         | ~10-12 GB    | ~55s/image | ~186 MB |

**Current standard: Illustrious SDXL** (WAI-Illustrious-SDXL v16). All projects
migrated from SD1.5 to Illustrious as of 2026-03-04. SDXL produces higher quality
(better anatomy, more detail) but is 3x slower and LoRA training is tight on 12GB.
Old SD1.5 LoRAs are incompatible and must be retrained against Illustrious.

### How to Do Common Tasks

#### Generate images of a character
1. **Story** tab → select project
2. **Cast** tab → click character → **Generate**
3. The system auto-selects the project checkpoint + character LoRA

#### Upload a reference video and extract frames
```bash
# Upload from your machine
curl -X POST http://192.168.50.135:8401/api/training/ingest/video \
  -F "file=@/path/to/video.mp4" -F "character_slug=mei_kobayashi"

# Ingest from a file already on the server
curl -X POST http://192.168.50.135:8401/api/training/ingest/local-video \
  -H "Content-Type: application/json" \
  -d '{"video_path": "/path/on/server/video.mp4", "character_slug": "mei_kobayashi"}'

# Ingest from YouTube
curl -X POST http://192.168.50.135:8401/api/training/ingest/youtube \
  -H "Content-Type: application/json" \
  -d '{"url": "https://youtube.com/watch?v=XXXXX", "character_slug": "mario"}'
```

#### Upload a movie and split frames across characters
```bash
# Upload a movie file
curl -X POST http://192.168.50.135:8401/api/training/ingest/movie-upload \
  -F "file=@/path/to/movie.mp4"

# Extract + classify frames from a movie already on disk
curl -X POST http://192.168.50.135:8401/api/training/ingest/movie-extract \
  -H "Content-Type: application/json" \
  -d '{"movie_path": "/opt/anime-studio/datasets/_movies/movie.mp4", "project_name": "Project Name"}'
```

#### Approve images for training
Images must be approved before LoRA training. Minimum 100 approved.

**UI**: Cast tab → character → review images → approve/reject

**Bulk approve from terminal:**
```bash
python3 -c "
import os, requests
slug = 'mei_kobayashi'  # change this
imgs = [f for f in os.listdir(f'/opt/anime-studio/datasets/{slug}/images') if f.endswith(('.png','.jpg'))]
r = requests.post('http://localhost:8401/api/training/approval/bulk-status',
    json={'images': [{'character_slug': slug, 'image_name': i} for i in imgs], 'status': 'approved'})
print(f'Approved {r.json().get(\"updated_count\",0)} images')
"
```

#### Train a character LoRA
**UI**: Cast tab → character → Train

**Terminal:**
```bash
curl -X POST http://192.168.50.135:8401/api/training/start \
  -H "Content-Type: application/json" \
  -d '{"character_name": "Mei Kobayashi"}'

# Monitor
tail -f /opt/anime-studio/logs/train_mei_kobayashi_*.log
```

Training auto-detects the project checkpoint. ~10-15 min (SD1.5), ~30-45 min (SDXL).
One job at a time (single GPU).

#### Generate video from a reference clip (reference_v2v)
```bash
# Extract clips from a reference video
curl -X POST http://192.168.50.135:8401/api/training/ingest/clips/extract \
  -H "Content-Type: application/json" \
  -d '{"video_path": "/opt/anime-studio/datasets/_movies/fury/roxy_fox_bed_01.mp4",
       "character_slug": "roxy", "clip_duration": 5}'

# Assign clip to a shot (auto-selects reference_v2v engine)
curl -X POST http://192.168.50.135:8401/api/scenes/{scene_id}/shots/{shot_id}/assign-source-video \
  -H "Content-Type: application/json" \
  -d '{"clip_path": "/path/to/clip.mp4"}'

# Generate
curl -X POST http://192.168.50.135:8401/api/scenes/{scene_id}/generate
```

#### Check system status
```bash
# All trained LoRAs
curl -s http://192.168.50.135:8401/api/training/loras | python3 -m json.tool

# All checkpoints
curl -s http://192.168.50.135:8401/api/story/checkpoints | python3 -m json.tool

# Gap analysis (what characters need training)
curl -s http://192.168.50.135:8401/api/training/gap-analysis | python3 -m json.tool

# Training jobs
curl -s http://192.168.50.135:8401/api/training/jobs | python3 -m json.tool
```

#### Add a new checkpoint from CivitAI
1. Download .safetensors from CivitAI
2. Copy to `/opt/ComfyUI/models/checkpoints/` — it appears automatically
3. Add a generation style:
```sql
PGPASSWORD=RP78eIrW7cI2jYvL5akt1yurE psql -h localhost -U patrick -d anime_production -c "
INSERT INTO generation_styles (style_name, checkpoint_model, model_architecture, width, height, cfg_scale, sampler, scheduler, steps)
VALUES ('my_style', 'filename.safetensors', 'sd15', 512, 768, 7.0, 'dpmpp_2m', 'karras', 30);"
```
4. Assign to project: `UPDATE projects SET default_style = 'my_style' WHERE name = 'Project';`
5. **WARNING**: Changing checkpoint means retraining ALL character LoRAs for that project.

#### Add a LoRA from CivitAI
1. Download .safetensors from CivitAI
2. Copy to `/opt/ComfyUI/models/loras/`
3. Check the CivitAI page for: **base model** (must match your architecture) and **trigger word**
4. Style LoRAs: add trigger word to your prompt
5. Character LoRAs: assign to a character via DB `lora_path` column

### CivitAI Shopping Guide

On civitai.com/models, the **Base Model** filter is the most important:
- **"SD 1.5"** → compatible with: cyberrealistic_v9, Counterfeit-V3.0, realcartoonPixar, realistic_vision, dreamshaper, basil_mix, lazymix
- **"Pony"** → compatible with: ponyDiffusionV6XL, nova_animal_xl_v11
- **"Illustrious"** → compatible with: NoobAI-XL-Vpred
- **"SDXL 1.0"** → compatible with: cyberrealisticXL_v8

**LoRA ecosystems are incompatible across families.** A Pony LoRA won't work on
Illustrious/NoobAI and vice versa.

**What to look for**: Downloads > 50K (community tested), multiple diverse example
images (not cherry-picked), trigger word documented, file size matches arch
(~2GB checkpoint = SD1.5, ~6.5GB = SDXL, ~12MB LoRA = SD1.5, ~186MB LoRA = SDXL).

**Red flags**: No examples, "LoRA" over 2GB (mislabeled checkpoint), no trigger
word, all examples identical, comments saying "doesn't work".

### Current Projects

| Project | Style | Checkpoint | Arch | Characters |
|---------|-------|-----------|------|------------|
| Cyberpunk Goblin Slayer | illustrious_anime | waiIllustriousSDXL_v160 | SDXL | 15 characters |
| Tokyo Debt Desire | illustrious_realistic | waiIllustriousSDXL_v160 | SDXL | Mei, Rina, Yuki, Takeshi, Beth |
| Mario Galaxy | illustrious_stylized | waiIllustriousSDXL_v160 | SDXL | Mario, Luigi, Peach + others |
| Echo Chamber | illustrious_anime | waiIllustriousSDXL_v160 | SDXL | 5 characters |
| Rosa Caliente | illustrious_realistic | waiIllustriousSDXL_v160 | SDXL | Rosa |
| Small Wonders | illustrious_nature | waiIllustriousSDXL_v160 | SDXL | 4 characters |
| Fury | nova_animal_xl | nova_animal_xl_v11 | SDXL | Roxy, Lilith, Zara, Buck + others |

**Note**: All projects migrated to Illustrious SDXL (2026-03-04). Fury stays on nova_animal_xl (anthro-specific).
All SD1.5 LoRAs are incompatible with Illustrious and need retraining.

### File Locations

| Thing | Path |
|-------|------|
| Checkpoints | `/opt/ComfyUI/models/checkpoints/` |
| LoRAs | `/opt/ComfyUI/models/loras/` |
| Character datasets | `/opt/anime-studio/datasets/{slug}/images/` |
| Uploaded movies | `/opt/anime-studio/datasets/_movies/` |
| Generated videos | `/opt/ComfyUI/output/` |
| Training logs | `/opt/anime-studio/logs/` |
| Approval status | `/opt/anime-studio/datasets/{slug}/approval_status.json` |

---

## Tabs (Developer Reference)

| # | Tab | Purpose |
|---|-----|---------|
| 1 | **Project** | Create/select projects, configure checkpoint models, generation styles |
| 2 | **Story & World** | Storyline, world settings, art direction, cinematography, Echo Brain narration assist |
| 3 | **Characters** | Character roster, design prompts, YouTube/video/image ingestion |
| 4 | **Approve** | Human-in-the-loop image approval with Gemma3 auto-triage, species validation, replenishment loop controls |
| 5 | **Train** | Launch LoRA training jobs, monitor epochs/loss |
| 6 | **Generate** | Generate images (Stable Diffusion) or videos (FramePack/LTX/Wan I2V/T2V) per character |
| 7 | **Scenes** | Scene Builder + Episodes: compose multi-shot scenes with per-shot engine selection, motion presets, dialogue, continuity chaining; assemble with crossfade transitions; frame interpolation; upscaling; audio ducking; episode assembly; Jellyfin publish |
| 8 | **Gallery** | Browse generated outputs |
| — | **Echo Brain** | AI chat with project context, prompt enhancement |

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for system diagrams and data flow.

## Key Paths

| Path | Purpose |
|------|---------|
| `server/app.py` | FastAPI entry point — mounts all package routers |
| `packages/core/` | DB pool, auth middleware, config, GPU status, models, events, learning, replenishment, orchestrator, graph |
| `packages/story/` | Story & world settings, project CRUD (15 routes) |
| `packages/visual_pipeline/` | Vision review, classification, ComfyUI workflows (5 routes) |
| `packages/scene_generation/` | Scene builder, FramePack/LTX-Video/Wan T2V, progressive-gate generation, crossfade assembly, audio ducking, frame interpolation, upscaling, music gen, motion presets, story-to-scenes AI (23 routes) |
| `packages/episode_assembly/` | Episode CRUD, multi-scene assembly, Jellyfin publishing (10 routes) |
| `packages/lora_training/` | Training, ingestion, regeneration, feedback (32 routes) |
| `packages/audio_composition/` | Voice ingestion/transcription, ACE-Step music generation, music cache (8 routes) |
| `packages/echo_integration/` | Echo Brain chat, prompt enhancement (4 routes) |
| `src/components/` | Vue 3 tab components with sub-component directories |
| `src/api/` | TypeScript API client split by domain (base, story, training, visual, scenes, episodes, echo) |
| `src/generate_training_images.py` | Standalone generation script (per-character negatives, IP-Adapter) |
| `datasets/{slug}/images/` | Character training images |
| `datasets/{slug}/reference_images/` | IP-Adapter reference images per character |
| `datasets/{slug}/approval_status.json` | Per-character approval state |
| `output/scenes/` | Assembled scene videos |
| `output/episodes/` | Assembled episode videos |

## Database

PostgreSQL `anime_production` database. Key tables:

- `projects` - Project definitions with default generation style
- `generation_styles` - Checkpoint, CFG, steps, sampler, resolution
- `characters` - Character names, design prompts, appearance_data (species, key_colors, key_features, common_errors)
- `storylines` - Story metadata per project
- `world_settings` - Art direction, cinematography, color palettes, negative_prompt_guidance
- `scenes` - Scene metadata, generation status, output paths, dialogue audio, post-processing settings (interpolation fps, upscale factor)
- `shots` - Individual shots within scenes, per-shot video engine selection (FramePack/LTX/Wan), generation state, dialogue text/character, transition settings
- `episodes` - Episode metadata, assembly status, Jellyfin publish path
- `episode_scenes` - Junction table linking scenes to episodes with position ordering

## SSOT Principle

All generation parameters are project-level (Single Source of Truth):
- Projects reference a `generation_style` (checkpoint, CFG, steps, sampler, resolution)
- Characters only store `design_prompt` and `appearance_data` - no per-character generation overrides
- The design prompt IS the main prompt; style templates add quality tags only
- Per-character negative prompts are built dynamically from `appearance_data.species` and `appearance_data.common_errors`

## Character Quality Pipeline

### Per-Character Negatives
Non-human characters (species containing "NOT human") automatically get negative prompt terms:
`human, human face, human skin, realistic person, humanoid body, human proportions`
Plus species-specific terms from `common_errors` (e.g., Luigi gets `letter M on cap, child, teenager`).

### IP-Adapter Reference Images
Each character's `datasets/{slug}/reference_images/` directory is checked during generation.
If references exist + IP-Adapter models are installed, reference conditioning is injected into the ComfyUI workflow (weight 0.7, end_at 0.85).

### Vision Review (Gemma3)
- Scores character_match, clarity, training_value (0-10), solo detection, completeness
- Feature checklist built from `appearance_data` (species, key_colors, key_features, common_errors)
- Species verification step for non-human characters (focused binary check)
- **Non-human characters never auto-approve** — always require manual review
- Auto-reject threshold: quality_score < 0.4
- Human characters auto-approve at quality_score >= 0.8 + solo

## Scene Builder

The Scene Builder (tab 7) enables multi-shot video scene composition:

1. **Define** scenes with metadata (location, time, weather, mood)
2. **Add shots** with source images, motion prompts (with preset library), shot types, camera angles, per-shot dialogue, transition settings, and **video engine selection** (FramePack, FramePack F1, LTX-Video, Wan T2V)
2b. **Auto engine selection**: Orchestrator automatically picks the best engine per shot — establishing shots → `wan` T2V, characters with LoRA on disk → `ltx` (native LoRA injection), has source image → `framepack`, no source image → `wan` fallback. Engine blacklist respected. Manual override via `POST /scenes/{id}/shots/{id}/select-engine`
3. **Generate** shots via progressive quality gates — each shot is generated, quality-checked by vision AI, and retried up to 3x with loosening thresholds (0.6→0.45→0.3) and more steps per retry
4. **Chain** continuity: each shot's last frame becomes the next shot's first frame
5. **Assemble** completed shots with crossfade transitions (ffmpeg xfade filter, 0.3s dissolve overlap)
5b. **Post-process** (optional): frame interpolation (30→60fps via minterpolate), video upscaling (2x via lanczos, capped at 1080p)
6. **Music**: auto-generates AI music from scene mood via ACE-Step (3.5B model, AMD GPU), or uses assigned Apple Music tracks
7. **Audio mixing**: dialogue WAVs (100%) + music with **sidechain ducking** (30% volume auto-dips to ~5% during dialogue) mixed into final scene video

Generation runs as a background async task with one-at-a-time ComfyUI queueing (no queue flooding). The monitor view polls status every 5 seconds.

### Motion Presets
6 shot types with curated motion prompts: `establishing`, `wide`, `medium`, `close-up`, `extreme_close-up`, `action`. Presets appear as clickable chips in the shot editor; selecting one populates the motion prompt textarea.

### Story-to-Scenes AI
`POST /scenes/generate-from-story` sends the project storyline + world settings + character list to Ollama (gemma3:12b) and returns structured scene breakdowns with suggested shots, locations, moods, and motion prompts. The frontend shows a "Generate Scenes from Story" button when no scenes exist.

### Keyframe Blitz (Two-Pass Generation)
Fast keyframe preview (~18s/shot) before committing to slow video (~5min/shot):
1. `POST /scenes/{id}/keyframe-blitz?skip_existing=true` — generates txt2img keyframes for all shots
2. Shot spec enrichment via Ollama gemma3:12b (pose/camera/emotion-aware prompts, ~3s/shot)
3. Sets `source_image_path` on each shot for subsequent I2V video generation
4. Frontend: "Keyframe All" button in StoryboardGrid topbar
5. CLI: `scripts/generate_all_keyframes.py [start_scene_num]` — sequential with crash recovery

### Shot Spec Enrichment
Before keyframe/video generation, each shot is enriched via Ollama gemma3:12b (`packages/scene_generation/shot_spec.py`):
- **Pose selection**: From shot-type-specific vocabulary, avoiding recently used poses
- **Camera/lighting**: Emotion-based suggestions (tension→dutch-angle, intimacy→warm soft lighting, etc.)
- **Anti-sameness**: `must_differ_from` UUIDs + negative prompt terms from recent poses
- **Enhanced prompts**: Adds pose, body language, and emotion-specific visual cues to generation prompt

## Episodes & Publishing

Episodes group scenes into ordered sequences for final video assembly:

1. **Create** episodes with number, title, description, story arc
2. **Add scenes** to episodes in position order (drag-and-drop reordering)
3. **Assemble** episode via ffmpeg concat of all scene videos
4. **Publish** to Jellyfin with proper naming convention:
   ```
   /mnt/1TB-storage/media/anime/{Project Name}/Season 01/S01E01 - {Title}.mp4
   ```
5. **Auto-scan** triggers Jellyfin library refresh via API

### Episode Endpoints
- `GET/POST /episodes` — list/create episodes per project
- `GET/PATCH/DELETE /episodes/{id}` — CRUD
- `POST/DELETE /episodes/{id}/scenes/{scene_id}` — add/remove scenes
- `PUT /episodes/{id}/reorder` — reorder scene positions
- `POST /episodes/{id}/assemble` — ffmpeg concat + thumbnail
- `GET /episodes/{id}/video` — serve assembled MP4
- `POST /episodes/{id}/publish` — Jellyfin publish with library scan

## Production Orchestrator

End-to-end pipeline coordinator (`packages/core/orchestrator.py` + `orchestrator_router.py`) that autonomously advances projects through all production stages. **Off by default** — enable via `POST /api/system/orchestrator/toggle`.

### Pipeline Phases

**Per character** (sequential):
```
training_data → lora_training → ready
```

**Per project** (blocks until all characters ready):
```
scene_planning → shot_preparation → video_generation → scene_assembly → episode_assembly → publishing
```

### Gate Checks
Each phase has a gate that must pass before advancing:
- `training_data`: character has ≥ N approved images (default 30)
- `lora_training`: LoRA `.safetensors` file exists on disk
- `scene_planning`: scenes exist in DB
- `shot_preparation`: all shots have `source_image_path` assigned + auto engine selection (wan/ltx/framepack based on shot type, LoRA availability, blacklist)
- `video_generation`: all shots have completed video
- `scene_assembly`: all scenes have `final_video_path`
- `episode_assembly`: all episodes assembled
- `publishing`: all episodes published to Jellyfin

### Orchestrator Endpoints
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/system/orchestrator/status` | Global on/off + config |
| POST | `/api/system/orchestrator/toggle` | Enable/disable |
| POST | `/api/system/orchestrator/initialize` | Bootstrap pipeline for a project |
| GET | `/api/system/orchestrator/pipeline/{project_id}` | Full structured status |
| GET | `/api/system/orchestrator/summary/{project_id}` | Human-readable summary |
| POST | `/api/system/orchestrator/tick` | Trigger manual evaluation pass |
| POST | `/api/system/orchestrator/override` | Force phase status (skip/reset/complete) |
| POST | `/api/system/orchestrator/training-target` | Set approved image threshold |

### Safety
- Off by default (must explicitly toggle on)
- Respects ComfyUI semaphore (generation serialization)
- FramePack: one scene at a time (GPU memory constraint)
- All autonomous actions logged to `autonomy_decisions` table
- Resets to disabled on service restart

### Database
`production_pipeline` table tracks phase state per entity (character or project):
- `entity_type`, `entity_id`, `project_id`, `phase`, `status`
- `progress_current`/`progress_target` for training_data tracking
- `gate_check_result` (JSONB) stores last gate evaluation
- `blocked_reason` for debugging

## Autonomy System

### EventBus
In-process async event emitter (`packages/core/events.py`) for cross-package coordination. Events: `image.approved`, `image.rejected`, `generation.submitted`, `generation.completed`, `feedback.recorded`, `regeneration.queued`, `pipeline.phase_advanced`.

### Learning System
SQL-based pattern analysis from generation history, rejections, and approvals. Learns success/failure patterns per character, suggests optimal params, detects quality drift.

### Replenishment Loop
Autonomous image generation to reach target approved counts per character (`packages/core/replenishment.py`). Off by default — enable via Approve tab toggle or `POST /api/lora/replenishment/toggle`.

**Flow**: `IMAGE_APPROVED → check count vs target → generate batch → copy to datasets → register pending → vision review → auto-approve/reject → learn → repeat if still below target → STOP at target`

**Safety mechanisms**:
| Guard | Default | Purpose |
|-------|---------|---------|
| Enable flag | OFF | Must explicitly enable |
| Cooldown | 60s/char | Prevents burst from simultaneous approvals |
| Daily limit | 10/char | Caps daily GPU usage |
| Consecutive rejects | 5 max | Stops if model can't generate well |
| Pending buffer | 3 max | Won't generate if review backlog exists |
| Max concurrent | 2 | Limits parallel GPU load |
| Batch size | 3/round | Small batches for faster feedback |

**Endpoints**:
- `GET /api/lora/replenishment/status` — loop status, active tasks, daily counts
- `POST /api/lora/replenishment/toggle?enabled=true` — enable/disable
- `POST /api/lora/replenishment/target?target=20&character_slug=luigi` — set target count
- `GET /api/lora/replenishment/readiness?project_name=...` — per-character progress

### Auto-Correction
7 fix strategies for rejected images (`packages/core/auto_correction.py`). Off by default. Strategies: fix_quality, fix_resolution, fix_blur, fix_brightness, fix_contrast, fix_appearance, fix_solo.

### Quality Gates
Configurable DB-stored thresholds for auto-approve (0.8), auto-reject (0.4), and scene shot minimum (0.4). Managed via `GET/PUT /api/lora/quality/gates`.

## Generation Pipeline

### Image Generation
Character design prompt + style template + per-character negatives -> ComfyUI checkpoint workflow (+ IP-Adapter if refs exist) -> output image -> vision review -> approval queue

### FramePack Video (I2V)
Source image + motion prompt -> FramePack model -> sampling (sections) -> VAE decode tiled -> MP4

### Wan 2.1 T2V (Text-to-Video)
Text prompt -> Wan 2.1 1.3B (GGUF Q8_0, UMT5-XXL text encoder) -> uni_pc sampling -> VAE decode -> MP4
Ideal for environment/establishing shots where no source image exists. ~4-6GB VRAM with GGUF.

### Scene Generation (Progressive Gates)
```
For each shot (ordered):
  1. First frame = previous shot's last frame (or source image for shot 1)
  2. Copy to ComfyUI/input/
  3. Build workflow per shot engine (FramePack/LTX/Wan — one at a time, no queue flooding)
  4. Submit to ComfyUI, poll until complete
  5. Extract last frame, quality-check via Ollama vision (score 0-1)
  6. If score < threshold: RETRY with new seed + more steps (up to 3 attempts)
     Gate 1: threshold=0.6, Gate 2: 0.45, Gate 3: 0.3
  7. Accept best result, chain last frame to next shot
After all shots:
  8. ffmpeg xfade crossfade between shots (dissolve/fade/wipe, 0.3s overlap)
  8b. Optional: frame interpolation (30→60fps via minterpolate)
  8c. Optional: video upscaling (2x via lanczos, max 1080p)
  9. Build dialogue audio (TTS per shot, concat)
  10. Get music: ACE-Step generated > Apple Music preview > auto-generate from mood
  11. Mix: video + dialogue (100%) + music (30%) -> final scene video
```

### Episode Assembly
```
For each episode:
  1. Gather scene videos in position order
  2. ffmpeg xfade crossfade between scenes (fadeblack default, 0.5s) -> episode video
  3. Extract thumbnail from first frame
  4. Optional: publish to Jellyfin (symlink + library scan)
```

## Development

```bash
# Frontend
cd /opt/anime-studio
npm install
npm run dev    # Dev server with HMR
npm run build  # Production build to dist/

# Backend
source venv/bin/activate
python -m uvicorn src.app:app --host 0.0.0.0 --port 8401  # Dev run

# Service
sudo systemctl restart tower-anime-studio
sudo systemctl status tower-anime-studio
journalctl -u tower-anime-studio -f
```

## Dependencies

### Python
FastAPI, asyncpg, uvicorn, hvac (Vault), Pillow, yt-dlp

### Node
Vue 3, TypeScript, Vite, Pinia, vue-router, Tailwind CSS

### External Services
- **ComfyUI** (port 8188) - Image/video generation engine (NVIDIA RTX 3060, 12GB)
- **ACE-Step** (port 8440) - AI music generation, 3.5B model (AMD RX 9070 XT, 16GB, ROCm 7.2)
- **Qdrant** (port 6333) - Vector database for Echo Brain
- **Echo Brain** (port 8309) - Memory/context API (AMD RX 9070 XT)
- **Ollama** (port 11434) - Gemma3 vision model for auto-triage and quality gates
- **PostgreSQL** - Database backend
- **Vault** - Database credential management
- **Jellyfin** (port 8096) - Media server for published episodes
