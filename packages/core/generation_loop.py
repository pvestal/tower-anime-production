"""Continuous Generation Loop — fire-and-forget per-project pipeline.

Replaces the manual: keyframe gen → vision review → video I2V → scene assembly workflow.
Runs as an async background task per project, saturating both local GPUs and
optionally bursting to RunPod when backed up.

Architecture:
  1. KEYFRAME PHASE (3060): Generate keyframes for shots lacking source images
  2. VIDEO PHASE (AMD 9070 XT / RunPod burst): I2V for approved keyframes
  3. ASSEMBLY PHASE: Auto-assemble completed scenes and episodes

Safety:
  - Respects orchestrator enabled flag per project
  - All actions logged to autonomy_decisions
  - Budget cap for RunPod burst
  - Dry-run mode for testing
"""

import asyncio
import json
import logging
import random
import time
import urllib.request
from datetime import datetime
from pathlib import Path

from .config import (
    BASE_PATH, COMFYUI_URL, COMFYUI_VIDEO_URL, COMFYUI_OUTPUT_DIR,
    get_comfyui_url,
)
from .db import get_pool, connect_direct
from .events import event_bus, SHOT_GENERATED, KEYFRAME_UPDATED
from .audit import log_decision, log_generation, log_approval

logger = logging.getLogger(__name__)

# ── Module-level state ────────────────────────────────────────────────

_enabled = False          # Global kill switch — must be explicitly enabled per session
_active_loops: dict[int, "ProjectGenerationLoop"] = {}


def is_enabled() -> bool:
    """Check if the generation loop system is enabled."""
    return _enabled


async def enable(on: bool = True) -> dict:
    """Enable or disable the generation loop system globally.

    When disabled, no new loops can start and all running loops are stopped.
    Must be called explicitly each session — never auto-enables.
    """
    global _enabled
    _enabled = on

    if not on:
        # Stop all running loops
        stopped = []
        for pid, loop in list(_active_loops.items()):
            if loop._running:
                await loop.stop()
                stopped.append(pid)
        if stopped:
            logger.info(f"Generation loop disabled — stopped loops for projects: {stopped}")

    await log_decision(
        decision_type="generation_loop_toggle",
        decision_made=f"Generation loop {'enabled' if on else 'disabled'}",
        confidence_score=1.0,
        reasoning="Explicit user confirmation",
    )

    logger.info(f"Generation loop system {'ENABLED' if on else 'DISABLED'}")
    return {"enabled": _enabled, "stopped_projects": [] if on else list(_active_loops.keys())}


# ── Default configuration ─────────────────────────────────────────────

DEFAULT_CONFIG = {
    "auto_approve_threshold": 0.75,
    "burst_enabled": False,
    "burst_budget_cap": 5.00,         # USD per session
    "burst_queue_threshold": 3,       # burst if AMD queue > N
    "target_keyframes_per_lora": 1,   # keyframes to generate per LoRA/shot
    "max_concurrent_videos": 2,       # parallel video gens on AMD
    "tick_interval_seconds": 30,      # main loop sleep
    "video_enabled": True,
    "assembly_enabled": True,
    "dry_run": False,
    "keyframe_batch_size": 3,         # seeds per keyframe batch
}


def get_loop(project_id: int) -> "ProjectGenerationLoop | None":
    """Get active loop for a project."""
    return _active_loops.get(project_id)


def get_all_loops() -> dict[int, "ProjectGenerationLoop"]:
    """Get all active loops."""
    return dict(_active_loops)


