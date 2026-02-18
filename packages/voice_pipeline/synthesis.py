"""Voice synthesis — multi-engine speech generation with scene integration.

Resolution order for voice engine:
1. RVC v2 model (highest quality, if trained)
2. GPT-SoVITS model (fast prototyping, if trained)
3. edge-tts with character's preset voice
4. edge-tts default voice
"""

import asyncio
import json
import logging
import os
import subprocess
import uuid
from datetime import datetime
from pathlib import Path

from packages.core.config import BASE_PATH, OLLAMA_URL
from packages.core.db import connect_direct

logger = logging.getLogger(__name__)

VOICE_DATASETS = BASE_PATH.parent / "voice_datasets"
SOVITS_DIR = Path("/opt/GPT-SoVITS")
RVC_DIR = Path("/opt/rvc-v2")

# Default edge-tts voice when character has no preset
DEFAULT_EDGE_VOICE = "en-US-GuyNeural"


async def _get_voice_profile(character_slug: str) -> dict:
    """Load voice_profile JSONB from characters table."""
    conn = await connect_direct()
    try:
        raw = await conn.fetchval(
            "SELECT voice_profile FROM characters WHERE REGEXP_REPLACE(LOWER(REPLACE(name, ' ', '_')), '[^a-z0-9_-]', '', 'g') = $1 AND project_id IS NOT NULL",
            character_slug,
        )
        if raw:
            return json.loads(raw) if isinstance(raw, str) else raw
        return {}
    finally:
        await conn.close()


async def synthesize_dialogue(
    character_slug: str,
    text: str,
    engine: str | None = None,
    output_dir: Path | None = None,
) -> dict:
    """Generate speech from text using the best available voice for a character.

    Args:
        character_slug: Character identifier
        text: Text to speak
        engine: Force specific engine ('rvc', 'sovits', 'edge-tts'), or None for auto
        output_dir: Where to save output WAV, defaults to voice_datasets/{slug}/synthesis/

    Returns:
        dict with output_path, engine_used, duration_seconds
    """
    profile = await _get_voice_profile(character_slug)
    if output_dir is None:
        output_dir = VOICE_DATASETS / character_slug / "synthesis"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / f"synth_{uuid.uuid4().hex[:8]}.wav"

    # Determine engine to use
    if engine is None:
        if profile.get("rvc_model_path") and Path(profile["rvc_model_path"]).exists():
            engine = "rvc"
        elif profile.get("sovits_model_path") and Path(profile["sovits_model_path"]).exists():
            engine = "sovits"
        else:
            engine = "edge-tts"

    success = False
    if engine == "rvc":
        success = await _synthesize_rvc(profile, text, output_path)
    elif engine == "sovits":
        success = await _synthesize_sovits(profile, text, output_path)

    if not success:
        # Fallback to edge-tts
        engine = "edge-tts"
        success = await _synthesize_edge_tts(profile, text, output_path)

    if not success:
        return {"error": "All synthesis engines failed"}

    # Get output duration
    duration = 0.0
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(output_path)],
            capture_output=True, text=True, timeout=10,
        )
        duration = float(result.stdout.strip()) if result.stdout.strip() else 0
    except Exception:
        pass

    return {
        "output_path": str(output_path),
        "engine_used": engine,
        "duration_seconds": round(duration, 2),
        "character_slug": character_slug,
        "text": text,
    }


async def _synthesize_rvc(profile: dict, text: str, output_path: Path) -> bool:
    """Synthesize via RVC v2: edge-tts → source audio → RVC conversion."""
    rvc_model = profile.get("rvc_model_path")
    if not rvc_model or not Path(rvc_model).exists():
        return False

    # Step 1: Generate source audio with edge-tts
    source_path = output_path.with_suffix(".source.wav")
    edge_voice = profile.get("voice_preset", DEFAULT_EDGE_VOICE)

    try:
        proc = await asyncio.create_subprocess_exec(
            "edge-tts", "--voice", edge_voice, "--text", text,
            "--write-media", str(source_path),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.wait(), timeout=30)
    except Exception as e:
        logger.warning(f"edge-tts source generation failed: {e}")
        return False

    if not source_path.exists():
        return False

    # Step 2: Run RVC voice conversion
    try:
        cmd = [
            str(RVC_DIR / "venv" / "bin" / "python"),
            str(RVC_DIR / "tools" / "infer_cli.py"),
            "--model_path", rvc_model,
            "--input_path", str(source_path),
            "--output_path", str(output_path),
            "--f0method", "rmvpe",
            "--index_rate", "0.75",
        ]

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120,
            cwd=str(RVC_DIR),
            env={**os.environ, "CUDA_VISIBLE_DEVICES": "0"},
        )

        source_path.unlink(missing_ok=True)

        if result.returncode == 0 and output_path.exists():
            return True
        logger.warning(f"RVC inference failed: {result.stderr[:500]}")
        return False

    except Exception as e:
        logger.warning(f"RVC synthesis failed: {e}")
        source_path.unlink(missing_ok=True)
        return False


