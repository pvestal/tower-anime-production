"""
Condition Compiler for Multi-Condition Video Generation
Compiles high-level creative direction into executable ComfyUI workflows
"""

import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import numpy as np
from pathlib import Path

from .comfyui_api_client import DynamicWorkflowBuilder

logger = logging.getLogger(__name__)


class ConditionType(Enum):
    """Types of conditions that can be applied to generation"""
    TEXT_PROMPT = "text_prompt"
    CHARACTER_IDENTITY = "character_identity"
    POSE_CONTROL = "pose_control"
    CAMERA_MOTION = "camera_motion"
    STYLE_REFERENCE = "style_reference"
    EMOTION_EXPRESSION = "emotion_expression"
    SCENE_CONTEXT = "scene_context"
    TEMPORAL_CONSISTENCY = "temporal_consistency"


@dataclass
class GenerationCondition:
    """Individual generation condition"""
    type: ConditionType
    data: Any
    weight: float = 1.0
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class SceneRequest:
    """Complete scene generation request"""
    scene_id: str
    storyline_text: str
    character_ids: List[str]
    conditions: List[GenerationCondition]
    output_format: str = "video"  # video, image_sequence, single_frame
    resolution: Tuple[int, int] = (512, 768)
    duration_seconds: float = 2.0
    fps: int = 8
    style_preset: Optional[str] = None