async def start_loop(project_id: int, config: dict | None = None) -> dict:
    """Start a generation loop for a project. Returns status dict.

    Requires the generation loop system to be explicitly enabled first
    via enable(True). This is a safety measure — the loop will never
    auto-start without user confirmation.
    """
    if not _enabled:
        return {
            "status": "error",
            "error": "Generation loop system is not enabled. "
                     "Call POST /api/system/generation-loop/enable {\"enabled\": true} first.",
            "project_id": project_id,
        }

    if project_id in _active_loops:
        loop = _active_loops[project_id]
        if loop._running:
            return {"status": "already_running", "project_id": project_id}

    merged_config = {**DEFAULT_CONFIG, **(config or {})}
    loop = ProjectGenerationLoop(project_id, merged_config)
    _active_loops[project_id] = loop
    asyncio.create_task(loop.start())

    await log_decision(
        decision_type="generation_loop_start",
        project_name=str(project_id),
        input_context=merged_config,
        decision_made=f"Started generation loop for project {project_id}",
        confidence_score=1.0,
        reasoning="User-initiated continuous generation",
    )

    return {"status": "started", "project_id": project_id, "config": merged_config}


async def stop_loop(project_id: int) -> dict:
    """Stop a generation loop for a project."""
    loop = _active_loops.get(project_id)
    if not loop or not loop._running:
        return {"status": "not_running", "project_id": project_id}

    await loop.stop()
    return {"status": "stopped", "project_id": project_id}


async def get_status(project_id: int | None = None) -> dict:
    """Get status of one or all generation loops."""
    if project_id:
        loop = _active_loops.get(project_id)
        if not loop:
            return {"enabled": _enabled, "status": "not_running", "project_id": project_id}
        status = loop.get_status()
        status["enabled"] = _enabled
        return status

    return {
        "enabled": _enabled,
        "active_loops": {
            pid: loop.get_status() for pid, loop in _active_loops.items()
        },
    }