async def _synthesize_sovits(profile: dict, text: str, output_path: Path) -> bool:
    """Synthesize via GPT-SoVITS using reference audio."""
    sovits_model = profile.get("sovits_model_path")
    ref_audio = profile.get("ref_audio")

    if not sovits_model or not Path(sovits_model).exists():
        return False
    if not ref_audio or not Path(ref_audio).exists():
        return False

    try:
        cmd = [
            str(SOVITS_DIR / "venv" / "bin" / "python"),
            str(SOVITS_DIR / "GPT_SoVITS" / "inference_cli.py"),
            "--model_path", sovits_model,
            "--ref_audio", ref_audio,
            "--text", text,
            "--output_path", str(output_path),
            "--language", "en",
        ]

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120,
            cwd=str(SOVITS_DIR),
            env={**os.environ, "CUDA_VISIBLE_DEVICES": "0"},
        )

        if result.returncode == 0 and output_path.exists():
            return True
        logger.warning(f"SoVITS inference failed: {result.stderr[:500]}")
        return False

    except Exception as e:
        logger.warning(f"SoVITS synthesis failed: {e}")
        return False


async def _synthesize_edge_tts(profile: dict, text: str, output_path: Path) -> bool:
    """Synthesize using edge-tts with character's preset voice or default."""
    voice = profile.get("voice_preset", DEFAULT_EDGE_VOICE)

    try:
        proc = await asyncio.create_subprocess_exec(
            "edge-tts", "--voice", voice, "--text", text,
            "--write-media", str(output_path),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.wait(), timeout=30)
        return output_path.exists()
    except Exception as e:
        logger.warning(f"edge-tts failed: {e}")
        return False


async def synthesize_scene_dialogue(
    scene_id: str,
    dialogue_list: list[dict],
    pause_seconds: float = 0.5,
) -> dict:
    """Synthesize all dialogue lines for a scene and concatenate with pauses.

    dialogue_list: [{"character_slug": "mario", "text": "It's-a me!"}, ...]
    """
    output_dir = VOICE_DATASETS / "_scenes" / scene_id
    output_dir.mkdir(parents=True, exist_ok=True)

    results = []
    wav_files = []

    for i, line in enumerate(dialogue_list):
        slug = line.get("character_slug", "")
        text = line.get("text", "")
        if not text:
            continue

        result = await synthesize_dialogue(
            character_slug=slug,
            text=text,
            engine=line.get("engine"),
            output_dir=output_dir,
        )
        results.append(result)

        if "output_path" in result:
            wav_files.append(result["output_path"])

    if not wav_files:
        return {"error": "No dialogue synthesized successfully"}

    # Create silence pad
    silence_path = output_dir / "silence.wav"
    subprocess.run(
        ["ffmpeg", "-f", "lavfi", "-i",
         f"anullsrc=r=22050:cl=mono:d={pause_seconds}",
         "-acodec", "pcm_s16le", str(silence_path), "-y"],
        capture_output=True, timeout=10,
    )

    # Build concat list interleaving dialogue with pauses
    concat_list = output_dir / "dialogue_concat.txt"
    with open(concat_list, "w") as f:
        for i, wav in enumerate(wav_files):
            f.write(f"file '{wav}'\n")
            if i < len(wav_files) - 1 and silence_path.exists():
                f.write(f"file '{silence_path}'\n")

    # Concatenate
    combined_path = output_dir / "scene_dialogue.wav"
    subprocess.run(
        ["ffmpeg", "-f", "concat", "-safe", "0", "-i", str(concat_list),
         "-acodec", "pcm_s16le", str(combined_path), "-y"],
        capture_output=True, timeout=60,
    )

    silence_path.unlink(missing_ok=True)
    concat_list.unlink(missing_ok=True)

    # Get total duration
    duration = 0.0
    if combined_path.exists():
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(combined_path)],
                capture_output=True, text=True, timeout=10,
            )
            duration = float(result.stdout.strip()) if result.stdout.strip() else 0
        except Exception:
            pass

    # Record in DB
    conn = await connect_direct()
    try:
        for r in results:
            if "output_path" in r:
                job_id = f"synth_{uuid.uuid4().hex[:8]}"
                await conn.execute("""
                    INSERT INTO voice_synthesis_jobs
                        (job_id, scene_id, character_slug, engine, text,
                         output_path, duration_seconds, status, created_at, completed_at)
                    VALUES ($1, $2::uuid, $3, $4, $5, $6, $7, 'completed', NOW(), NOW())
                """, job_id, scene_id, r.get("character_slug", ""),
                    r.get("engine_used", ""), r.get("text", ""),
                    r.get("output_path", ""), r.get("duration_seconds", 0))
    finally:
        await conn.close()

    return {
        "scene_id": scene_id,
        "dialogue_count": len(results),
        "combined_path": str(combined_path) if combined_path.exists() else None,
        "total_duration_seconds": round(duration, 2),
        "lines": results,
    }


