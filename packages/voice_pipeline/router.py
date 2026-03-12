"""Voice pipeline — diarization, training, synthesis.

Voice sample management routes (assignment, approval, streaming, stats)
are in voice_samples.py (included as sub-router).
"""

import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import FileResponse

from packages.core.auth import get_user_projects

from packages.core.config import BASE_PATH
from packages.core.db import connect_direct, get_char_project_map
from packages.core.models import (
    VoiceDiarizeRequest, VoiceTrainRequest, VoiceSynthesizeRequest,
    VoiceSceneDialogueRequest,
)
from packages.voice_pipeline.diarization import diarize_project
from packages.voice_pipeline.cloning import (
    start_sovits_training, start_rvc_training, get_training_jobs,
    get_training_job, get_training_log, cancel_training_job,
)
from packages.voice_pipeline.synthesis import (
    synthesize_dialogue, get_voice_models,
    synthesize_scene_dialogue, generate_dialogue_from_story,
    synthesize_episode_dialogue,
)

from .voice_samples import router as samples_router

logger = logging.getLogger(__name__)


async def _voice_content_gate(request: Request, allowed_projects: list[int] = Depends(get_user_projects)):
    """Block voice operations on scenes/shots/episodes the user can't access."""
    scene_id = request.path_params.get("scene_id")
    shot_id = request.path_params.get("shot_id")
    episode_id = request.path_params.get("episode_id")
    if not (scene_id or shot_id or episode_id):
        return
    conn = await connect_direct()
    try:
        project_id = None
        if scene_id:
            import uuid
            project_id = await conn.fetchval(
                "SELECT project_id FROM scenes WHERE id = $1", uuid.UUID(scene_id))
        elif shot_id:
            import uuid
            project_id = await conn.fetchval("""
                SELECT sc.project_id FROM shots sh
                JOIN scenes sc ON sh.scene_id = sc.id
                WHERE sh.id = $1""", uuid.UUID(shot_id))
        elif episode_id:
            import uuid
            project_id = await conn.fetchval(
                "SELECT project_id FROM episodes WHERE id = $1", uuid.UUID(episode_id))
    finally:
        await conn.close()
    if project_id is not None and project_id not in allowed_projects:
        raise HTTPException(status_code=403, detail="Access denied to this project")


router = APIRouter(dependencies=[Depends(_voice_content_gate)])
router.include_router(samples_router)

VOICE_BASE = BASE_PATH.parent
VOICE_DATASETS = VOICE_BASE / "voice_datasets"


# =============================================================================
# Phase A: Diarization
# =============================================================================

