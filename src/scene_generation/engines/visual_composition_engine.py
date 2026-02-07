"""
Visual Composition Engine
Professional visual scene composition for anime production
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import random
import json

logger = logging.getLogger(__name__)

class VisualCompositionEngine:
    """Engine for generating professional visual compositions"""

    def __init__(self):
        self.composition_templates = self._load_composition_templates()
        self.color_palettes = self._load_color_palettes()
        self.framing_rules = self._load_framing_rules()

    def _load_composition_templates(self) -> Dict[str, Any]:
        """Load professional composition templates"""
        return {
            "rule_of_thirds": {
                "description": "Classic rule of thirds composition",
                "focal_points": ["upper_left", "upper_right", "lower_left", "lower_right"],
                "character_placement": "intersection_points",
                "visual_weight": "balanced"
            },
            "golden_ratio": {
                "description": "Golden ratio spiral composition",
                "focal_points": ["spiral_center"],
                "character_placement": "spiral_path",
                "visual_weight": "dynamic"
            },
            "central_symmetry": {
                "description": "Symmetrical central composition",
                "focal_points": ["center"],
                "character_placement": "centered",
                "visual_weight": "stable"
            },
            "diagonal_dynamic": {
                "description": "Dynamic diagonal composition",
                "focal_points": ["diagonal_line"],
                "character_placement": "diagonal_path",
                "visual_weight": "energetic"
            },
            "depth_layering": {
                "description": "Multiple depth layers",
                "focal_points": ["foreground", "midground", "background"],
                "character_placement": "layered",
                "visual_weight": "dimensional"
            }
        }

    def _load_color_palettes(self) -> Dict[str, List[str]]:
        """Load color palettes for different moods and times"""
        return {
            "dawn": ["#FFD700", "#FF6B35", "#4A90E2", "#8A2BE2", "#FF1493"],
            "morning": ["#87CEEB", "#FFD700", "#32CD32", "#FF6347", "#4169E1"],
            "midday": ["#00BFFF", "#FFFF00", "#32CD32", "#FF6347", "#FF1493"],
            "afternoon": ["#FFA500", "#FF6347", "#4169E1", "#32CD32", "#8B4513"],
            "evening": ["#FF4500", "#8B0000", "#4B0082", "#2F4F4F", "#FFD700"],
            "dusk": ["#8B0000", "#4B0082", "#2F4F4F", "#FF6347", "#FFD700"],
            "night": ["#191970", "#2F4F4F", "#4B0082", "#8B0000", "#FFFFFF"],
            "midnight": ["#000000", "#191970", "#2F4F4F", "#8B0000", "#FFFFFF"],

            # Mood-based palettes
            "dramatic": ["#8B0000", "#000000", "#4B0082", "#2F4F4F", "#FFFFFF"],
            "romantic": ["#FF69B4", "#FF1493", "#8B0000", "#FFD700", "#FFFFFF"],
            "peaceful": ["#87CEEB", "#32CD32", "#F0E68C", "#DDA0DD", "#FFFFFF"],
            "mysterious": ["#2F4F4F", "#4B0082", "#8B0000", "#000000", "#C0C0C0"],
            "energetic": ["#FF6347", "#FFD700", "#32CD32", "#00BFFF", "#FF1493"]
        }

    def _load_framing_rules(self) -> Dict[str, Dict[str, Any]]:
        """Load framing rules for different shot types"""
        return {
            "wide_shot": {
                "character_size": "small",
                "environment_prominence": "high",
                "detail_level": "overview",
                "emotional_distance": "objective"
            },
            "medium_shot": {
                "character_size": "waist_up",
                "environment_prominence": "medium",
                "detail_level": "balanced",
                "emotional_distance": "engaged"
            },
            "close_up": {
                "character_size": "head_shoulders",
                "environment_prominence": "low",
                "detail_level": "intimate",
                "emotional_distance": "personal"
            },
            "extreme_close_up": {
                "character_size": "face_detail",
                "environment_prominence": "minimal",
                "detail_level": "intense",
                "emotional_distance": "intimate"
            },
            "establishing_shot": {
                "character_size": "tiny_or_absent",
                "environment_prominence": "maximum",
                "detail_level": "contextual",
                "emotional_distance": "informative"
            }
        }

    async def generate_visual_composition(
        self,
        scene_data: Dict[str, Any],
        style_preferences: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Generate comprehensive visual composition"""
        try:
            # Analyze scene requirements
            composition_type = await self._select_composition_type(scene_data)
            camera_angle = await self._determine_camera_angle(scene_data)
            color_palette = await self._select_color_palette(scene_data)
            lighting_setup = await self._design_lighting(scene_data)

            # Character positioning
            character_layout = await self._position_characters(
                scene_data.get("characters", []),
                composition_type,
                camera_angle
            )

            # Environment design
            environment_design = await self._design_environment(scene_data)

            # Generate detailed description
            visual_description = await self._generate_visual_description(
                composition_type=composition_type,
                camera_angle=camera_angle,
                color_palette=color_palette,
                lighting_setup=lighting_setup,
                character_layout=character_layout,
                environment_design=environment_design,
                scene_data=scene_data
            )

            return {
                "composition_type": composition_type,
                "camera_angle": camera_angle,
                "color_palette": color_palette,
                "lighting_setup": lighting_setup,
                "character_layout": character_layout,
                "environment_design": environment_design,
                "visual_description": visual_description,
                "technical_notes": await self._generate_technical_notes(
                    composition_type, camera_angle, lighting_setup
                )
            }

        except Exception as e:
            logger.error(f"Visual composition generation failed: {e}")
            raise

    async def _select_composition_type(self, scene_data: Dict[str, Any]) -> str:
        """Select appropriate composition type based on scene"""
        mood = scene_data.get("mood", "peaceful")
        character_count = len(scene_data.get("characters", []))
        action_type = scene_data.get("action_summary", "").lower()

        # Rule-based composition selection
        if "contemplat" in action_type or mood == "peaceful":
            return "rule_of_thirds"
        elif "action" in action_type or mood == "energetic":
            return "diagonal_dynamic"
        elif character_count == 1 and "dramatic" in mood:
            return "central_symmetry"
        elif "mysterious" in mood:
            return "golden_ratio"
        else:
            return "depth_layering"

    async def _determine_camera_angle(self, scene_data: Dict[str, Any]) -> str:
        """Determine optimal camera angle"""
        character_count = len(scene_data.get("characters", []))
        mood = scene_data.get("mood", "peaceful")
        action_summary = scene_data.get("action_summary", "").lower()

        if character_count == 0:
            return "establishing_shot"
        elif character_count == 1:
            if "contemplat" in action_summary:
                return "medium_shot"
            elif "dramatic" in mood:
                return "close_up"
            else:
                return "medium_shot"
        elif character_count == 2:
            return "medium_shot"  # Two-shot or over-shoulder
        else:
            return "wide_shot"

    async def _select_color_palette(self, scene_data: Dict[str, Any]) -> List[str]:
        """Select color palette based on time and mood"""
        time_of_day = scene_data.get("time_of_day", "midday")
        mood = scene_data.get("mood", "peaceful")

        # Primary palette from time of day
        time_palette = self.color_palettes.get(time_of_day, self.color_palettes["midday"])

        # Secondary palette from mood
        mood_palette = self.color_palettes.get(mood, [])

        # Combine and balance palettes
        combined_palette = time_palette[:3] + mood_palette[:2]
        return combined_palette[:5]  # Limit to 5 colors

    async def _design_lighting(self, scene_data: Dict[str, Any]) -> Dict[str, Any]:
        """Design lighting setup for the scene"""
        time_of_day = scene_data.get("time_of_day", "midday")
        mood = scene_data.get("mood", "peaceful")
        location = scene_data.get("location", "").lower()

        lighting_setups = {
            "dawn": {
                "primary": "soft_golden",
                "direction": "low_horizon",
                "intensity": "gentle",
                "shadows": "long_soft"
            },
            "morning": {
                "primary": "bright_natural",
                "direction": "slight_angle",
                "intensity": "moderate",
                "shadows": "defined"
            },
            "midday": {
                "primary": "harsh_overhead",
                "direction": "top_down",
                "intensity": "strong",
                "shadows": "sharp_short"
            },
            "evening": {
                "primary": "warm_angled",
                "direction": "low_side",
                "intensity": "moderate",
                "shadows": "dramatic"
            },
            "night": {
                "primary": "artificial_point",
                "direction": "varied",
                "intensity": "selective",
                "shadows": "deep_contrast"
            }
        }

        base_lighting = lighting_setups.get(time_of_day, lighting_setups["midday"])

        # Modify based on mood
        if mood == "dramatic":
            base_lighting["contrast"] = "high"
            base_lighting["shadows"] = "deep_dramatic"
        elif mood == "romantic":
            base_lighting["warmth"] = "increased"
            base_lighting["softness"] = "enhanced"
        elif mood == "mysterious":
            base_lighting["shadows"] = "obscuring"
            base_lighting["selective_illumination"] = True

        return base_lighting

    async def _position_characters(
        self,
        characters: List[str],
        composition_type: str,
        camera_angle: str
    ) -> Dict[str, Any]:
        """Position characters according to composition rules"""
        composition = self.composition_templates[composition_type]
        framing = self.framing_rules[camera_angle]

        character_positions = {}

        if len(characters) == 1:
            character_positions[characters[0]] = {
                "position": "center_focus",
                "size": framing["character_size"],
                "prominence": "primary"
            }
        elif len(characters) == 2:
            character_positions[characters[0]] = {
                "position": "left_focus",
                "size": framing["character_size"],
                "prominence": "primary"
            }
            character_positions[characters[1]] = {
                "position": "right_balance",
                "size": framing["character_size"],
                "prominence": "secondary"
            }
        else:
            # Multiple characters - distribute according to composition
            focal_points = composition["focal_points"]
            for i, character in enumerate(characters[:len(focal_points)]):
                character_positions[character] = {
                    "position": focal_points[i],
                    "size": framing["character_size"],
                    "prominence": "primary" if i == 0 else "secondary"
                }

        return {
            "layout": character_positions,
            "composition_rule": composition_type,
            "depth_arrangement": await self._arrange_depth(characters)
        }

    async def _arrange_depth(self, characters: List[str]) -> Dict[str, str]:
        """Arrange characters in depth layers"""
        if len(characters) <= 1:
            return {characters[0]: "midground"} if characters else {}
        elif len(characters) == 2:
            return {
                characters[0]: "midground",
                characters[1]: "midground"
            }
        else:
            return {
                characters[0]: "foreground",
                characters[1]: "midground",
                **{char: "background" for char in characters[2:]}
            }

    async def _design_environment(self, scene_data: Dict[str, Any]) -> Dict[str, Any]:
        """Design environment elements"""
        location = scene_data.get("location", "")
        time_of_day = scene_data.get("time_of_day", "midday")
        mood = scene_data.get("mood", "peaceful")

        environment_elements = {
            "primary_setting": location,
            "atmospheric_elements": [],
            "background_details": [],
            "environmental_mood": mood
        }

        # Add atmospheric elements based on time
        time_atmosphere = {
            "dawn": ["morning_mist", "soft_light_rays", "dew_drops"],
            "morning": ["clear_air", "bright_colors", "active_wildlife"],
            "midday": ["sharp_shadows", "bright_highlights", "clear_visibility"],
            "evening": ["warm_glow", "lengthening_shadows", "golden_light"],
            "night": ["darkness", "selective_lighting", "mysterious_shadows"]
        }

        environment_elements["atmospheric_elements"] = time_atmosphere.get(
            time_of_day, ["natural_lighting"]
        )

        # Add mood-specific details
        mood_details = {
            "dramatic": ["stark_contrasts", "dramatic_angles", "imposing_structures"],
            "peaceful": ["gentle_curves", "natural_harmony", "soft_textures"],
            "mysterious": ["hidden_areas", "obscured_details", "intriguing_shadows"],
            "energetic": ["dynamic_lines", "vibrant_colors", "movement_suggestion"]
        }

        environment_elements["background_details"] = mood_details.get(
            mood, ["neutral_background"]
        )

        return environment_elements

    async def _generate_visual_description(
        self,
        composition_type: str,
        camera_angle: str,
        color_palette: List[str],
        lighting_setup: Dict[str, Any],
        character_layout: Dict[str, Any],
        environment_design: Dict[str, Any],
        scene_data: Dict[str, Any]
    ) -> str:
        """Generate comprehensive visual description"""

        description_parts = []

        # Camera angle and framing
        angle_descriptions = {
            "wide_shot": "Sweeping wide shot establishing the full environment",
            "medium_shot": "Medium shot focusing on character interaction and immediate surroundings",
            "close_up": "Intimate close-up capturing emotional nuance and detail",
            "extreme_close_up": "Extreme close-up revealing critical emotional or narrative details",
            "establishing_shot": "Establishing shot providing full contextual overview"
        }

        description_parts.append(angle_descriptions.get(camera_angle, "Professional camera composition"))

        # Environment description
        env_desc = f"Set in {environment_design['primary_setting']}"
        if environment_design['atmospheric_elements']:
            env_desc += f" with {', '.join(environment_design['atmospheric_elements'])}"
        description_parts.append(env_desc)

        # Lighting description
        lighting_desc = f"Lit with {lighting_setup['primary']} lighting from {lighting_setup['direction']}"
        if 'contrast' in lighting_setup:
            lighting_desc += f" creating {lighting_setup['contrast']} contrast"
        description_parts.append(lighting_desc)

        # Character positioning
        characters = scene_data.get("characters", [])
        if characters:
            char_desc = f"Characters positioned using {composition_type} composition"
            if len(characters) == 1:
                char_desc += f" with {characters[0]} in center focus"
            elif len(characters) == 2:
                char_desc += f" with {characters[0]} and {characters[1]} in balanced interaction"
            else:
                char_desc += f" with {len(characters)} characters strategically arranged"
            description_parts.append(char_desc)

        # Color palette
        palette_desc = f"Color palette emphasizing {', '.join(color_palette[:3])}"
        description_parts.append(palette_desc)

        # Mood integration
        mood = scene_data.get("mood", "neutral")
        mood_desc = f"Overall atmosphere conveys {mood} mood through visual composition"
        description_parts.append(mood_desc)

        return ". ".join(description_parts) + "."

    async def _generate_technical_notes(
        self,
        composition_type: str,
        camera_angle: str,
        lighting_setup: Dict[str, Any]
    ) -> str:
        """Generate technical notes for production"""

        technical_notes = []

        # Composition notes
        comp_notes = {
            "rule_of_thirds": "Place primary elements on third-line intersections for balanced composition",
            "golden_ratio": "Use spiral composition guide for dynamic visual flow",
            "central_symmetry": "Maintain perfect symmetrical balance around center axis",
            "diagonal_dynamic": "Emphasize diagonal lines for energy and movement",
            "depth_layering": "Establish clear foreground, midground, and background separation"
        }
        technical_notes.append(comp_notes.get(composition_type, "Standard composition guidelines"))

        # Camera technical notes
        camera_notes = {
            "wide_shot": "Use wide-angle lens, ensure stable mounting for environmental shots",
            "medium_shot": "Standard lens, focus on character interaction zones",
            "close_up": "Slightly telephoto lens, precise focus control essential",
            "extreme_close_up": "Macro or telephoto lens, critical focus and lighting control",
            "establishing_shot": "Ultra-wide lens, maximum depth of field"
        }
        technical_notes.append(camera_notes[camera_angle])

        # Lighting technical notes
        lighting_note = f"Lighting setup: {lighting_setup['primary']} from {lighting_setup['direction']}"
        if 'intensity' in lighting_setup:
            lighting_note += f" at {lighting_setup['intensity']} intensity"
        technical_notes.append(lighting_note)

        return " | ".join(technical_notes)