class ConditionCompiler:
    """
    Compiles multiple conditions into a unified ComfyUI workflow
    """

    def __init__(self, vector_db_client=None, asset_manager=None):
        self.vector_db = vector_db_client
        self.asset_manager = asset_manager
        self.workflow_templates = self._load_workflow_templates()

    def _load_workflow_templates(self) -> Dict[str, Any]:
        """Load pre-defined workflow templates"""
        templates = {
            "text_to_image": "workflows/templates/text_to_image.json",
            "text_to_video": "workflows/templates/text_to_video.json",
            "character_consistent": "workflows/templates/character_consistent.json",
            "pose_controlled": "workflows/templates/pose_controlled.json",
            "multi_condition": "workflows/templates/multi_condition.json",
            "animation_sequence": "workflows/templates/animation_sequence.json"
        }

        loaded_templates = {}
        for name, path in templates.items():
            template_path = Path(path)
            if template_path.exists():
                with open(template_path, 'r') as f:
                    loaded_templates[name] = json.load(f)
            else:
                logger.warning(f"Template not found: {path}")

        return loaded_templates

    def compile_scene(self, request: SceneRequest) -> Dict[str, Any]:
        """
        Compile a scene request into an executable workflow

        Args:
            request: Scene generation request with all conditions

        Returns:
            Complete ComfyUI workflow ready for execution
        """
        # Select base template based on conditions
        template_name = self._select_template(request)
        builder = DynamicWorkflowBuilder()

        # Build the workflow based on conditions
        if request.output_format == "video":
            workflow = self._build_video_workflow(builder, request)
        elif request.output_format == "image_sequence":
            workflow = self._build_image_sequence_workflow(builder, request)
        else:
            workflow = self._build_single_image_workflow(builder, request)

        # Inject placeholders with actual values
        placeholders = self._extract_placeholders(request)
        workflow = self._inject_values(workflow, placeholders)

        return workflow

    def _select_template(self, request: SceneRequest) -> str:
        """Select appropriate workflow template based on conditions"""
        condition_types = {c.type for c in request.conditions}

        if ConditionType.POSE_CONTROL in condition_types and \
           ConditionType.CHARACTER_IDENTITY in condition_types:
            return "multi_condition"
        elif ConditionType.CHARACTER_IDENTITY in condition_types:
            return "character_consistent"
        elif ConditionType.POSE_CONTROL in condition_types:
            return "pose_controlled"
        elif request.output_format == "video":
            return "text_to_video"
        else:
            return "text_to_image"

    def _build_video_workflow(self, builder: DynamicWorkflowBuilder,
                             request: SceneRequest) -> Dict[str, Any]:
        """Build a video generation workflow"""
        # Load checkpoint
        checkpoint = builder.add_checkpoint_loader()

        # Process text prompt
        positive_prompt = self._compile_positive_prompt(request)
        negative_prompt = self._compile_negative_prompt(request)

        positive = builder.add_clip_text_encode(
            positive_prompt,
            builder.link(checkpoint, 1)
        )
        negative = builder.add_clip_text_encode(
            negative_prompt,
            builder.link(checkpoint, 1)
        )

        # Apply character identity if present
        model_output = builder.link(checkpoint, 0)
        conditioning_positive = builder.link(positive, 0)

        character_condition = self._get_condition(request, ConditionType.CHARACTER_IDENTITY)
        if character_condition:
            # Load IPAdapter for character consistency
            ipadapter_loader = builder.add_node("IPAdapterModelLoader", {
                "ipadapter_file": "ip-adapter-plus_sd15.bin"
            })

            # Load character reference image
            character_image = builder.add_node("LoadImage", {
                "image": character_condition.data["reference_image"]
            })

            # Apply IPAdapter
            ipadapter_apply = builder.add_ipadapter(
                model_output,
                builder.link(ipadapter_loader, 0),
                builder.link(character_image, 0),
                weight=character_condition.weight
            )
            model_output = builder.link(ipadapter_apply, 0)

        # Apply pose control if present
        pose_condition = self._get_condition(request, ConditionType.POSE_CONTROL)
        if pose_condition:
            # Load ControlNet
            controlnet = builder.add_controlnet_loader("control_v11p_sd15_openpose.pth")

            # Load pose image
            pose_image = builder.add_node("LoadImage", {
                "image": pose_condition.data["pose_image"]
            })

            # Apply ControlNet
            controlnet_apply = builder.add_controlnet_apply(
                conditioning_positive,
                builder.link(controlnet, 0),
                builder.link(pose_image, 0),
                strength=pose_condition.weight
            )
            conditioning_positive = builder.link(controlnet_apply, 0)

        # Generate frames
        frame_count = int(request.duration_seconds * request.fps)

        # For video, we need to use AnimateDiff or similar
        # This is a simplified version - real implementation would use proper video model
        animatediff = builder.add_node("ADE_AnimateDiffLoaderGen1", {
            "model_name": "mm_sd_v15_v2.ckpt",
            "beta_schedule": "sqrt_linear"
        })

        # Apply AnimateDiff to model
        animated_model = builder.add_node("ADE_ApplyAnimateDiffModel", {
            "model": model_output,
            "motion_model": builder.link(animatediff, 0)
        })

        # Create latent for animation
        latent = builder.add_node("ADE_EmptyLatentImageLarge", {
            "width": request.resolution[0],
            "height": request.resolution[1],
            "batch_size": frame_count
        })

        # Sample
        sampler = builder.add_ksampler(
            builder.link(animated_model, 0),
            conditioning_positive,
            builder.link(negative, 0),
            builder.link(latent, 0),
            steps=20,  # Reduced for video
            cfg=7.0
        )

        # Decode
        vae_decode = builder.add_vae_decode(
            builder.link(sampler, 0),
            builder.link(checkpoint, 2)
        )

        # Combine into video
        video_combine = builder.add_video_combine(
            builder.link(vae_decode, 0),
            frame_rate=request.fps
        )

        return builder.build()

    def _build_image_sequence_workflow(self, builder: DynamicWorkflowBuilder,
                                      request: SceneRequest) -> Dict[str, Any]:
        """Build workflow for image sequence generation"""
        # Similar to video but saves individual frames
        workflow = self._build_video_workflow(builder, request)

        # Replace video combine with image save
        # (Implementation details omitted for brevity)

        return workflow

    def _build_single_image_workflow(self, builder: DynamicWorkflowBuilder,
                                    request: SceneRequest) -> Dict[str, Any]:
        """Build workflow for single image generation"""
        # Load checkpoint
        checkpoint = builder.add_checkpoint_loader()

        # Text encoding
        positive_prompt = self._compile_positive_prompt(request)
        negative_prompt = self._compile_negative_prompt(request)

        positive = builder.add_clip_text_encode(
            positive_prompt,
            builder.link(checkpoint, 1)
        )
        negative = builder.add_clip_text_encode(
            negative_prompt,
            builder.link(checkpoint, 1)
        )

        # Empty latent
        latent = builder.add_empty_latent(
            width=request.resolution[0],
            height=request.resolution[1]
        )

        # Sample
        sampler = builder.add_ksampler(
            builder.link(checkpoint, 0),
            builder.link(positive, 0),
            builder.link(negative, 0),
            builder.link(latent, 0)
        )

        # Decode and save
        vae_decode = builder.add_vae_decode(
            builder.link(sampler, 0),
            builder.link(checkpoint, 2)
        )

        save_image = builder.add_image_save(
            builder.link(vae_decode, 0),
            filename_prefix=f"scene_{request.scene_id}"
        )

        return builder.build()

    def _compile_positive_prompt(self, request: SceneRequest) -> str:
        """Compile all positive prompt conditions"""
        prompt_parts = [request.storyline_text]

        # Add style preset if specified
        if request.style_preset:
            prompt_parts.append(self._get_style_prompt(request.style_preset))

        # Add emotion expressions
        emotion_condition = self._get_condition(request, ConditionType.EMOTION_EXPRESSION)
        if emotion_condition:
            prompt_parts.append(emotion_condition.data["expression"])

        # Add scene context
        scene_condition = self._get_condition(request, ConditionType.SCENE_CONTEXT)
        if scene_condition:
            prompt_parts.append(scene_condition.data["context"])

        # Add quality tags
        prompt_parts.extend([
            "masterpiece", "best quality", "highly detailed",
            "professional", "4k", "ultra-detailed"
        ])

        return ", ".join(prompt_parts)

    def _compile_negative_prompt(self, request: SceneRequest) -> str:
        """Compile negative prompt to avoid unwanted elements"""
        negative_parts = [
            "worst quality", "low quality", "normal quality",
            "lowres", "blurry", "text", "watermark", "logo",
            "banner", "extra digits", "cropped", "jpeg artifacts",
            "signature", "username", "error", "duplicate",
            "ugly", "monochrome", "horror", "geometry",
            "mutation", "disgusting"
        ]

        # Add style-specific negatives
        if request.style_preset == "realistic":
            negative_parts.extend(["cartoon", "anime", "illustration", "painting"])
        elif request.style_preset == "anime":
            negative_parts.extend(["realistic", "photo", "photorealistic"])

        return ", ".join(negative_parts)

    def _get_condition(self, request: SceneRequest,
                      condition_type: ConditionType) -> Optional[GenerationCondition]:
        """Get specific condition from request"""
        for condition in request.conditions:
            if condition.type == condition_type:
                return condition
        return None

    def _get_style_prompt(self, style_preset: str) -> str:
        """Get style-specific prompt additions"""
        style_prompts = {
            "realistic": "photorealistic, hyperrealistic, raw photo, 8k uhd, dslr",
            "anime": "anime style, anime artwork, anime character, cel shaded",
            "cinematic": "cinematic lighting, dramatic atmosphere, film grain, movie still",
            "fantasy": "fantasy art, magical atmosphere, ethereal lighting",
            "cyberpunk": "cyberpunk style, neon lights, futuristic, tech noir",
            "watercolor": "watercolor painting, soft colors, artistic, painted"
        }
        return style_prompts.get(style_preset, "")

    def _extract_placeholders(self, request: SceneRequest) -> Dict[str, Any]:
        """Extract placeholder values from request"""
        placeholders = {
            "SCENE_ID": request.scene_id,
            "PREFIX": f"scene_{request.scene_id}",
            "VIDEO_PREFIX": f"video_{request.scene_id}",
            "SEED": np.random.randint(0, 2**32),
            "MODEL": "sd15/chilloutmix_NiPrunedFp32Fix.safetensors"
        }

        # Add character-specific placeholders
        if request.character_ids:
            placeholders["CHARACTER_ID"] = request.character_ids[0]

        return placeholders

    def _inject_values(self, workflow: Dict[str, Any],
                      placeholders: Dict[str, Any]) -> Dict[str, Any]:
        """Inject placeholder values into workflow"""
        workflow_str = json.dumps(workflow)

        for key, value in placeholders.items():
            placeholder = f"{{{{PLACEHOLDER_{key}}}}}"
            if isinstance(value, str):
                replacement = value
            else:
                replacement = str(value)

            workflow_str = workflow_str.replace(placeholder, replacement)

        return json.loads(workflow_str)

    def validate_conditions(self, conditions: List[GenerationCondition]) -> List[str]:
        """
        Validate that conditions are compatible

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        # Check for conflicting conditions
        condition_types = [c.type for c in conditions]

        # Can't have multiple character identities
        if condition_types.count(ConditionType.CHARACTER_IDENTITY) > 1:
            errors.append("Multiple character identities not supported in single generation")

        # Pose control requires character identity for best results
        if ConditionType.POSE_CONTROL in condition_types and \
           ConditionType.CHARACTER_IDENTITY not in condition_types:
            logger.warning("Pose control without character identity may produce inconsistent results")

        # Validate data formats
        for condition in conditions:
            if condition.type == ConditionType.CHARACTER_IDENTITY:
                if "reference_image" not in condition.data and "embedding_id" not in condition.data:
                    errors.append("Character identity requires reference_image or embedding_id")

            elif condition.type == ConditionType.POSE_CONTROL:
                if "pose_image" not in condition.data and "pose_keypoints" not in condition.data:
                    errors.append("Pose control requires pose_image or pose_keypoints")

        return errors