async def generate_dialogue_from_story(
    scene_id: str,
    description: str,
    characters: list[str],
) -> list[dict]:
    """Use LLM (gemma3 via Ollama) to write dialogue for a scene.

    Returns list of {"character_slug": str, "text": str} ready for synthesis.
    """
    import httpx

    char_list = ", ".join(characters)
    prompt = f"""Write short dialogue for an anime scene.

Scene description: {description}
Characters present: {char_list}

Write 3-6 lines of dialogue. Output ONLY a JSON array where each element has "character" (name) and "text" (spoken line).
Example: [{{"character": "Mario", "text": "Let's-a go!"}}]

Keep lines short (1-2 sentences). Match character personalities. No narration."""

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(f"{OLLAMA_URL}/api/generate", json={
                "model": "gemma3:12b",
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.7},
            })
            resp.raise_for_status()
            text = resp.json().get("response", "")

        # Parse JSON from response (may be wrapped in markdown code block)
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        dialogue = json.loads(text)
        if not isinstance(dialogue, list):
            return []

        # Convert character names to slugs
        import re
        results = []
        for line in dialogue:
            name = line.get("character", "")
            slug = re.sub(r'[^a-z0-9_-]', '', name.lower().replace(' ', '_'))
            results.append({
                "character_slug": slug,
                "character_name": name,
                "text": line.get("text", ""),
            })
        return results

    except Exception as e:
        logger.error(f"Dialogue generation failed: {e}")
        return []


async def get_voice_models(character_slug: str) -> dict:
    """Get available voice models/options for a character."""
    profile = await _get_voice_profile(character_slug)

    models = {
        "character_slug": character_slug,
        "available_engines": [],
        "preferred_engine": None,
        "voice_preset": profile.get("voice_preset"),
    }

    if profile.get("rvc_model_path") and Path(profile["rvc_model_path"]).exists():
        models["available_engines"].append({
            "engine": "rvc",
            "model_path": profile["rvc_model_path"],
            "quality": "production",
        })
        models["preferred_engine"] = "rvc"

    if profile.get("sovits_model_path") and Path(profile["sovits_model_path"]).exists():
        models["available_engines"].append({
            "engine": "sovits",
            "model_path": profile["sovits_model_path"],
            "quality": "prototype",
        })
        if not models["preferred_engine"]:
            models["preferred_engine"] = "sovits"

    # edge-tts always available
    models["available_engines"].append({
        "engine": "edge-tts",
        "voice": profile.get("voice_preset", DEFAULT_EDGE_VOICE),
        "quality": "fallback",
    })
    if not models["preferred_engine"]:
        models["preferred_engine"] = "edge-tts"

    return models
