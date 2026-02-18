"""Voice clone training — GPT-SoVITS (fast prototyping) and RVC v2 (production quality).

Both engines run via subprocess in their own venvs to avoid dependency conflicts.
Job status is tracked in the DB (voice_training_jobs table).
"""

import asyncio
import json
import logging
import os
import signal
import subprocess
import uuid
from datetime import datetime
from pathlib import Path

from packages.core.config import BASE_PATH
from packages.core.db import connect_direct
from packages.core.events import event_bus, VOICE_TRAINING_SUBMITTED, VOICE_TRAINING_COMPLETED

logger = logging.getLogger(__name__)

VOICE_DATASETS = BASE_PATH.parent / "voice_datasets"
SOVITS_DIR = Path("/opt/GPT-SoVITS")
RVC_DIR = Path("/opt/rvc-v2")

# Track running processes
_running_jobs: dict[str, subprocess.Popen] = {}


def _get_approved_samples(character_slug: str) -> list[Path]:
    """Get list of approved WAV samples for a character."""
    char_dir = VOICE_DATASETS / character_slug / "samples"
    if not char_dir.is_dir():
        return []

    approval_path = VOICE_DATASETS / character_slug / "approval_status.json"
    if not approval_path.exists():
        return []

    with open(approval_path) as f:
        statuses = json.load(f)

    return [
        char_dir / fname
        for fname, status in statuses.items()
        if status == "approved" and (char_dir / fname).exists()
    ]


def _total_duration(wav_files: list[Path]) -> float:
    """Sum durations of WAV files using ffprobe."""
    total = 0.0
    for wav in wav_files:
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(wav)],
                capture_output=True, text=True, timeout=10,
            )
            total += float(result.stdout.strip()) if result.stdout.strip() else 0
        except Exception:
            pass
    return round(total, 2)


async def start_sovits_training(
    character_slug: str,
    character_name: str = "",
    project_name: str = "",
    epochs: int = 8,
) -> dict:
    """Start GPT-SoVITS training for a character via subprocess.

    Requires minimum 5 seconds of approved audio.
    Training typically takes 5-10 minutes on RTX 3060.
    """
    if not SOVITS_DIR.exists():
        return {"error": f"GPT-SoVITS not installed at {SOVITS_DIR}. Run scripts/setup_voice_engines.sh"}

    samples = _get_approved_samples(character_slug)
    if not samples:
        return {"error": f"No approved voice samples for '{character_slug}'"}

    total_dur = _total_duration(samples)
    if total_dur < 5.0:
        return {"error": f"Minimum 5s audio required, have {total_dur}s. Approve more samples."}

    job_id = f"sovits_{character_slug}_{uuid.uuid4().hex[:8]}"
    output_dir = VOICE_DATASETS / character_slug / "sovits_model"
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / f"{job_id}.log"

    # Create training list file (GPT-SoVITS format)
    list_file = output_dir / "train_list.txt"
    with open(list_file, "w") as f:
        for wav in samples:
            # GPT-SoVITS expects: wav_path|speaker_name|language|text
            txt_path = wav.with_suffix(".txt")
            text = ""
            if txt_path.exists():
                text = txt_path.read_text().strip()
            f.write(f"{wav}|{character_name or character_slug}|en|{text}\n")

    # Record job in DB
    conn = await connect_direct()
    try:
        await conn.execute("""
            INSERT INTO voice_training_jobs (job_id, character_slug, character_name,
                project_name, engine, status, approved_samples, total_duration_seconds,
                epochs, log_path, created_at)
            VALUES ($1, $2, $3, $4, 'sovits', 'queued', $5, $6, $7, $8, NOW())
        """, job_id, character_slug, character_name, project_name,
            len(samples), total_dur, epochs, str(log_path))
    finally:
        await conn.close()

    await event_bus.emit(VOICE_TRAINING_SUBMITTED, {
        "job_id": job_id,
        "character_slug": character_slug,
        "engine": "sovits",
        "samples": len(samples),
        "duration": total_dur,
    })

    # Launch training subprocess
    asyncio.create_task(_run_sovits_training(
        job_id, character_slug, character_name, output_dir, list_file, epochs, log_path
    ))

    return {
        "job_id": job_id,
        "engine": "sovits",
        "character_slug": character_slug,
        "samples": len(samples),
        "total_duration_seconds": total_dur,
        "epochs": epochs,
        "status": "queued",
    }