@router.post("/ingest-file")
async def ingest_voice_file(
    file: UploadFile = File(...),
    character_slug: str = Form(""),
    label: str = Form(""),
):
    """Upload a movie/audio file, extract audio, split into voice samples.

    Accepts .mp4, .mkv, .avi, .mov, .wav, .mp3, .flac, .ogg files.
    Extracts audio to 16kHz mono WAV, then splits into segments by silence.
    If character_slug is provided, segments go directly into that character's
    samples dir for F5-TTS reference. Otherwise stored for later diarization.
    """
    import subprocess
    import tempfile
    import shutil

    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    ext = Path(file.filename).suffix.lower()
    allowed = {".mp4", ".mkv", ".avi", ".mov", ".wav", ".mp3", ".flac", ".ogg", ".m4a", ".webm"}
    if ext not in allowed:
        raise HTTPException(status_code=400, detail=f"Unsupported format {ext}. Allowed: {', '.join(sorted(allowed))}")

    # Save uploaded file to temp
    tmpdir = tempfile.mkdtemp(prefix="voice_ingest_")
    try:
        tmp_input = Path(tmpdir) / f"input{ext}"
        with open(tmp_input, "wb") as f:
            content = await file.read()
            f.write(content)

        # Determine output dir
        if character_slug:
            safe_slug = character_slug.lower().replace(" ", "_")[:50]
            out_dir = VOICE_DATASETS / safe_slug / "samples"
        else:
            safe_label = (label or file.filename or "uploaded").lower().replace(" ", "_")[:50]
            safe_label = "".join(c for c in safe_label if c.isalnum() or c in "_-.")
            out_dir = VOICE_BASE / "voice" / safe_label
        out_dir.mkdir(parents=True, exist_ok=True)

        # Extract audio to WAV (16kHz mono for TTS)
        full_audio = out_dir / "full_audio.wav"
        ffmpeg_result = subprocess.run(
            ["ffmpeg", "-i", str(tmp_input), "-vn", "-acodec", "pcm_s16le",
             "-ar", "16000", "-ac", "1", str(full_audio), "-y"],
            capture_output=True, text=True, timeout=300,
        )
        if ffmpeg_result.returncode != 0:
            raise HTTPException(status_code=500, detail=f"ffmpeg failed: {ffmpeg_result.stderr[:500]}")

        # Get total duration
        probe = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(full_audio)],
            capture_output=True, text=True, timeout=30,
        )
        total_duration = float(probe.stdout.strip()) if probe.stdout.strip() else 0

        # Split into segments using silence detection
        segments = []
        if character_slug:
            # For direct character assignment, split by silence into 5-15s clips
            seg_dir = out_dir
            seg_result = subprocess.run(
                ["ffmpeg", "-i", str(full_audio),
                 "-af", "silencedetect=noise=-30dB:d=0.5",
                 "-f", "null", "-"],
                capture_output=True, text=True, timeout=120,
            )
            # Parse silence timestamps
            import re
            silence_starts = []
            for line in seg_result.stderr.split("\n"):
                m = re.search(r"silence_start: ([\d.]+)", line)
                if m:
                    silence_starts.append(float(m.group(1)))

            # Create segments at silence boundaries (aim for 5-15s clips)
            splits = [0.0] + silence_starts + [total_duration]
            seg_num = 1
            i = 0
            while i < len(splits) - 1:
                start = splits[i]
                # Accumulate until we have at least 3s
                end = splits[min(i + 1, len(splits) - 1)]
                while (end - start) < 3.0 and i + 2 < len(splits):
                    i += 1
                    end = splits[min(i + 1, len(splits) - 1)]
                if end - start < 1.0:
                    i += 1
                    continue

                # Cap at 15s
                if end - start > 15.0:
                    end = start + 15.0

                seg_path = seg_dir / f"segment_{seg_num:03d}.wav"
                subprocess.run(
                    ["ffmpeg", "-i", str(full_audio), "-ss", str(start),
                     "-t", str(end - start), "-y", str(seg_path)],
                    capture_output=True, timeout=30,
                )
                if seg_path.exists():
                    segments.append({
                        "filename": seg_path.name,
                        "start": round(start, 2),
                        "end": round(end, 2),
                        "duration": round(end - start, 2),
                    })
                    seg_num += 1
                i += 1
        else:
            segments.append({
                "filename": "full_audio.wav",
                "duration": round(total_duration, 2),
            })

        return {
            "status": "ok",
            "output_dir": str(out_dir),
            "total_duration_seconds": round(total_duration, 2),
            "segments": segments,
            "total_segments": len(segments),
            "character_slug": character_slug or None,
            "next_step": "diarize" if not character_slug else "review samples at Cast > Voice > Review",
        }
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


@router.post("/ingest-path")
async def ingest_voice_from_path(
    file_path: str = Form(...),
    character_slug: str = Form(""),
):
    """Ingest a local file by path (for movie files already on disk).

    Same as ingest-file but reads from a local path instead of upload.
    """
    import subprocess
    source = Path(file_path)
    if not source.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

    ext = source.suffix.lower()
    allowed = {".mp4", ".mkv", ".avi", ".mov", ".wav", ".mp3", ".flac", ".ogg", ".m4a", ".webm"}
    if ext not in allowed:
        raise HTTPException(status_code=400, detail=f"Unsupported format {ext}")

    if character_slug:
        safe_slug = character_slug.lower().replace(" ", "_")[:50]
        out_dir = VOICE_DATASETS / safe_slug / "samples"
    else:
        out_dir = VOICE_BASE / "voice" / source.stem.lower()[:50]
    out_dir.mkdir(parents=True, exist_ok=True)

    full_audio = out_dir / "full_audio.wav"
    result = subprocess.run(
        ["ffmpeg", "-i", str(source), "-vn", "-acodec", "pcm_s16le",
         "-ar", "16000", "-ac", "1", str(full_audio), "-y"],
        capture_output=True, text=True, timeout=600,
    )
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=f"ffmpeg failed: {result.stderr[:500]}")

    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(full_audio)],
        capture_output=True, text=True, timeout=30,
    )
    total_duration = float(probe.stdout.strip()) if probe.stdout.strip() else 0

    return {
        "status": "ok",
        "output_dir": str(out_dir),
        "full_audio": str(full_audio),
        "total_duration_seconds": round(total_duration, 2),
        "character_slug": character_slug or None,
        "next_step": "diarize" if not character_slug else "review samples",
    }


@router.post("/diarize")
async def run_diarization(body: VoiceDiarizeRequest):
    """Run pyannote speaker diarization on project audio."""
    result = await diarize_project(body.project_name)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/speakers/{project_name}")