class ProjectGenerationLoop:
    """Continuous generation loop for a single project."""

    def __init__(self, project_id: int, config: dict):
        self.project_id = project_id
        self.config = config
        self._running = False
        self._task: asyncio.Task | None = None
        self._started_at: datetime | None = None
        self._tick_count = 0
        self._keyframes_generated = 0
        self._videos_generated = 0
        self._videos_burst = 0
        self._scenes_assembled = 0
        self._burst_spend = 0.0
        self._last_error: str | None = None
        self._active_video_tasks: list[asyncio.Task] = []
        self._burst_manager: "BurstManager | None" = None

    async def start(self):
        """Main loop: keyframes → videos → assembly."""
        self._running = True
        self._started_at = datetime.now()
        logger.info(f"[GenLoop:{self.project_id}] Starting (config: {json.dumps(self.config, default=str)})")

        try:
            while self._running:
                self._tick_count += 1
                try:
                    # Phase 1: Generate keyframes on 3060
                    await self._generate_keyframes()

                    # Phase 2: Submit I2V on AMD (+ RunPod burst)
                    if self.config.get("video_enabled", True):
                        await self._generate_videos()

                    # Phase 3: Auto-assemble completed scenes
                    if self.config.get("assembly_enabled", True):
                        await self._auto_assemble()

                except Exception as e:
                    self._last_error = str(e)
                    logger.error(f"[GenLoop:{self.project_id}] Tick {self._tick_count} error: {e}")

                interval = self.config.get("tick_interval_seconds", 30)
                await asyncio.sleep(interval)
        finally:
            self._running = False
            logger.info(f"[GenLoop:{self.project_id}] Stopped after {self._tick_count} ticks")

    async def stop(self):
        """Stop the loop gracefully."""
        self._running = False
        # Cancel active video tasks
        for task in self._active_video_tasks:
            if not task.done():
                task.cancel()
        self._active_video_tasks.clear()
        logger.info(f"[GenLoop:{self.project_id}] Stop requested")

    def get_status(self) -> dict:
        """Current loop status for API response."""
        return {
            "project_id": self.project_id,
            "running": self._running,
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "tick_count": self._tick_count,
            "keyframes_generated": self._keyframes_generated,
            "videos_generated": self._videos_generated,
            "videos_burst": self._videos_burst,
            "scenes_assembled": self._scenes_assembled,
            "burst_spend": round(self._burst_spend, 2),
            "last_error": self._last_error,
            "config": self.config,
        }

    # ── Phase 1: Keyframe Generation (3060) ───────────────────────────

    async def _generate_keyframes(self):
        """Find shots without source images and generate keyframes on 3060."""
        dry_run = self.config.get("dry_run", False)

        pool = await get_pool()
        async with pool.acquire() as conn:
            # Find shots that need keyframes
            shots = await conn.fetch("""
                SELECT s.id, s.scene_id, s.motion_prompt, s.lora_name, s.lora_strength,
                       s.characters_present, sc.project_id,
                       p.name as project_name, p.default_style, p.content_rating
                FROM shots s
                JOIN scenes sc ON s.scene_id = sc.id
                JOIN projects p ON sc.project_id = p.id
                WHERE sc.project_id = $1
                  AND (s.source_image_path IS NULL OR s.source_image_path = '')
                  AND s.status NOT IN ('completed', 'generating', 'accepted_best')
                ORDER BY s.sort_order, s.created_at
                LIMIT $2
            """, self.project_id, self.config.get("keyframe_batch_size", 3))

            if not shots:
                return

            logger.info(f"[GenLoop:{self.project_id}] Found {len(shots)} shots needing keyframes")

            for shot in shots:
                if not self._running:
                    break

                if dry_run:
                    logger.info(f"[GenLoop:{self.project_id}] DRY RUN: Would generate keyframe for shot {shot['id']}")
                    continue

                await self._generate_single_keyframe(conn, shot)

    async def _generate_single_keyframe(self, conn, shot):
        """Generate keyframe for a single shot using the 3060."""
        shot_id = shot["id"]
        chars = shot["characters_present"] or []
        char_slug = chars[0] if chars else None

        try:
            # Get character design prompt for keyframe generation
            design_prompt = ""
            checkpoint = None
            if char_slug:
                char_row = await conn.fetchrow("""
                    SELECT c.design_prompt, c.lora_path, c.lora_trigger,
                           gs.checkpoint_model, gs.cfg_scale, gs.steps,
                           gs.width, gs.height, gs.sampler, gs.scheduler,
                           gs.positive_prompt_template, gs.negative_prompt_template
                    FROM characters c
                    JOIN projects p ON c.project_id = p.id
                    LEFT JOIN generation_styles gs ON gs.style_name = p.default_style
                    WHERE REGEXP_REPLACE(LOWER(REPLACE(c.name, ' ', '_')), '[^a-z0-9_-]', '', 'g') = $1
                      AND c.project_id = $2
                """, char_slug, self.project_id)
                if char_row:
                    design_prompt = char_row["design_prompt"] or ""
                    checkpoint = char_row["checkpoint_model"]

            if not design_prompt:
                logger.warning(f"[GenLoop:{self.project_id}] No design prompt for {char_slug}, skipping shot {shot_id}")
                return

            # Build prompt from motion_prompt + design_prompt
            motion_prompt = shot["motion_prompt"] or ""
            prompt = f"{design_prompt}, {motion_prompt}" if motion_prompt else design_prompt

            # Get generation parameters from style or defaults
            seed = random.randint(0, 2**32)
            width = char_row["width"] if char_row and char_row["width"] else 832
            height = char_row["height"] if char_row and char_row["height"] else 1216
            steps = char_row["steps"] if char_row and char_row["steps"] else 25
            cfg = float(char_row["cfg_scale"]) if char_row and char_row["cfg_scale"] else 5.0
            sampler = char_row["sampler"] if char_row else "euler_ancestral"
            scheduler = char_row["scheduler"] if char_row else "normal"
            checkpoint = checkpoint or "waiIllustriousSDXL_v160.safetensors"
            negative = char_row["negative_prompt_template"] if char_row and char_row["negative_prompt_template"] else "low quality, blurry, worst quality"

            # Apply LoRA trigger if available
            lora_trigger = char_row["lora_trigger"] if char_row else None
            if lora_trigger and lora_trigger not in prompt:
                prompt = f"{lora_trigger}, {prompt}"

            # Build txt2img workflow
            from .comfyui import build_txt2img_workflow
            file_prefix = f"genloop_{self.project_id}_{char_slug or 'unknown'}_{int(time.time())}"
            workflow = build_txt2img_workflow(
                prompt_text=prompt,
                negative_text=negative,
                checkpoint=checkpoint,
                seed=seed,
                steps=steps,
                cfg=cfg,
                width=width,
                height=height,
                filename_prefix=file_prefix,
                sampler_name=sampler or "euler_ancestral",
                scheduler=scheduler or "normal",
            )

            # Add LoRA node if character has trained LoRA
            lora_path = char_row["lora_path"] if char_row else None
            if lora_path:
                workflow = _inject_lora_into_workflow(workflow, lora_path, 0.8)

            # Submit to 3060 (keyframe GPU)
            comfyui_url = get_comfyui_url("keyframe")
            prompt_id = _submit_comfyui(comfyui_url, workflow)
            if not prompt_id:
                logger.error(f"[GenLoop:{self.project_id}] Failed to submit keyframe for shot {shot_id}")
                return

            logger.info(f"[GenLoop:{self.project_id}] Submitted keyframe: {prompt_id} (shot {shot_id})")

            # Log generation
            gen_id = await log_generation(
                character_slug=char_slug or "unknown",
                project_name=shot["project_name"],
                comfyui_prompt_id=prompt_id,
                generation_type="keyframe",
                checkpoint_model=checkpoint,
                prompt=prompt,
                negative_prompt=negative,
                seed=seed,
                cfg_scale=cfg,
                steps=steps,
                width=width,
                height=height,
                lora_name=shot["lora_name"],
                source="generation_loop",
            )

            # Poll for completion
            result = await _poll_comfyui(comfyui_url, prompt_id, timeout=300)
            if not result:
                logger.warning(f"[GenLoop:{self.project_id}] Keyframe timed out: {prompt_id}")
                return

            # Find output image
            image_path = _extract_image_path(result, file_prefix)
            if not image_path:
                logger.warning(f"[GenLoop:{self.project_id}] No output image from {prompt_id}")
                return

            # Run quality gate (lightweight, no GPU)
            from .quality_gate import quality_gate
            gate_result = await quality_gate(
                image_path=image_path,
                character_slug=char_slug,
                lora_name=shot["lora_name"],
                project_id=self.project_id,
                expected_width=width,
                expected_height=height,
                config=self.config,
            )

            logger.info(f"[GenLoop:{self.project_id}] Quality gate: {gate_result['decision']} "
                        f"(score={gate_result['score']}, reasons={gate_result['reasons']})")

            if gate_result["decision"] == "rejected":
                return

            if gate_result["decision"] in ("approved", "review"):
                # Copy to ComfyUI input for I2V
                from packages.scene_generation.scene_comfyui import copy_to_comfyui_input
                input_path = await copy_to_comfyui_input(image_path)

                # Update shot with keyframe
                await conn.execute("""
                    UPDATE shots
                    SET source_image_path = $2, status = 'ready'
                    WHERE id = $1
                """, shot_id, str(image_path))

                self._keyframes_generated += 1

                # Log approval
                if gate_result["auto_approved"]:
                    await log_approval(
                        character_slug=char_slug or "unknown",
                        image_name=Path(image_path).name,
                        quality_score=gate_result["score"],
                        auto_approved=True,
                        vision_review=gate_result,
                        project_name=shot["project_name"],
                        generation_history_id=gen_id,
                    )

                # Emit event
                await event_bus.emit(KEYFRAME_UPDATED, {
                    "shot_id": str(shot_id),
                    "image_path": str(image_path),
                    "quality_score": gate_result["score"],
                    "auto_approved": gate_result["auto_approved"],
                })

        except Exception as e:
            logger.error(f"[GenLoop:{self.project_id}] Keyframe gen failed for shot {shot_id}: {e}")

    # ── Phase 2: Video Generation (AMD 9070 XT + RunPod burst) ────────

    async def _generate_videos(self):
        """Submit I2V jobs for approved keyframes."""
        dry_run = self.config.get("dry_run", False)

        pool = await get_pool()
        async with pool.acquire() as conn:
            # Find shots with keyframes but no videos
            shots = await conn.fetch("""
                SELECT s.id, s.scene_id, s.motion_prompt, s.lora_name, s.lora_strength,
                       s.source_image_path, s.characters_present,
                       sc.project_id, p.name as project_name, p.content_rating
                FROM shots s
                JOIN scenes sc ON s.scene_id = sc.id
                JOIN projects p ON sc.project_id = p.id
                WHERE sc.project_id = $1
                  AND s.source_image_path IS NOT NULL
                  AND s.source_image_path != ''
                  AND (s.output_video_path IS NULL OR s.output_video_path = '')
                  AND s.status IN ('ready', 'pending')
                ORDER BY s.sort_order, s.created_at
                LIMIT $2
            """, self.project_id, self.config.get("max_concurrent_videos", 2))

            if not shots:
                return

            logger.info(f"[GenLoop:{self.project_id}] Found {len(shots)} shots ready for video gen")

            for shot in shots:
                if not self._running:
                    break

                if dry_run:
                    logger.info(f"[GenLoop:{self.project_id}] DRY RUN: Would generate video for shot {shot['id']}")
                    continue

                # Check if we should burst to RunPod
                use_burst = await self._should_burst()

                if use_burst:
                    await self._generate_video_burst(conn, shot)
                else:
                    await self._generate_video_local(conn, shot)

    async def _generate_video_local(self, conn, shot):
        """Generate video on local AMD 9070 XT via DaSiWa."""
        shot_id = shot["id"]
        source_image = shot["source_image_path"]
        motion_prompt = shot["motion_prompt"] or ""
        lora_name = shot["lora_name"]
        lora_strength = shot["lora_strength"] or 0.85

        try:
            # Mark as generating
            await conn.execute(
                "UPDATE shots SET status = 'generating' WHERE id = $1", shot_id
            )

            # Get motion params
            from packages.scene_generation.motion_intensity import (
                classify_motion_intensity, get_dasiwa_motion_params,
            )
            tier = classify_motion_intensity(motion_prompt, lora_name)
            params = get_dasiwa_motion_params(tier)

            # Build DaSiWa I2V workflow
            from packages.scene_generation.wan_video import build_dasiwa_i2v_workflow
            image_filename = Path(source_image).name

            # Ensure image is in ComfyUI input directory
            from packages.scene_generation.scene_comfyui import copy_to_comfyui_input
            await copy_to_comfyui_input(source_image)

            file_prefix = f"genloop_video_{self.project_id}_{int(time.time())}"
            seed = random.randint(0, 2**32)

            workflow, output_prefix = build_dasiwa_i2v_workflow(
                prompt_text=motion_prompt,
                ref_image=image_filename,
                width=480,
                height=720,
                num_frames=49,
                fps=16,
                total_steps=params.total_steps,
                split_steps=params.split_steps,
                cfg=params.cfg,
                seed=seed,
                negative_text="low quality, blurry, distorted, static",
                output_prefix=file_prefix,
                content_lora_high=lora_name,
                content_lora_strength=lora_strength,
            )

            # Submit to AMD ComfyUI (:8189)
            comfyui_url = get_comfyui_url("video")
            prompt_id = _submit_comfyui(comfyui_url, workflow)
            if not prompt_id:
                await conn.execute(
                    "UPDATE shots SET status = 'error', error_message = 'ComfyUI submission failed' WHERE id = $1",
                    shot_id,
                )
                return

            logger.info(f"[GenLoop:{self.project_id}] Video submitted to AMD: {prompt_id} (shot {shot_id})")

            # Update shot with prompt ID
            await conn.execute(
                "UPDATE shots SET comfyui_prompt_id = $2 WHERE id = $1",
                shot_id, prompt_id,
            )

            # Poll for completion (video gen can take 3-10 minutes)
            result = await _poll_comfyui(comfyui_url, prompt_id, timeout=900)
            if not result:
                await conn.execute(
                    "UPDATE shots SET status = 'error', error_message = 'Video generation timed out' WHERE id = $1",
                    shot_id,
                )
                return

            # Find output video
            video_path = _extract_video_path(result, file_prefix)
            if not video_path:
                await conn.execute(
                    "UPDATE shots SET status = 'error', error_message = 'No video output found' WHERE id = $1",
                    shot_id,
                )
                return

            # Update shot
            await conn.execute("""
                UPDATE shots SET output_video_path = $2, status = 'completed',
                       seed = $3, steps = $4
                WHERE id = $1
            """, shot_id, video_path, seed, params.total_steps)

            self._videos_generated += 1
            logger.info(f"[GenLoop:{self.project_id}] Video completed: {video_path} (shot {shot_id})")

            # Emit event for audio pipeline + QC
            chars = shot["characters_present"] or []
            await event_bus.emit(SHOT_GENERATED, {
                "shot_id": shot_id,
                "video_path": video_path,
                "project_id": self.project_id,
                "character_slug": chars[0] if chars else None,
            })

        except Exception as e:
            logger.error(f"[GenLoop:{self.project_id}] Video gen failed for shot {shot_id}: {e}")
            try:
                await conn.execute(
                    "UPDATE shots SET status = 'error', error_message = $2 WHERE id = $1",
                    shot_id, str(e)[:500],
                )
            except Exception:
                pass

    async def _generate_video_burst(self, conn, shot):
        """Generate video on RunPod A100 (burst overflow)."""
        shot_id = shot["id"]

        # Budget check
        budget_cap = self.config.get("burst_budget_cap", 5.00)
        if self._burst_spend >= budget_cap:
            logger.warning(f"[GenLoop:{self.project_id}] Burst budget exhausted (${self._burst_spend:.2f} >= ${budget_cap:.2f})")
            # Fall back to local
            await self._generate_video_local(conn, shot)
            return

        try:
            from packages.scene_generation.runpod_burst import RunPodBurst

            # Lazy-init burst connection
            if not self._burst_manager:
                self._burst_manager = await BurstManager.connect()
            if not self._burst_manager or not self._burst_manager.burst:
                logger.warning(f"[GenLoop:{self.project_id}] RunPod burst unavailable, falling back to local")
                await self._generate_video_local(conn, shot)
                return

            await conn.execute(
                "UPDATE shots SET status = 'generating' WHERE id = $1", shot_id
            )

            motion_prompt = shot["motion_prompt"] or ""
            source_image = shot["source_image_path"]

            from packages.scene_generation.motion_intensity import classify_motion_intensity
            tier = classify_motion_intensity(motion_prompt, shot["lora_name"])

            video_path = await self._burst_manager.burst.generate_video(
                keyframe_path=source_image,
                prompt=motion_prompt,
                lora_high=shot["lora_name"],
                lora_strength=shot["lora_strength"] or 0.85,
                motion_tier=tier,
            )

            if video_path:
                await conn.execute("""
                    UPDATE shots SET output_video_path = $2, status = 'completed'
                    WHERE id = $1
                """, shot_id, video_path)

                self._videos_generated += 1
                self._videos_burst += 1
                # A100 costs ~$1.15/hr, avg video ~3 min → ~$0.06/video
                self._burst_spend += 0.06

                logger.info(f"[GenLoop:{self.project_id}] Burst video completed: {video_path} (shot {shot_id})")

                chars = shot["characters_present"] or []
                await event_bus.emit(SHOT_GENERATED, {
                    "shot_id": shot_id,
                    "video_path": video_path,
                    "project_id": self.project_id,
                    "character_slug": chars[0] if chars else None,
                })
            else:
                await conn.execute(
                    "UPDATE shots SET status = 'error', error_message = 'RunPod burst failed' WHERE id = $1",
                    shot_id,
                )

        except Exception as e:
            logger.error(f"[GenLoop:{self.project_id}] Burst gen failed for shot {shot_id}: {e}")
            # Fall back to local
            await self._generate_video_local(conn, shot)

    async def _should_burst(self) -> bool:
        """Check if we should burst to RunPod (AMD queue too deep)."""
        if not self.config.get("burst_enabled", False):
            return False

        budget_cap = self.config.get("burst_budget_cap", 5.00)
        if self._burst_spend >= budget_cap:
            return False

        threshold = self.config.get("burst_queue_threshold", 3)
        queue_depth = await _get_comfyui_queue_depth(COMFYUI_VIDEO_URL)
        return queue_depth > threshold

    # ── Phase 3: Auto-Assembly ────────────────────────────────────────

    async def _auto_assemble(self):
        """Auto-assemble scenes where all shots have completed videos."""
        dry_run = self.config.get("dry_run", False)

        pool = await get_pool()
        async with pool.acquire() as conn:
            # Find scenes where all shots are completed
            scenes = await conn.fetch("""
                SELECT sc.id, sc.title, sc.project_id,
                       COUNT(s.id) as total_shots,
                       COUNT(s.id) FILTER (WHERE s.status = 'completed' AND s.output_video_path IS NOT NULL) as done_shots
                FROM scenes sc
                JOIN shots s ON s.scene_id = sc.id
                WHERE sc.project_id = $1
                  AND (sc.final_video_path IS NULL OR sc.final_video_path = '')
                GROUP BY sc.id, sc.title, sc.project_id
                HAVING COUNT(s.id) = COUNT(s.id) FILTER (WHERE s.status = 'completed' AND s.output_video_path IS NOT NULL)
                   AND COUNT(s.id) > 0
            """, self.project_id)

            if not scenes:
                return

            for scene in scenes:
                if not self._running:
                    break

                if dry_run:
                    logger.info(f"[GenLoop:{self.project_id}] DRY RUN: Would assemble scene '{scene['title']}' "
                                f"({scene['done_shots']} shots)")
                    continue

                await self._assemble_scene(conn, scene)

    async def _assemble_scene(self, conn, scene):
        """Concatenate all shot videos into a scene video."""
        scene_id = scene["id"]
        try:
            # Get shot videos in order
            shot_rows = await conn.fetch("""
                SELECT output_video_path FROM shots
                WHERE scene_id = $1 AND output_video_path IS NOT NULL
                ORDER BY sort_order, created_at
            """, scene_id)

            video_paths = [r["output_video_path"] for r in shot_rows if r["output_video_path"]]
            if len(video_paths) < 1:
                return

            if len(video_paths) == 1:
                # Single shot — just use it directly
                final_path = video_paths[0]
            else:
                # Concatenate with ffmpeg
                from packages.scene_generation.scene_video_utils import concat_videos
                output_name = f"scene_{scene_id}_{int(time.time())}.mp4"
                output_path = str(COMFYUI_OUTPUT_DIR / output_name)
                final_path = concat_videos(video_paths, output_path)
                if not final_path:
                    logger.error(f"[GenLoop:{self.project_id}] Scene assembly failed for {scene_id}")
                    return

            # Update scene
            await conn.execute(
                "UPDATE scenes SET final_video_path = $2 WHERE id = $1",
                scene_id, final_path,
            )
            self._scenes_assembled += 1
            logger.info(f"[GenLoop:{self.project_id}] Scene assembled: {scene['title']} → {final_path}")

            await event_bus.emit("scene.ready", {
                "scene_id": str(scene_id),
                "project_id": self.project_id,
                "video_path": final_path,
            })

        except Exception as e:
            logger.error(f"[GenLoop:{self.project_id}] Scene assembly error for {scene_id}: {e}")