async def _run_sovits_training(
    job_id: str, character_slug: str, character_name: str,
    output_dir: Path, list_file: Path, epochs: int, log_path: Path,
):
    """Execute GPT-SoVITS training in background subprocess."""
    conn = await connect_direct()
    try:
        await conn.execute(
            "UPDATE voice_training_jobs SET status = 'running', started_at = NOW() WHERE job_id = $1",
            job_id,
        )

        model_name = f"{character_slug}_sovits"
        cmd = [
            str(SOVITS_DIR / "venv" / "bin" / "python"),
            str(SOVITS_DIR / "GPT_SoVITS" / "s2_train.py"),
            "--train_list", str(list_file),
            "--exp_name", model_name,
            "--epochs", str(epochs),
            "--save_dir", str(output_dir),
        ]

        with open(log_path, "w") as logf:
            proc = subprocess.Popen(
                cmd, stdout=logf, stderr=subprocess.STDOUT,
                cwd=str(SOVITS_DIR),
                env={**os.environ, "CUDA_VISIBLE_DEVICES": "0"},
            )
            _running_jobs[job_id] = proc

            await conn.execute(
                "UPDATE voice_training_jobs SET pid = $1 WHERE job_id = $2",
                proc.pid, job_id,
            )

        # Wait for completion in a thread to avoid blocking
        loop = asyncio.get_event_loop()
        returncode = await loop.run_in_executor(None, proc.wait)

        _running_jobs.pop(job_id, None)

        model_path = output_dir / f"{model_name}.pth"
        if returncode == 0 and model_path.exists():
            await conn.execute("""
                UPDATE voice_training_jobs
                SET status = 'completed', completed_at = NOW(), model_path = $1
                WHERE job_id = $2
            """, str(model_path), job_id)

            # Update character voice_profile
            await _update_voice_profile(conn, character_slug, "sovits", str(model_path))

            await event_bus.emit(VOICE_TRAINING_COMPLETED, {
                "job_id": job_id, "character_slug": character_slug,
                "engine": "sovits", "model_path": str(model_path),
            })
            logger.info(f"SoVITS training completed: {job_id} → {model_path}")
        else:
            error_msg = f"Process exited with code {returncode}"
            if log_path.exists():
                lines = log_path.read_text().strip().split("\n")
                error_msg = lines[-1] if lines else error_msg
            await conn.execute(
                "UPDATE voice_training_jobs SET status = 'failed', error = $1 WHERE job_id = $2",
                error_msg[:1000], job_id,
            )
            logger.error(f"SoVITS training failed: {job_id} — {error_msg}")

    except Exception as e:
        logger.error(f"SoVITS training error: {e}")
        await conn.execute(
            "UPDATE voice_training_jobs SET status = 'failed', error = $1 WHERE job_id = $2",
            str(e)[:1000], job_id,
        )
    finally:
        await conn.close()