async def list_speakers(project_name: str):
    """List speaker clusters for a project with segment counts."""
    conn = await connect_direct()
    try:
        rows = await conn.fetch(
            "SELECT * FROM voice_speakers WHERE project_name = $1 ORDER BY speaker_label",
            project_name,
        )

        speakers = [dict(r) for r in rows]

        # Also check diarization_meta.json if DB is empty
        if not speakers:
            safe_project = project_name.lower().replace(" ", "_")[:50]
            meta_path = VOICE_BASE / "voice" / safe_project / "diarization_meta.json"
            if meta_path.exists():
                with open(meta_path) as f:
                    meta = json.load(f)

                # Seed DB from diarization metadata
                for spk in meta.get("speakers", []):
                    await conn.execute("""
                        INSERT INTO voice_speakers (speaker_label, project_name, segment_count,
                            total_duration_seconds, created_at)
                        VALUES ($1, $2, $3, $4, NOW())
                        ON CONFLICT DO NOTHING
                    """, spk["speaker_label"], project_name,
                        spk["segment_count"], spk["total_duration_seconds"])

                speakers = [dict(r) for r in await conn.fetch(
                    "SELECT * FROM voice_speakers WHERE project_name = $1 ORDER BY speaker_label",
                    project_name,
                )]

        return {"project_name": project_name, "speakers": speakers, "total": len(speakers)}
    finally:
        await conn.close()


# =============================================================================
# Phase C: Voice Clone Training
# =============================================================================

