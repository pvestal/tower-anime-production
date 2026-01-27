"""
Episode compilation service for Tower Anime Production API
Handles scene stitching, transitions, and episode assembly
"""

import os
import logging
import asyncio
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from ..models import Scene, Episode, AnimeProject
# Import services lazily to avoid circular imports

logger = logging.getLogger(__name__)


class EpisodeCompilerService:
    """Service for compiling scenes into complete episodes"""

    def __init__(self):
        # Import services lazily to avoid circular imports
        from .video_generation import video_generation_service
        from .audio_manager import audio_manager_service
        self.video_service = video_generation_service
        self.audio_service = audio_manager_service

    async def compile_episode_from_scenes(
        self,
        episode_id: int,
        db: Session,
        include_transitions: bool = True,
        background_music: bool = True
    ) -> Dict[str, Any]:
        """
        Compile scenes into a complete episode with transitions and audio
        """
        try:
            # Get episode and associated scenes
            episode = db.query(Episode).filter(Episode.id == episode_id).first()
            if not episode:
                raise ValueError(f"Episode {episode_id} not found")

            scenes = db.query(Scene).filter(
                Scene.episode_id == episode_id
            ).order_by(Scene.order_index).all()

            if not scenes:
                raise ValueError(f"No scenes found for episode {episode_id}")

            logger.info(f"Compiling episode '{episode.name}' with {len(scenes)} scenes")

            # Process each scene
            scene_outputs = []
            total_duration = 0

            for scene in scenes:
                scene_result = await self._process_scene(scene, db)
                scene_outputs.append(scene_result)
                total_duration += scene_result.get("duration", 3.0)

            # Add transitions if requested
            if include_transitions:
                scene_outputs = await self._add_transitions(scene_outputs)

            # Stitch scenes together
            final_video_path = await self._stitch_scenes(
                scene_outputs,
                episode.name,
                episode_id
            )

            # Add background music if requested
            if background_music:
                final_video_path = await self.audio_service.add_background_music(
                    final_video_path,
                    duration=total_duration,
                    mood="anime_dramatic"
                )

            # Update episode status
            episode.status = "completed"
            episode.duration = total_duration
            episode.episode_data = episode.episode_data or {}
            episode.episode_data.update({
                "scenes_count": len(scenes),
                "compilation_timestamp": int(asyncio.get_event_loop().time()),
                "final_video_path": final_video_path,
                "includes_transitions": include_transitions,
                "includes_background_music": background_music
            })
            db.commit()

            return {
                "episode_id": episode_id,
                "episode_name": episode.name,
                "total_duration": total_duration,
                "scenes_count": len(scenes),
                "output_path": final_video_path,
                "compilation_successful": True
            }

        except Exception as e:
            logger.error(f"Episode compilation failed: {e}")
            # Update episode status to failed
            episode = db.query(Episode).filter(Episode.id == episode_id).first()
            if episode:
                episode.status = "failed"
                episode.episode_data = episode.episode_data or {}
                episode.episode_data.update({
                    "compilation_error": str(e),
                    "compilation_timestamp": int(asyncio.get_event_loop().time())
                })
                db.commit()
            raise

    async def _process_scene(self, scene: Scene, db: Session) -> Dict[str, Any]:
        """Process individual scene for video generation"""
        try:
            logger.info(f"Processing scene '{scene.name}' (ID: {scene.id})")

            # Check if scene already has generated video
            if scene.scene_data and scene.scene_data.get("video_path"):
                return {
                    "scene_id": scene.id,
                    "name": scene.name,
                    "video_path": scene.scene_data["video_path"],
                    "duration": scene.duration or 3.0,
                    "type": scene.scene_type
                }

            # Generate video for scene
            prompt = self._build_scene_prompt(scene)
            generation_result = await self.video_service.generate_video_with_animatediff(
                prompt=prompt,
                frame_count=int((scene.duration or 3.0) * 8)  # 8 FPS
            )

            # Update scene with generated video path
            scene.scene_data = scene.scene_data or {}
            scene.scene_data.update({
                "video_path": generation_result["output_path"],
                "generation_timestamp": int(asyncio.get_event_loop().time()),
                "prompt_used": prompt
            })
            scene.status = "completed"
            db.commit()

            return {
                "scene_id": scene.id,
                "name": scene.name,
                "video_path": generation_result["output_path"],
                "duration": scene.duration or 3.0,
                "type": scene.scene_type,
                "prompt_id": generation_result.get("prompt_id")
            }

        except Exception as e:
            logger.error(f"Scene processing failed for scene {scene.id}: {e}")
            scene.status = "failed"
            scene.scene_data = scene.scene_data or {}
            scene.scene_data["error"] = str(e)
            db.commit()
            raise

    def _build_scene_prompt(self, scene: Scene) -> str:
        """Build generation prompt from scene data"""
        base_prompt = scene.description or scene.name

        # Add scene type context
        if scene.scene_type == "dialogue":
            base_prompt += ", characters talking, dialogue scene"
        elif scene.scene_type == "action":
            base_prompt += ", dynamic action scene, movement"
        elif scene.scene_type == "transition":
            base_prompt += ", scene transition, cinematic"

        # Add any character information from scene data
        if scene.scene_data and scene.scene_data.get("characters"):
            characters = ", ".join(scene.scene_data["characters"])
            base_prompt += f", featuring {characters}"

        # Add location if specified
        if scene.scene_data and scene.scene_data.get("location"):
            base_prompt += f", in {scene.scene_data['location']}"

        return base_prompt

    async def _add_transitions(self, scene_outputs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Add transition scenes between main scenes"""
        enhanced_scenes = []

        for i, scene in enumerate(scene_outputs):
            enhanced_scenes.append(scene)

            # Add transition after each scene (except the last one)
            if i < len(scene_outputs) - 1:
                next_scene = scene_outputs[i + 1]
                transition = await self._generate_transition(scene, next_scene)
                enhanced_scenes.append(transition)

        return enhanced_scenes

    async def _generate_transition(
        self,
        from_scene: Dict[str, Any],
        to_scene: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate a transition scene between two main scenes"""
        try:
            # Build transition prompt based on scene types
            transition_prompt = self._build_transition_prompt(from_scene, to_scene)

            generation_result = await self.video_service.generate_video_with_animatediff(
                prompt=transition_prompt,
                frame_count=8  # Short transition - 1 second at 8fps
            )

            return {
                "scene_id": f"transition_{from_scene['scene_id']}_to_{to_scene['scene_id']}",
                "name": f"Transition from {from_scene['name']} to {to_scene['name']}",
                "video_path": generation_result["output_path"],
                "duration": 1.0,
                "type": "transition",
                "prompt_id": generation_result.get("prompt_id")
            }

        except Exception as e:
            logger.error(f"Transition generation failed: {e}")
            # Return a simple fade transition fallback
            return {
                "scene_id": f"transition_{from_scene['scene_id']}_to_{to_scene['scene_id']}",
                "name": "Fade Transition",
                "video_path": None,  # Will be handled in stitching
                "duration": 0.5,
                "type": "fade_transition"
            }

    def _build_transition_prompt(
        self,
        from_scene: Dict[str, Any],
        to_scene: Dict[str, Any]
    ) -> str:
        """Build transition prompt based on scene context"""
        from_type = from_scene.get("type", "unknown")
        to_type = to_scene.get("type", "unknown")

        if from_type == "dialogue" and to_type == "action":
            return "cinematic transition, camera movement, anime style, smooth transition from close-up to wide shot"
        elif from_type == "action" and to_type == "dialogue":
            return "cinematic transition, camera zoom in, anime style, smooth transition from wide shot to close-up"
        else:
            return "smooth cinematic transition, anime style, flowing movement, seamless scene change"

    async def _stitch_scenes(
        self,
        scene_outputs: List[Dict[str, Any]],
        episode_name: str,
        episode_id: int
    ) -> str:
        """Stitch all scene videos together into final episode"""
        try:
            # This would integrate with FFmpeg or similar video processing
            # For now, return a placeholder path
            timestamp = int(asyncio.get_event_loop().time())
            output_path = f"/mnt/1TB-storage/ComfyUI/output/episode_{episode_id}_{timestamp}.mp4"

            logger.info(f"Stitching {len(scene_outputs)} scenes into episode: {output_path}")

            # TODO: Implement actual video stitching logic
            # - Use FFmpeg to concatenate videos
            # - Handle fade transitions for None video_paths
            # - Ensure proper frame rates and dimensions
            # - Add chapter markers for scenes

            return output_path

        except Exception as e:
            logger.error(f"Video stitching failed: {e}")
            raise

    async def get_episode_compilation_status(self, episode_id: int, db: Session) -> Dict[str, Any]:
        """Get compilation status for an episode"""
        episode = db.query(Episode).filter(Episode.id == episode_id).first()
        if not episode:
            raise ValueError(f"Episode {episode_id} not found")

        scenes = db.query(Scene).filter(Scene.episode_id == episode_id).all()
        completed_scenes = [s for s in scenes if s.status == "completed"]

        return {
            "episode_id": episode_id,
            "episode_name": episode.name,
            "status": episode.status,
            "total_scenes": len(scenes),
            "completed_scenes": len(completed_scenes),
            "progress": len(completed_scenes) / len(scenes) if scenes else 0,
            "episode_data": episode.episode_data
        }


# Global service instance
episode_compiler_service = EpisodeCompilerService()