async def start_rvc_training(
    character_slug: str,
    character_name: str = "",
    project_name: str = "",
    epochs: int = 40,
) -> dict:
    """Start RVC v2 training for a character via subprocess.

    Recommended: 5+ minutes of approved audio for production quality.
    Training typically takes ~45 minutes on RTX 3060.
    """
    if not RVC_DIR.exists():
        return {"error": f"RVC v2 not installed at {RVC_DIR}. Run scripts/setup_voice_engines.sh"}

    samples = _get_approved_samples(character_slug)
    if not samples:
        return {"error": f"No approved voice samples for '{character_slug}'"}

    total_dur = _total_duration(samples)
    if total_dur < 10.0:
        return {"error": f"Minimum 10s audio required for RVC, have {total_dur}s. Approve more samples."}

    job_id = f"rvc_{character_slug}_{uuid.uuid4().hex[:8]}"
    output_dir = VOICE_DATASETS / character_slug / "rvc_model"
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / f"{job_id}.log"

    # Combine approved samples into single WAV for RVC
    combined_wav = output_dir / "combined_training.wav"
    filelist = output_dir / "filelist.txt"
    with open(filelist, "w") as f:
        for wav in samples:
            f.write(f"file '{wav}'\n")

    subprocess.run(
        ["ffmpeg", "-f", "concat", "-safe", "0", "-i", str(filelist),
         "-acodec", "pcm_s16le", "-ar", "40000", "-ac", "1",
         str(combined_wav), "-y"],
        capture_output=True, timeout=60,
    )

    # Record job in DB
    conn = await connect_direct()
    try:
        await conn.execute("""
            INSERT INTO voice_training_jobs (job_id, character_slug, character_name,
                project_name, engine, status, approved_samples, total_duration_seconds,
                epochs, log_path, created_at)
            VALUES ($1, $2, $3, $4, 'rvc', 'queued', $5, $6, $7, $8, NOW())
        """, job_id, character_slug, character_name, project_name,
            len(samples), total_dur, epochs, str(log_path))
    finally:
        await conn.close()

    await event_bus.emit(VOICE_TRAINING_SUBMITTED, {
        "job_id": job_id, "character_slug": character_slug,
        "engine": "rvc", "samples": len(samples), "duration": total_dur,
    })

    asyncio.create_task(_run_rvc_training(
        job_id, character_slug, character_name, output_dir, combined_wav, epochs, log_path
    ))

    return {
        "job_id": job_id,
        "engine": "rvc",
        "character_slug": character_slug,
        "samples": len(samples),
        "total_duration_seconds": total_dur,
        "epochs": epochs,
        "status": "queued",
    }


async def _run_rvc_training(
    job_id: str, character_slug: str, character_name: str,
    output_dir: Path, combined_wav: Path, epochs: int, log_path: Path,
):
    """Execute RVC v2 training in background subprocess."""
    conn = await connect_direct()
    try:
        await conn.execute(
            "UPDATE voice_training_jobs SET status = 'running', started_at = NOW() WHERE job_id = $1",
            job_id,
        )

        model_name = f"{character_slug}_voice"
        cmd = [
            str(RVC_DIR / "venv" / "bin" / "python"),
            str(RVC_DIR / "infer" / "modules" / "train" / "train.py"),
            "--experiment_dir", str(output_dir),
            "--model_name", model_name,
            "--training_file", str(combined_wav),
            "--total_epoch", str(epochs),
            "--sample_rate", "40000",
            "--batch_size", "8",
        ]

        with open(log_path, "w") as logf:
            proc = subprocess.Popen(
                cmd, stdout=logf, stderr=subprocess.STDOUT,
                cwd=str(RVC_DIR),
                env={**os.environ, "CUDA_VISIBLE_DEVICES": "0"},
            )
            _running_jobs[job_id] = proc

            await conn.execute(
                "UPDATE voice_training_jobs SET pid = $1 WHERE job_id = $2",
                proc.pid, job_id,
            )

        loop = asyncio.get_event_loop()
        returncode = await loop.run_in_executor(None, proc.wait)

        _running_jobs.pop(job_id, None)

        model_path = output_dir / f"{model_name}.pth"
        # RVC may output to a different location — check alternatives
        if not model_path.exists():
            pth_files = list(output_dir.glob("*.pth"))
            if pth_files:
                model_path = pth_files[0]

        if returncode == 0 and model_path.exists():
            await conn.execute("""
                UPDATE voice_training_jobs
                SET status = 'completed', completed_at = NOW(), model_path = $1
                WHERE job_id = $2
            """, str(model_path), job_id)

            await _update_voice_profile(conn, character_slug, "rvc", str(model_path))

            await event_bus.emit(VOICE_TRAINING_COMPLETED, {
                "job_id": job_id, "character_slug": character_slug,
                "engine": "rvc", "model_path": str(model_path),
            })
            logger.info(f"RVC training completed: {job_id} → {model_path}")
        else:
            error_msg = f"Process exited with code {returncode}"
            if log_path.exists():
                lines = log_path.read_text().strip().split("\n")
                error_msg = lines[-1] if lines else error_msg
            await conn.execute(
                "UPDATE voice_training_jobs SET status = 'failed', error = $1 WHERE job_id = $2",
                error_msg[:1000], job_id,
            )
            logger.error(f"RVC training failed: {job_id} — {error_msg}")

    except Exception as e:
        logger.error(f"RVC training error: {e}")
        await conn.execute(
            "UPDATE voice_training_jobs SET status = 'failed', error = $1 WHERE job_id = $2",
            str(e)[:1000], job_id,
        )
    finally:
        await conn.close()