@router.post("/train/sovits")
async def train_sovits(body: VoiceTrainRequest):
    """Start GPT-SoVITS voice training for a character."""
    result = await start_sovits_training(
        character_slug=body.character_slug,
        character_name=body.character_name or "",
        project_name=body.project_name or "",
        epochs=body.epochs or 8,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/train/rvc")
async def train_rvc(body: VoiceTrainRequest):
    """Start RVC v2 voice training for a character."""
    result = await start_rvc_training(
        character_slug=body.character_slug,
        character_name=body.character_name or "",
        project_name=body.project_name or "",
        epochs=body.epochs or 40,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/train/jobs")
async def list_training_jobs(project_name: str = None, character_slug: str = None):
    """List all voice training jobs, optionally filtered."""
    jobs = await get_training_jobs(project_name=project_name, character_slug=character_slug)
    return {"jobs": jobs, "total": len(jobs)}


@router.get("/train/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Get status of a specific training job."""
    job = await get_training_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Training job not found")
    return job


@router.get("/train/jobs/{job_id}/log")
async def get_job_log(job_id: str, lines: int = 50):
    """Tail the log file of a training job."""
    log_text = get_training_log(job_id, lines=lines)
    return {"job_id": job_id, "log": log_text}


@router.post("/train/jobs/{job_id}/cancel")
async def cancel_job(job_id: str):
    """Cancel a running training job."""
    result = await cancel_training_job(job_id)
    return result


# =============================================================================
# Phase D: Voice Synthesis
# =============================================================================

@router.post("/synthesize")
async def synthesize(body: VoiceSynthesizeRequest):
    """Generate speech from text using character's voice model."""
    result = await synthesize_dialogue(
        character_slug=body.character_slug,
        text=body.text,
        engine=body.engine,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    # Record in DB
    conn = await connect_direct()
    try:
        import uuid
        job_id = f"synth_{uuid.uuid4().hex[:8]}"
        await conn.execute("""
            INSERT INTO voice_synthesis_jobs
                (job_id, character_slug, engine, text, output_path,
                 duration_seconds, status, created_at, completed_at)
            VALUES ($1, $2, $3, $4, $5, $6, 'completed', NOW(), NOW())
        """, job_id, body.character_slug, result.get("engine_used", ""),
            body.text, result.get("output_path", ""),
            result.get("duration_seconds", 0))
        result["job_id"] = job_id
    finally:
        await conn.close()

    return result


@router.get("/synthesis/{job_id}")
async def get_synthesis_result(job_id: str):
    """Get synthesis job result."""
    conn = await connect_direct()
    try:
        row = await conn.fetchrow(
            "SELECT * FROM voice_synthesis_jobs WHERE job_id = $1", job_id
        )
        if not row:
            raise HTTPException(status_code=404, detail="Synthesis job not found")
        return dict(row)
    finally:
        await conn.close()


@router.get("/synthesis/{job_id}/audio")
async def stream_synthesis_audio(job_id: str):
    """Stream synthesized audio WAV file."""
    conn = await connect_direct()
    try:
        output_path = await conn.fetchval(
            "SELECT output_path FROM voice_synthesis_jobs WHERE job_id = $1", job_id
        )
    finally:
        await conn.close()

    if not output_path or not Path(output_path).exists():
        raise HTTPException(status_code=404, detail="Audio file not found")

    return FileResponse(output_path, media_type="audio/wav")


@router.post("/scene/{scene_id}/dialogue")
async def generate_scene_dialogue(scene_id: str, body: VoiceSceneDialogueRequest):
    """Generate and synthesize dialogue for a scene.

    If dialogue_list is provided, synthesize those lines directly.
    If description + characters are provided, use LLM to generate dialogue first.
    """
    dialogue_list = body.dialogue_list

    if not dialogue_list and body.description and body.characters:
        dialogue_list = await generate_dialogue_from_story(
            scene_id=scene_id,
            description=body.description,
            characters=body.characters,
        )
        if not dialogue_list:
            raise HTTPException(status_code=400, detail="Failed to generate dialogue from description")

    if not dialogue_list:
        raise HTTPException(status_code=400, detail="Provide dialogue_list or description + characters")

    result = await synthesize_scene_dialogue(
        scene_id=scene_id,
        dialogue_list=dialogue_list,
        pause_seconds=body.pause_seconds or 0.5,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/shot/{shot_id}/synthesize")
async def synthesize_shot_dialogue(shot_id: str, engine: str = None):
    """Synthesize dialogue for a specific shot using the character's voice.

    Reads dialogue_text and dialogue_character_slug from the shot record,
    synthesizes audio, and returns the audio URL for playback.
    """
    conn = await connect_direct()
    try:
        row = await conn.fetchrow(
            "SELECT dialogue_text, dialogue_character_slug FROM shots WHERE id = $1::uuid",
            shot_id,
        )
    finally:
        await conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Shot not found")
    if not row["dialogue_text"] or not row["dialogue_character_slug"]:
        raise HTTPException(status_code=400, detail="Shot has no dialogue text or character assigned")

    result = await synthesize_dialogue(
        character_slug=row["dialogue_character_slug"],
        text=row["dialogue_text"],
        engine=engine,
    )
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    # Record in DB
    import uuid as _uuid
    job_id = f"synth_{_uuid.uuid4().hex[:8]}"
    conn = await connect_direct()
    try:
        await conn.execute("""
            INSERT INTO voice_synthesis_jobs
                (job_id, character_slug, engine, text, output_path,
                 duration_seconds, status, created_at, completed_at)
            VALUES ($1, $2, $3, $4, $5, $6, 'completed', NOW(), NOW())
        """, job_id, row["dialogue_character_slug"], result.get("engine_used", ""),
            row["dialogue_text"], result.get("output_path", ""),
            result.get("duration_seconds", 0))
    finally:
        await conn.close()

    result["job_id"] = job_id
    return result


@router.post("/episode/{episode_id}/synthesize-all")
async def synthesize_all_episode_dialogue(episode_id: str):
    """Synthesize dialogue for all scenes in an episode.

    Processes each scene in episode order. Skips scenes that already have
    valid dialogue audio. Returns per-scene results.
    """
    result = await synthesize_episode_dialogue(episode_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/project/{project_id}/synthesize-all")
async def synthesize_all_project_dialogue(project_id: int, force: bool = False):
    """Bulk-synthesize voice for ALL shots with dialogue in a project.

    Processes every shot that has dialogue_text + dialogue_character_slug but
    no voice_audio_path (unless force=True to re-do all). Stores the result
    path in shots.voice_audio_path.

    This reads the actual dialogue from the database — no generic SFX.
    """
    conn = await connect_direct()
    try:
        where = (
            "s.dialogue_text IS NOT NULL AND s.dialogue_character_slug IS NOT NULL"
        )
        if not force:
            where += " AND (s.voice_audio_path IS NULL OR s.voice_audio_path = '')"

        rows = await conn.fetch(f"""
            SELECT s.id, s.dialogue_text, s.dialogue_character_slug, s.voice_audio_path
            FROM shots s
            JOIN scenes sc ON s.scene_id = sc.id
            WHERE sc.project_id = $1 AND {where}
            ORDER BY sc.scene_number, s.shot_number
        """, project_id)
    finally:
        await conn.close()

    if not rows:
        return {"project_id": project_id, "processed": 0, "skipped": 0,
                "message": "No shots need voice synthesis"}

    results = []
    processed = 0
    failed = 0

    for row in rows:
        shot_id = row["id"]
        text = row["dialogue_text"]
        char_slug = row["dialogue_character_slug"]

        try:
            result = await synthesize_dialogue(
                character_slug=char_slug,
                text=text,
            )
            if result.get("output_path"):
                conn = await connect_direct()
                try:
                    await conn.execute(
                        "UPDATE shots SET voice_audio_path = $2 WHERE id = $1",
                        shot_id, result["output_path"],
                    )
                finally:
                    await conn.close()
                results.append({
                    "shot_id": str(shot_id),
                    "character": char_slug,
                    "engine": result.get("engine_used"),
                    "status": "synthesized",
                })
                processed += 1
            else:
                results.append({
                    "shot_id": str(shot_id), "character": char_slug,
                    "status": "no_output",
                })
                failed += 1
        except Exception as e:
            results.append({
                "shot_id": str(shot_id), "character": char_slug,
                "status": "error", "error": str(e),
            })
            failed += 1
            logger.warning(f"Voice synthesis failed for shot {shot_id} ({char_slug}): {e}")

    return {
        "project_id": project_id,
        "processed": processed,
        "failed": failed,
        "total": len(rows),
        "results": results,
    }


@router.get("/models/{character_slug}")
async def available_voice_models(character_slug: str):
    """Get available voice models and engines for a character."""
    return await get_voice_models(character_slug)


# =============================================================================
# SFX Library — Explicit vocal sound effects
# =============================================================================

@router.get("/sfx/catalog")
async def sfx_catalog():
    """List all generated SFX samples from the manifest."""
    manifest_path = BASE_PATH.parent / "output" / "sfx_test" / "sfx_manifest.json"
    if not manifest_path.exists():
        return {"samples": [], "categories": {}, "total": 0}
    with open(manifest_path) as f:
        data = json.load(f)
    return data


@router.get("/sfx/library")
async def sfx_library():
    """List categorized real audio segments + downloaded foley SFX."""
    manifest_path = BASE_PATH.parent / "output" / "sfx_library" / "segments_manifest.json"
    by_cat = {}
    total = 0
    if manifest_path.exists():
        with open(manifest_path) as f:
            data = json.load(f)
        for seg in data.get("segments", []):
            cat = seg.get("category", "uncategorized")
            if cat not in by_cat:
                by_cat[cat] = []
            by_cat[cat].append(seg)
            total += 1

    # Add downloaded foley SFX
    foley_dir = BASE_PATH.parent / "output" / "sfx_library" / "foley"
    if foley_dir.exists():
        for tag_dir in sorted(foley_dir.iterdir()):
            if not tag_dir.is_dir():
                continue
            tag = tag_dir.name
            cat_key = f"foley_{tag}"
            if cat_key not in by_cat:
                by_cat[cat_key] = []
            for f in sorted(tag_dir.glob("*.wav")):
                by_cat[cat_key].append({
                    "filename": f.name,
                    "category": cat_key,
                    "subcategory": tag,
                    "source": "foley_download",
                    "duration": None,
                    "path": f"foley/{tag}/{f.name}",
                })
                total += 1

    return {"categories": by_cat, "total": total,
            "sources": ["spicy_audio_recordings", "foley_downloads"]}


@router.get("/sfx/audio/{category}/{filename}")
async def stream_sfx_audio(category: str, filename: str):
    """Stream an SFX audio file by category/filename."""
    safe_cat = Path(category).name
    safe_file = Path(filename).name
    # Check edge-tts generated samples first
    audio_path = BASE_PATH.parent / "output" / "sfx_test" / safe_cat / safe_file
    if not audio_path.exists():
        # Check categorized real segments
        audio_path = BASE_PATH.parent / "output" / "sfx_library" / "categorized" / safe_cat / safe_file
    if not audio_path.exists():
        # Check raw segments
        audio_path = BASE_PATH.parent / "output" / "sfx_library" / "segments" / safe_file
    if not audio_path.exists():
        # Check foley downloads (category key is foley_tagname, dir is foley/tagname)
        foley_tag = safe_cat.removeprefix("foley_") if safe_cat.startswith("foley_") else safe_cat
        audio_path = BASE_PATH.parent / "output" / "sfx_library" / "foley" / foley_tag / safe_file
    if not audio_path.exists() or audio_path.suffix != ".wav":
        raise HTTPException(status_code=404, detail="SFX file not found")
    return FileResponse(audio_path, media_type="audio/wav")


@router.get("/sfx/player")
async def sfx_player():
    """HTML page for browsing and playing SFX samples."""
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=_SFX_PLAYER_HTML, status_code=200)


_SFX_PLAYER_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>SFX Library + Project Browser</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0d1117;color:#e0e0e0;display:flex;height:100vh}

#sidebar{width:340px;background:#161b22;border-right:1px solid #30363d;display:flex;flex-direction:column;flex-shrink:0}
.sidebar-hdr{padding:14px;border-bottom:1px solid #30363d}
.sidebar-hdr h1{font-size:1.1em;color:#ff6b9d;margin-bottom:10px}
.project-select{width:100%;background:#0d1117;color:#e0e0e0;border:1px solid #30363d;padding:8px 12px;border-radius:6px;font-size:0.85em}
#shots{flex:1;overflow-y:auto;padding:8px}
.scene-hdr{font-size:0.8em;color:#7ee787;padding:8px 8px 4px;margin:0;font-weight:600}
.shot{background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:8px 10px;margin:4px 8px;cursor:pointer;transition:border-color .15s}
.shot:hover{border-color:#58a6ff}
.shot.selected{border-color:#ff6b9d;background:#1a1028}
.shot-num{color:#ff6b9d;font-weight:bold;font-size:0.8em}
.shot-prompt{font-size:0.7em;color:#8b949e;margin-top:3px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.shot-tags{margin-top:4px;display:flex;flex-wrap:wrap;gap:2px}

#main{flex:1;display:flex;flex-direction:column;overflow:hidden}
.main-hdr{padding:16px 24px;border-bottom:1px solid #30363d;background:#161b22;position:sticky;top:0;z-index:10}
.main-hdr h1{font-size:1.2em;color:#ff6b9d;margin-bottom:12px}
#content-wrap{flex:1;overflow-y:auto;padding:20px 24px}

.stats-bar{display:flex;gap:12px;margin-bottom:14px;flex-wrap:wrap}
.chip{background:#21262d;padding:5px 12px;border-radius:16px;font-size:0.8em;border:1px solid #30363d}
.chip strong{color:#ff6b9d;margin-right:4px}

.search{width:100%;background:#0d1117;color:#e0e0e0;border:1px solid #30363d;padding:8px 12px;border-radius:6px;font-size:0.85em;margin-bottom:12px}
.search:focus{outline:none;border-color:#58a6ff}

.filter-section{margin-bottom:6px}
.filter-label{font-size:0.65em;color:#484f58;text-transform:uppercase;letter-spacing:.5px;margin-bottom:3px}
.filter-row{display:flex;gap:5px;flex-wrap:wrap;margin-bottom:4px}
.pill{background:#21262d;color:#8b949e;border:1px solid #30363d;padding:3px 10px;border-radius:14px;cursor:pointer;font-size:0.75em;transition:all .15s}
.pill:hover{border-color:#58a6ff;color:#c9d1d9}
.pill.active{background:#1f6feb;color:white;border-color:#1f6feb}

.cat-card{background:#161b22;border:1px solid #30363d;border-radius:10px;margin-bottom:14px;overflow:hidden}
.cat-hdr{display:flex;align-items:center;justify-content:space-between;padding:11px 16px;cursor:pointer;user-select:none;border-bottom:1px solid transparent}
.cat-hdr:hover{background:#1c2129}
.cat-hdr.open{border-bottom-color:#21262d}
.cat-title{font-size:.95em;font-weight:600;color:#c44dff;display:flex;align-items:center;gap:8px}
.cat-count{background:#21262d;color:#8b949e;font-size:.7em;padding:2px 8px;border-radius:10px}
.cat-arrow{color:#484f58;font-size:.7em;transition:transform .2s}
.cat-arrow.open{transform:rotate(90deg)}
.cat-body{display:none}
.cat-body.open{display:block}

.sgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:1px;background:#21262d}
.scard{background:#0d1117;padding:10px 14px;display:flex;align-items:center;gap:10px;transition:background .1s}
.scard:hover{background:#161b22}
.sicon{width:34px;height:34px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:1.1em;flex-shrink:0}
.sicon.real{background:rgba(163,113,247,.15);color:#a371f7}
.sicon.tts{background:rgba(56,139,253,.15);color:#388bfd}
.sdetails{flex:1;min-width:0}
.sname{font-size:.8em;font-weight:600;color:#e94560;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.smeta{display:flex;gap:5px;align-items:center;margin-top:2px;flex-wrap:wrap}
.tag{font-size:.65em;padding:1px 5px;border-radius:3px;font-weight:500}
.tag-sub{background:rgba(31,111,235,.2);color:#58a6ff}
.tag-int{background:rgba(35,134,54,.2);color:#7ee787}
.tag-int.hard{background:rgba(218,54,51,.2);color:#f85149}
.tag-int.climax{background:rgba(163,113,247,.2);color:#a371f7}
.sreason{font-size:.7em;color:#484f58;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sdur{font-size:.7em;color:#484f58;white-space:nowrap}
.saudio{flex-shrink:0}
.saudio audio{height:28px;width:160px}

.empty{color:#484f58;font-size:.85em;padding:20px;text-align:center}
</style>
</head>
<body>

<div id="sidebar">
  <div class="sidebar-hdr">
    <h1>Project Shots</h1>
    <select id="project-select" class="project-select" onchange="loadShots()">
      <option value="">Select project...</option>
    </select>
  </div>
  <div id="shots"><p class="empty">Select a project to browse shots</p></div>
</div>

<div id="main">
  <div class="main-hdr">
    <h1>SFX Library</h1>
    <div class="stats-bar" id="stats"></div>
    <input type="text" class="search" id="search" placeholder="Search samples by name, category, text..." oninput="onSearch(this.value)">
    <div id="filters"></div>
  </div>
  <div id="content-wrap">
    <div id="content"><p class="empty">Loading...</p></div>
  </div>
</div>

<script>
const SFX_API='/api/voice/sfx', STORY_API='/api/story/projects';
let allSegments=[], activeFilter='all', selectedShot=null, searchTerm='', openCats=new Set();

async function loadProjects(){
  try{
    const d=await(await fetch(STORY_API)).json();
    const sel=document.getElementById('project-select');
    for(const p of(d.projects||d||[]))
      sel.innerHTML+=`<option value="${p.id}">${p.name} (${p.content_rating||'?'})</option>`;
  }catch(e){console.error(e)}
}

async function loadShots(){
  const pid=document.getElementById('project-select').value;
  if(!pid)return;
  const div=document.getElementById('shots');
  div.innerHTML='<p class="empty">Loading...</p>';
  try{
    const scenes=await(await fetch(`/api/scenes?project_id=${pid}`)).json();
    let h='';
    for(const sc of(scenes.scenes||scenes||[])){
      h+=`<div class="scene-hdr">Sc${sc.scene_number}: ${(sc.title||'').substring(0,28)}</div>`;
      const sd=await(await fetch(`/api/scenes/${sc.id}/shots`)).json();
      for(const s of(sd.shots||sd||[])){
        const sfx=(s.sfx_tags||[]).map(t=>`<span class="tag tag-sub">${t}</span>`).join('');
        const foley=(s.foley_tags||[]).map(t=>`<span class="tag tag-int">${t}</span>`).join('');
        h+=`<div class="shot" onclick="selectShot('${s.id}',this)">
          <span class="shot-num">Shot ${s.shot_number}</span>
          <span class="tag tag-int ${s.sfx_intensity||''}">${s.sfx_intensity||'med'}</span>
          <div class="shot-prompt">${(s.generation_prompt||'').substring(0,80)}</div>
          <div class="shot-tags">${sfx}${foley}</div></div>`;
      }
    }
    div.innerHTML=h||'<p class="empty">No shots found</p>';
  }catch(e){div.innerHTML=`<p style="color:#f85149;padding:12px">${e.message}</p>`}
}

function selectShot(id,el){
  document.querySelectorAll('.shot').forEach(s=>s.classList.remove('selected'));
  el.classList.add('selected'); selectedShot=id; renderSegments();
}
function onSearch(v){ searchTerm=v.toLowerCase().trim(); renderSegments(); }

async function loadLibrary(){
  try{
    const[catResp,libResp]=await Promise.all([fetch(`${SFX_API}/catalog`),fetch(`${SFX_API}/library`)]);
    const catalog=catResp.ok?await catResp.json():{samples:[]};
    const lib=libResp.ok?await libResp.json():{categories:{},total:0};
    allSegments=[];
    const catSet=new Set(),subSet=new Set(),intSet=new Set();
    for(const[cat,segs] of Object.entries(lib.categories||{})){
      catSet.add(cat);
      for(const s of segs){s._type='real';if(s.sub_category)subSet.add(s.sub_category);if(s.intensity)intSet.add(s.intensity);allSegments.push(s)}
    }
    for(const s of(catalog.samples||[])){s._type='tts';s.category=s.category||'tts';catSet.add(s.category);allSegments.push(s)}

    document.getElementById('stats').innerHTML=`
      <div class="chip"><strong>${lib.total||0}</strong>Real</div>
      <div class="chip"><strong>${(catalog.samples||[]).length}</strong>TTS</div>
      <div class="chip"><strong>${catSet.size}</strong>Categories</div>
      <div class="chip"><strong>${allSegments.length}</strong>Total</div>`;

    let fh='<div class="filter-section"><div class="filter-label">Category</div><div class="filter-row">';
    fh+=`<span class="pill active" onclick="setFilter('all',this)">All</span>`;
    for(const c of[...catSet].sort()){
      const n=allSegments.filter(s=>s.category===c).length;
      fh+=`<span class="pill" onclick="setFilter('${c}',this)">${c.replace(/_/g,' ')} (${n})</span>`;
    }
    fh+='</div></div>';
    if(subSet.size){
      fh+='<div class="filter-section"><div class="filter-label">Sub-category</div><div class="filter-row">';
      for(const s of[...subSet].sort())fh+=`<span class="pill" onclick="setFilter('sub:${s}',this)">${s}</span>`;
      fh+='</div></div>';
    }
    if(intSet.size){
      fh+='<div class="filter-section"><div class="filter-label">Intensity</div><div class="filter-row">';
      for(const i of['soft','medium','hard','climax'])if(intSet.has(i))fh+=`<span class="pill" onclick="setFilter('int:${i}',this)">${i}</span>`;
      fh+='</div></div>';
    }
    document.getElementById('filters').innerHTML=fh;
    if(catSet.size)openCats.add([...catSet].sort()[0]);
    renderSegments();
  }catch(e){document.getElementById('content').innerHTML=`<p style="color:#f85149">${e.message}</p>`}
}

function setFilter(f,el){
  activeFilter=f;
  document.querySelectorAll('.pill').forEach(b=>b.classList.remove('active'));
  el.classList.add('active'); renderSegments();
}

function toggleCat(cat){
  if(openCats.has(cat))openCats.delete(cat);else openCats.add(cat);
  const b=document.getElementById('cb-'+cat), a=document.getElementById('ca-'+cat);
  if(b)b.classList.toggle('open'); if(a)a.classList.toggle('open');
  const h=document.getElementById('ch-'+cat); if(h)h.classList.toggle('open');
}

function renderSegments(){
  let f=allSegments;
  if(activeFilter!=='all'){
    if(activeFilter.startsWith('sub:'))f=f.filter(s=>s.sub_category===activeFilter.slice(4));
    else if(activeFilter.startsWith('int:'))f=f.filter(s=>s.intensity===activeFilter.slice(4));
    else f=f.filter(s=>s.category===activeFilter);
  }
  if(searchTerm)f=f.filter(s=>[s.filename,s.name,s.category,s.sub_category,s.reason,s.text,s.intensity].filter(Boolean).join(' ').toLowerCase().includes(searchTerm));

  const groups={};
  for(const s of f){const c=s.category||'unknown';if(!groups[c])groups[c]=[];groups[c].push(s)}
  const sorted=Object.entries(groups).sort((a,b)=>b[1].length-a[1].length);
  if(searchTerm||activeFilter!=='all')for(const[c] of sorted)openCats.add(c);

  let h='';
  for(const[cat,segs] of sorted){
    const open=openCats.has(cat);
    const cid=cat.replace(/[^a-zA-Z0-9]/g,'_');
    h+=`<div class="cat-card">
      <div id="ch-${cid}" class="cat-hdr${open?' open':''}" onclick="toggleCat('${cid}')">
        <div class="cat-title"><span id="ca-${cid}" class="cat-arrow${open?' open':''}">&#9654;</span>${cat.replace(/_/g,' ')}<span class="cat-count">${segs.length}</span></div>
      </div>
      <div id="cb-${cid}" class="cat-body${open?' open':''}"><div class="sgrid">`;

    for(const s of segs){
      if(s._type==='tts'){
        h+=`<div class="scard">
          <div class="sicon tts">&#9835;</div>
          <div class="sdetails"><div class="sname">${s.name||s.filename||'?'}</div>
            <div class="smeta"><span class="tag tag-sub">tts</span><span class="sreason">${(s.text||'').substring(0,50)}</span></div></div>
          <div class="saudio"><audio controls preload="none" src="${SFX_API}/audio/${s.category}/${s.name}.wav"></audio></div></div>`;
      } else {
        const sub=s.sub_category?`<span class="tag tag-sub">${s.sub_category}</span>`:'';
        const int=s.intensity?`<span class="tag tag-int ${s.intensity}">${s.intensity}</span>`:'';
        const dur=s.features?.duration||s.duration||0;
        const conf=s.confidence?` ${(s.confidence*100).toFixed(0)}%`:'';
        h+=`<div class="scard">
          <div class="sicon real">&#9836;</div>
          <div class="sdetails"><div class="sname">${s.filename}</div>
            <div class="smeta">${sub}${int}<span class="sreason">${(s.reason||'').substring(0,50)}</span><span class="sdur">${dur.toFixed(1)}s${conf}</span></div></div>
          <div class="saudio"><audio controls preload="none" src="${SFX_API}/audio/${cat}/${s.filename}"></audio></div></div>`;
      }
    }
    h+='</div></div></div>';
  }
  document.getElementById('content').innerHTML=h||'<p class="empty">No segments match</p>';
}

loadProjects(); loadLibrary();
</script>
</body>
</html>
"""