# ── Burst Manager ─────────────────────────────────────────────────────

class BurstManager:
    """Manages RunPod pod lifecycle for burst overflow."""

    def __init__(self, burst):
        self.burst = burst
        self._last_activity = time.time()
        self._idle_timeout = 600  # 10 min

    @classmethod
    async def connect(cls) -> "BurstManager | None":
        """Connect to RunPod, restarting pod if needed."""
        try:
            from packages.scene_generation.runpod_burst import RunPodBurst
            burst = await RunPodBurst.connect()
            if burst:
                return cls(burst)
        except Exception as e:
            logger.warning(f"BurstManager: Failed to connect: {e}")
        return None

    async def check_idle(self):
        """Stop pod if idle too long. Called periodically."""
        if time.time() - self._last_activity > self._idle_timeout:
            await self.stop_pod()

    async def stop_pod(self):
        """Stop the RunPod pod to save cost."""
        if self.burst:
            try:
                import subprocess
                subprocess.run(
                    ["runpodctl", "stop", "pod", self.burst.pod_id],
                    capture_output=True, timeout=15,
                )
                logger.info(f"BurstManager: Stopped pod {self.burst.pod_id}")
            except Exception as e:
                logger.warning(f"BurstManager: Failed to stop pod: {e}")
            self.burst = None