async def _update_voice_profile(conn, character_slug: str, engine: str, model_path: str):
    """Update character's voice_profile JSONB with the new model path."""
    existing = await conn.fetchval(
        "SELECT voice_profile FROM characters WHERE REGEXP_REPLACE(LOWER(REPLACE(name, ' ', '_')), '[^a-z0-9_-]', '', 'g') = $1 AND project_id IS NOT NULL",
        character_slug,
    )

    profile = json.loads(existing) if existing else {}
    profile[f"{engine}_model_path"] = model_path
    profile["trained_at"] = datetime.now().isoformat()

    if engine == "rvc":
        profile["tts_model"] = "rvc"
    elif engine == "sovits" and profile.get("tts_model") != "rvc":
        profile["tts_model"] = "sovits"

    # Pick a reference audio from approved samples
    samples = _get_approved_samples(character_slug)
    if samples and "ref_audio" not in profile:
        profile["ref_audio"] = str(samples[0])

    await conn.execute("""
        UPDATE characters SET voice_profile = $1::jsonb
        WHERE REGEXP_REPLACE(LOWER(REPLACE(name, ' ', '_')), '[^a-z0-9_-]', '', 'g') = $2
          AND project_id IS NOT NULL
    """, json.dumps(profile), character_slug)

    logger.info(f"Updated voice_profile for {character_slug}: {engine} model at {model_path}")


async def cancel_training_job(job_id: str) -> dict:
    """Cancel a running training job."""
    proc = _running_jobs.get(job_id)
    if proc and proc.poll() is None:
        proc.send_signal(signal.SIGTERM)
        _running_jobs.pop(job_id, None)

    conn = await connect_direct()
    try:
        await conn.execute(
            "UPDATE voice_training_jobs SET status = 'failed', error = 'Cancelled by user' WHERE job_id = $1",
            job_id,
        )
    finally:
        await conn.close()

    return {"job_id": job_id, "status": "cancelled"}


async def get_training_jobs(project_name: str = None, character_slug: str = None) -> list[dict]:
    """List voice training jobs, optionally filtered."""
    conn = await connect_direct()
    try:
        query = "SELECT * FROM voice_training_jobs WHERE 1=1"
        params = []
        idx = 1
        if project_name:
            query += f" AND project_name = ${idx}"
            params.append(project_name)
            idx += 1
        if character_slug:
            query += f" AND character_slug = ${idx}"
            params.append(character_slug)
            idx += 1
        query += " ORDER BY created_at DESC"

        rows = await conn.fetch(query, *params)
        return [dict(r) for r in rows]
    finally:
        await conn.close()


async def get_training_job(job_id: str) -> dict | None:
    """Get a single training job by ID."""
    conn = await connect_direct()
    try:
        row = await conn.fetchrow(
            "SELECT * FROM voice_training_jobs WHERE job_id = $1", job_id
        )
        return dict(row) if row else None
    finally:
        await conn.close()


def get_training_log(job_id: str, lines: int = 50) -> str:
    """Read the last N lines of a training job's log file."""
    for job_data in _running_jobs:
        pass  # We need the DB path

    # Search in voice_datasets for log files
    for log_file in VOICE_DATASETS.rglob(f"{job_id}.log"):
        if log_file.exists():
            all_lines = log_file.read_text().strip().split("\n")
            return "\n".join(all_lines[-lines:])

    return ""
