"""
Anime Production Integration
Integration with Tower Anime Production System for scene generation
"""

import asyncio
import aiohttp
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
import json

logger = logging.getLogger(__name__)

class AnimeProductionIntegration:
    """Integration with Tower Anime Production System for video generation"""

    def __init__(self, base_url: str = "http://localhost:8328"):
        self.base_url = base_url.rstrip('/')
        self.session = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def _get_session(self):
        """Get or create aiohttp session"""
        if not self.session or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def health_check(self) -> bool:
        """Check if Anime Production system is accessible"""
        try:
            session = await self._get_session()
            async with session.get(f"{self.base_url}/api/health") as response:
                return response.status == 200
        except Exception as e:
            logger.error(f"Anime Production health check failed: {e}")
            return False

    async def export_scene_descriptions(
        self,
        scene_ids: List[int],
        project_id: Optional[int] = None,
        export_options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Export scene descriptions to anime production system"""
        try:
            session = await self._get_session()

            # If no project specified, create a new one
            if not project_id:
                project_id = await self._create_anime_project(export_options or {})

            # Prepare export data
            export_data = {
                "project_id": project_id,
                "scene_ids": scene_ids,
                "export_type": "scene_descriptions",
                "options": export_options or {},
                "timestamp": datetime.utcnow().isoformat(),
                "source": "scene_description_generator"
            }

            async with session.post(
                f"{self.base_url}/api/anime/projects/{project_id}/import_scenes",
                json=export_data,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    return await self._process_export_result(result, scene_ids, project_id)
                else:
                    error_text = await response.text()
                    logger.error(f"Scene export failed: {response.status} - {error_text}")
                    return {
                        "success": False,
                        "error": f"Export failed: {error_text}",
                        "project_id": project_id
                    }

        except Exception as e:
            logger.error(f"Scene export error: {e}")
            return {
                "success": False,
                "error": str(e),
                "project_id": project_id
            }

    async def _create_anime_project(self, export_options: Dict[str, Any]) -> int:
        """Create a new anime project for scene export"""
        try:
            session = await self._get_session()

            project_data = {
                "name": export_options.get("project_name", f"Scene Export {datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"),
                "description": export_options.get("project_description", "Auto-generated project from scene descriptions"),
                "type": "scene_description_export",
                "settings": {
                    "resolution": export_options.get("resolution", "1920x1080"),
                    "frame_rate": export_options.get("frame_rate", 24),
                    "aspect_ratio": export_options.get("aspect_ratio", "16:9"),
                    "quality": export_options.get("quality", "high")
                },
                "created_by": "scene_description_generator"
            }

            async with session.post(
                f"{self.base_url}/api/anime/projects",
                json=project_data,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    return result.get("id", 1)  # Default to 1 if ID not returned
                else:
                    logger.warning("Failed to create anime project, using default ID")
                    return 1

        except Exception as e:
            logger.error(f"Project creation failed: {e}")
            return 1  # Default project ID

    async def _process_export_result(
        self,
        result: Dict[str, Any],
        scene_ids: List[int],
        project_id: int
    ) -> Dict[str, Any]:
        """Process the export result from anime production system"""

        return {
            "success": True,
            "project_id": project_id,
            "scenes_exported": len(scene_ids),
            "export_status": result.get("status", "queued"),
            "generation_queue_id": result.get("queue_id"),
            "estimated_completion": result.get("estimated_completion"),
            "summary": {
                "total_scenes": len(scene_ids),
                "project_type": "scene_description_export",
                "export_timestamp": datetime.utcnow().isoformat()
            }
        }

    async def convert_scene_to_generation_prompt(
        self,
        scene_description: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Convert scene description to anime generation prompt"""

        # Extract key elements for anime generation
        visual_description = scene_description.get("visual_description", "")
        cinematography_notes = scene_description.get("cinematography_notes", "")
        atmosphere_description = scene_description.get("atmosphere_description", "")
        technical_specs = scene_description.get("technical_specifications", {})

        # Create comprehensive generation prompt
        generation_prompt = await self._build_generation_prompt(
            visual_description, cinematography_notes, atmosphere_description, technical_specs
        )

        # Add technical parameters
        generation_parameters = await self._build_generation_parameters(technical_specs)

        return {
            "prompt": generation_prompt,
            "parameters": generation_parameters,
            "scene_metadata": {
                "source": "scene_description_generator",
                "conversion_timestamp": datetime.utcnow().isoformat()
            }
        }

    async def _build_generation_prompt(
        self,
        visual_description: str,
        cinematography_notes: str,
        atmosphere_description: str,
        technical_specs: Dict[str, Any]
    ) -> str:
        """Build comprehensive generation prompt"""

        prompt_parts = []

        # Start with visual description
        if visual_description:
            prompt_parts.append(f"Visual composition: {visual_description}")

        # Add cinematography elements
        if cinematography_notes:
            prompt_parts.append(f"Camera work: {cinematography_notes}")

        # Add atmospheric elements
        if atmosphere_description:
            prompt_parts.append(f"Atmosphere: {atmosphere_description}")

        # Add technical specifications
        if technical_specs:
            camera_angle = technical_specs.get("camera_angle", "medium_shot")
            camera_movement = technical_specs.get("camera_movement", "static")
            lighting_type = technical_specs.get("lighting_type", "natural")

            prompt_parts.append(f"Camera angle: {camera_angle}")
            prompt_parts.append(f"Camera movement: {camera_movement}")
            prompt_parts.append(f"Lighting: {lighting_type}")

        # Combine into single prompt
        full_prompt = ". ".join(prompt_parts)

        # Add anime-specific enhancement
        anime_enhanced_prompt = f"Professional anime scene: {full_prompt}. High quality, detailed animation, studio production quality."

        return anime_enhanced_prompt

    async def _build_generation_parameters(
        self,
        technical_specs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build generation parameters from technical specifications"""

        return {
            "resolution": technical_specs.get("resolution", "1920x1080"),
            "aspect_ratio": technical_specs.get("aspect_ratio", "16:9"),
            "frame_rate": technical_specs.get("frame_rate", 24),
            "duration_seconds": technical_specs.get("duration_seconds", 5.0),
            "quality": "high",
            "style": "anime",
            "model": "animatediff_evolved",
            "guidance_scale": 7.5,
            "num_inference_steps": 20,
            "seed": -1  # Random seed
        }

    async def trigger_scene_generation(
        self,
        scene_description: Dict[str, Any],
        project_id: int
    ) -> Dict[str, Any]:
        """Trigger anime generation for a specific scene"""
        try:
            session = await self._get_session()

            # Convert scene to generation format
            generation_data = await self.convert_scene_to_generation_prompt(scene_description)

            # Add project context
            generation_request = {
                "project_id": project_id,
                "prompt": generation_data["prompt"],
                "parameters": generation_data["parameters"],
                "scene_metadata": generation_data["scene_metadata"],
                "priority": "normal"
            }

            async with session.post(
                f"{self.base_url}/api/anime/generate",
                json=generation_request,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    return {
                        "success": True,
                        "generation_id": result.get("generation_id"),
                        "queue_position": result.get("queue_position"),
                        "estimated_completion": result.get("estimated_completion"),
                        "status": "queued"
                    }
                else:
                    error_text = await response.text()
                    return {
                        "success": False,
                        "error": f"Generation trigger failed: {error_text}"
                    }

        except Exception as e:
            logger.error(f"Scene generation trigger failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def get_generation_status(
        self,
        generation_id: str
    ) -> Dict[str, Any]:
        """Get status of anime generation"""
        try:
            session = await self._get_session()

            async with session.get(
                f"{self.base_url}/api/anime/generate/{generation_id}/status"
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    return {
                        "status": "unknown",
                        "error": "Could not retrieve generation status"
                    }

        except Exception as e:
            logger.error(f"Generation status check failed: {e}")
            return {
                "status": "error",
                "error": str(e)
            }

    async def batch_export_scenes(
        self,
        scenes_data: List[Dict[str, Any]],
        export_options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Export multiple scenes in batch"""
        try:
            # Create project for batch
            project_id = await self._create_anime_project(export_options or {})

            batch_results = []
            successful_exports = 0
            failed_exports = 0

            for i, scene_data in enumerate(scenes_data):
                try:
                    # Convert scene to generation format
                    generation_data = await self.convert_scene_to_generation_prompt(scene_data)

                    # Trigger generation
                    generation_result = await self.trigger_scene_generation(scene_data, project_id)

                    if generation_result.get("success"):
                        successful_exports += 1
                        batch_results.append({
                            "scene_index": i,
                            "status": "success",
                            "generation_id": generation_result.get("generation_id")
                        })
                    else:
                        failed_exports += 1
                        batch_results.append({
                            "scene_index": i,
                            "status": "failed",
                            "error": generation_result.get("error")
                        })

                except Exception as e:
                    failed_exports += 1
                    batch_results.append({
                        "scene_index": i,
                        "status": "error",
                        "error": str(e)
                    })

            return {
                "success": True,
                "project_id": project_id,
                "batch_summary": {
                    "total_scenes": len(scenes_data),
                    "successful_exports": successful_exports,
                    "failed_exports": failed_exports,
                    "success_rate": successful_exports / len(scenes_data) if scenes_data else 0
                },
                "individual_results": batch_results
            }

        except Exception as e:
            logger.error(f"Batch export failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def validate_scene_for_generation(
        self,
        scene_description: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate scene description for anime generation compatibility"""

        validation_results = {
            "valid": True,
            "issues": [],
            "warnings": [],
            "requirements_met": {}
        }

        # Check required fields
        required_fields = ["visual_description", "technical_specifications"]
        for field in required_fields:
            if field not in scene_description or not scene_description[field]:
                validation_results["valid"] = False
                validation_results["issues"].append(f"Missing required field: {field}")
                validation_results["requirements_met"][field] = False
            else:
                validation_results["requirements_met"][field] = True

        # Check technical specifications
        tech_specs = scene_description.get("technical_specifications", {})
        if isinstance(tech_specs, dict):
            # Check resolution
            resolution = tech_specs.get("resolution", "1920x1080")
            if not self._validate_resolution(resolution):
                validation_results["warnings"].append(f"Non-standard resolution: {resolution}")

            # Check frame rate
            frame_rate = tech_specs.get("frame_rate", 24)
            if frame_rate not in [24, 30, 60]:
                validation_results["warnings"].append(f"Non-standard frame rate: {frame_rate}")

            # Check duration
            duration = tech_specs.get("duration_seconds")
            if duration and (duration < 1 or duration > 30):
                validation_results["warnings"].append(f"Duration outside recommended range: {duration}s")

        # Check visual description quality
        visual_desc = scene_description.get("visual_description", "")
        if len(visual_desc) < 20:
            validation_results["warnings"].append("Visual description is very brief")

        return validation_results

    def _validate_resolution(self, resolution: str) -> bool:
        """Validate resolution format"""
        try:
            width, height = resolution.split('x')
            width_int = int(width)
            height_int = int(height)
            return width_int > 0 and height_int > 0
        except:
            return False

    async def get_project_status(self, project_id: int) -> Dict[str, Any]:
        """Get status of anime project"""
        try:
            session = await self._get_session()

            async with session.get(
                f"{self.base_url}/api/anime/projects/{project_id}"
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    return {
                        "status": "unknown",
                        "error": "Could not retrieve project status"
                    }

        except Exception as e:
            logger.error(f"Project status check failed: {e}")
            return {
                "status": "error",
                "error": str(e)
            }

    async def list_available_models(self) -> List[str]:
        """List available anime generation models"""
        try:
            session = await self._get_session()

            async with session.get(
                f"{self.base_url}/api/anime/models"
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    return result.get("models", ["animatediff_evolved"])
                else:
                    return ["animatediff_evolved"]  # Default model

        except Exception as e:
            logger.error(f"Model listing failed: {e}")
            return ["animatediff_evolved"]  # Default model

    async def optimize_scene_for_generation(
        self,
        scene_description: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Optimize scene description for better generation results"""

        optimized = scene_description.copy()

        # Optimize visual description
        visual_desc = scene_description.get("visual_description", "")
        if visual_desc:
            optimized["visual_description"] = await self._optimize_visual_description(visual_desc)

        # Optimize technical specifications
        tech_specs = scene_description.get("technical_specifications", {})
        if tech_specs:
            optimized["technical_specifications"] = await self._optimize_technical_specs(tech_specs)

        # Add generation-specific enhancements
        optimized["generation_optimizations"] = {
            "prompt_enhancement": "Applied anime-specific prompt optimization",
            "technical_optimization": "Optimized technical parameters for generation",
            "quality_enhancement": "Enhanced for professional anime production"
        }

        return optimized

    async def _optimize_visual_description(self, visual_desc: str) -> str:
        """Optimize visual description for anime generation"""

        # Add anime-specific keywords and enhancement
        anime_keywords = [
            "high quality", "detailed", "professional anime", "studio quality",
            "crisp", "vibrant", "well-lit", "sharp focus"
        ]

        # Check if description already contains optimization keywords
        desc_lower = visual_desc.lower()
        missing_keywords = [kw for kw in anime_keywords if kw not in desc_lower]

        if missing_keywords:
            optimization = ", ".join(missing_keywords[:3])  # Add top 3 missing keywords
            return f"{visual_desc}. {optimization}."
        else:
            return visual_desc

    async def _optimize_technical_specs(self, tech_specs: Dict[str, Any]) -> Dict[str, Any]:
        """Optimize technical specifications for generation"""

        optimized_specs = tech_specs.copy()

        # Set optimal defaults
        if "resolution" not in optimized_specs:
            optimized_specs["resolution"] = "1920x1080"

        if "frame_rate" not in optimized_specs:
            optimized_specs["frame_rate"] = 24

        if "duration_seconds" not in optimized_specs:
            optimized_specs["duration_seconds"] = 5.0

        # Ensure compatibility
        if optimized_specs.get("duration_seconds", 0) > 10:
            optimized_specs["duration_seconds"] = 10.0  # Cap at 10 seconds

        return optimized_specs