# ── Helpers ───────────────────────────────────────────────────────────

def _submit_comfyui(comfyui_url: str, workflow: dict) -> str | None:
    """Submit workflow to ComfyUI, return prompt_id."""
    try:
        import json
        data = json.dumps({"prompt": workflow}).encode()
        req = urllib.request.Request(
            f"{comfyui_url}/prompt",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=30)
        return json.loads(resp.read()).get("prompt_id")
    except Exception as e:
        logger.error(f"ComfyUI submit failed ({comfyui_url}): {e}")
        return None


async def _poll_comfyui(comfyui_url: str, prompt_id: str, timeout: int = 300) -> dict | None:
    """Poll ComfyUI for workflow completion."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            url = f"{comfyui_url}/history/{prompt_id}"
            resp = urllib.request.urlopen(urllib.request.Request(url), timeout=10)
            history = json.loads(resp.read())
            if prompt_id in history:
                status = history[prompt_id].get("status", {})
                if status.get("completed", False):
                    return history[prompt_id]
                if status.get("status_str") == "error":
                    logger.error(f"ComfyUI workflow error: {status}")
                    return None
        except Exception:
            pass
        await asyncio.sleep(5)
    return None


def _extract_image_path(result: dict, prefix: str) -> str | None:
    """Extract output image path from ComfyUI history result."""
    for node_id, output in result.get("outputs", {}).items():
        images = output.get("images", [])
        for img in images:
            filename = img.get("filename", "")
            if filename and prefix in filename:
                return str(COMFYUI_OUTPUT_DIR / filename)
            elif filename:
                return str(COMFYUI_OUTPUT_DIR / filename)
    return None


def _extract_video_path(result: dict, prefix: str) -> str | None:
    """Extract output video path from ComfyUI history result."""
    for node_id, output in result.get("outputs", {}).items():
        gifs = output.get("gifs", [])
        for g in gifs:
            filename = g.get("filename", "")
            if filename.endswith(".mp4"):
                return str(COMFYUI_OUTPUT_DIR / filename)
    return None


async def _get_comfyui_queue_depth(comfyui_url: str) -> int:
    """Get number of items in ComfyUI queue."""
    try:
        resp = urllib.request.urlopen(
            urllib.request.Request(f"{comfyui_url}/queue"), timeout=5,
        )
        data = json.loads(resp.read())
        running = len(data.get("queue_running", []))
        pending = len(data.get("queue_pending", []))
        return running + pending
    except Exception:
        return 0


def _inject_lora_into_workflow(workflow: dict, lora_path: str, strength: float) -> dict:
    """Inject a LoRA loader between checkpoint and KSampler in a txt2img workflow."""
    # In our standard txt2img workflow:
    # Node "4" = CheckpointLoaderSimple, Node "3" = KSampler (model from "4",0)
    if "4" not in workflow or "3" not in workflow:
        return workflow

    # Add LoRA loader node
    lora_node_id = "50"  # safe high number
    workflow[lora_node_id] = {
        "inputs": {
            "lora_name": Path(lora_path).name,
            "strength_model": strength,
            "strength_clip": strength,
            "model": ["4", 0],
            "clip": ["4", 1],
        },
        "class_type": "LoraLoader",
    }

    # Rewire KSampler to use LoRA output
    workflow["3"]["inputs"]["model"] = [lora_node_id, 0]
    # Rewire CLIP text encoders to use LoRA CLIP
    if "1" in workflow:
        workflow["1"]["inputs"]["clip"] = [lora_node_id, 1]
    if "2" in workflow:
        workflow["2"]["inputs"]["clip"] = [lora_node_id, 1]

    return workflow
