"""
Video Workflow Compiler for Tower Anime Production
Compiles narrative instructions into executable ComfyUI workflows
"""
import json
import os
import random
import copy
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path
import psycopg2
from psycopg2.extras import RealDictCursor


@dataclass
class SceneDefinition:
    """Represents a single scene in a video sequence"""
    scene_order: int
    location_prompt: str
    action_prompt: str
    emotion_prompt: str
    outfit_override: Optional[str] = None
    transition_type: str = "blend"
    transition_duration_frames: int = 10
    negative_prompt: Optional[str] = None


@dataclass
class CharacterReference:
    """Character consistency information"""
    character_id: int
    reference_image_path: str
    ip_adapter_strength: float = 0.8
    controlnet_strength: float = 0.7


@dataclass
class VideoGenerationRequest:
    """Complete request for video generation"""
    project_id: int
    scenes: List[SceneDefinition]
    character_refs: List[CharacterReference]
    resolution: Tuple[int, int] = (768, 1024)
    fps: int = 24
    total_frames: Optional[int] = None
    base_model: str = "dreamshaper_8.safetensors"
    style_lora: Optional[str] = None


class VideoWorkflowCompiler:
    """Compiles narrative instructions into ComfyUI workflows"""

    def __init__(self, template_dir: str = "/opt/tower-anime-production/workflows"):
        self.template_dir = Path(template_dir)
        self.templates_cache = {}
        self.node_counter = 1
        self.db_config = {
            'host': 'localhost',
            'database': 'anime_production',
            'user': 'patrick',
            'password': 'tower_echo_brain_secret_key_2025'
        }

    def get_db_connection(self):
        """Get database connection"""
        return psycopg2.connect(**self.db_config, cursor_factory=RealDictCursor)

    def load_template(self, template_name: str) -> Dict:
        """Load a workflow template from disk or cache"""
        if template_name in self.templates_cache:
            return copy.deepcopy(self.templates_cache[template_name])

        template_path = self.template_dir / f"{template_name}.json"
        if not template_path.exists():
            # Try to fetch from database
            with self.get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT template_path FROM workflow_templates
                        WHERE template_name = %s AND is_active = true
                    """, (template_name,))
                    result = cur.fetchone()
                    if result:
                        template_path = Path(result['template_path'])
                    else:
                        raise ValueError(f"Template {template_name} not found")

        with open(template_path, 'r') as f:
            template = json.load(f)

        self.templates_cache[template_name] = template
        return copy.deepcopy(template)

    def get_next_node_id(self) -> str:
        """Generate next node ID"""
        node_id = str(self.node_counter)
        self.node_counter += 1
        return node_id

    def create_checkpoint_loader(self, model_name: str) -> Tuple[str, Dict]:
        """Create checkpoint loader node"""
        node_id = self.get_next_node_id()
        node = {
            "inputs": {
                "ckpt_name": model_name
            },
            "class_type": "CheckpointLoaderSimple"
        }
        return node_id, node

    def create_scene_prompt_node(self, scene: SceneDefinition, clip_node: str) -> Tuple[str, str, Dict, Dict]:
        """Create positive and negative prompt conditioning nodes"""
        # Compile full prompt from scene components
        full_prompt = f"{scene.location_prompt}, {scene.action_prompt}, {scene.emotion_prompt}"
        if scene.outfit_override:
            full_prompt += f", {scene.outfit_override}"

        negative_prompt = scene.negative_prompt or "blurry, low quality, distorted, watermark"

        # Positive conditioning
        positive_id = self.get_next_node_id()
        positive_node = {
            "inputs": {
                "text": full_prompt,
                "clip": [clip_node, 1]
            },
            "class_type": "CLIPTextEncode"
        }

        # Negative conditioning
        negative_id = self.get_next_node_id()
        negative_node = {
            "inputs": {
                "text": negative_prompt,
                "clip": [clip_node, 1]
            },
            "class_type": "CLIPTextEncode"
        }

        return positive_id, negative_id, positive_node, negative_node

    def create_ip_adapter_node(self, character_ref: CharacterReference,
                              model_node: str, positive_node: str) -> Tuple[str, Dict]:
        """Create IP-Adapter node for character consistency"""
        node_id = self.get_next_node_id()
        node = {
            "inputs": {
                "weight": character_ref.ip_adapter_strength,
                "weight_type": "linear",
                "combine_embeds": "concat",
                "start_at": 0,
                "end_at": 1,
                "embeds_scaling": "V only",
                "model": [model_node, 0],
                "ipadapter": ["IPAdapterModelLoader", 0],
                "image": ["LoadImage", 0],
                "pos_embed": [positive_node, 0]
            },
            "class_type": "IPAdapterAdvanced"
        }
        return node_id, node

    def create_sampler_node(self, model: str, positive: str, negative: str,
                           latent: str, seed: Optional[int] = None) -> Tuple[str, Dict]:
        """Create KSampler node"""
        node_id = self.get_next_node_id()
        node = {
            "inputs": {
                "seed": seed or random.randint(1, 1000000),
                "steps": 20,
                "cfg": 7.5,
                "sampler_name": "dpmpp_2m",
                "scheduler": "karras",
                "denoise": 1.0,
                "model": [model, 0],
                "positive": [positive, 0],
                "negative": [negative, 0],
                "latent_image": [latent, 0]
            },
            "class_type": "KSampler"
        }
        return node_id, node

    def create_latent_blend_node(self, latent1: str, latent2: str, blend_factor: float = 0.5) -> Tuple[str, Dict]:
        """Create LatentBlend node for scene transitions"""
        node_id = self.get_next_node_id()
        node = {
            "inputs": {
                "blend_factor": blend_factor,
                "blend_mode": "normal",
                "samples1": [latent1, 0],
                "samples2": [latent2, 0]
            },
            "class_type": "LatentBlend"
        }
        return node_id, node

    def create_animatediff_node(self, model: str, context_length: int = 16) -> Tuple[str, Dict]:
        """Create AnimateDiff node for motion"""
        node_id = self.get_next_node_id()
        node = {
            "inputs": {
                "model_name": "mm_sd_v15_v2.ckpt",
                "beta_schedule": "autoselect",
                "context_length": context_length,
                "context_stride": 1,
                "context_overlap": 4,
                "closed_loop": False,
                "model": [model, 0]
            },
            "class_type": "AnimateDiffLoaderWithContext"
        }
        return node_id, node

    def compile_single_scene(self, scene: SceneDefinition, request: VideoGenerationRequest) -> Dict:
        """Compile a single scene workflow"""
        workflow = {}

        # 1. Load checkpoint
        checkpoint_id, checkpoint_node = self.create_checkpoint_loader(request.base_model)
        workflow[checkpoint_id] = checkpoint_node

        # 2. Create prompts
        pos_id, neg_id, pos_node, neg_node = self.create_scene_prompt_node(scene, checkpoint_id)
        workflow[pos_id] = pos_node
        workflow[neg_id] = neg_node

        # 3. Add IP-Adapter if character reference provided
        if request.character_refs:
            char_ref = request.character_refs[0]  # Use first character for now
            ip_id, ip_node = self.create_ip_adapter_node(char_ref, checkpoint_id, pos_id)
            workflow[ip_id] = ip_node
            model_connection = ip_id
        else:
            model_connection = checkpoint_id

        # 4. Create empty latent
        latent_id = self.get_next_node_id()
        workflow[latent_id] = {
            "inputs": {
                "width": request.resolution[0],
                "height": request.resolution[1],
                "batch_size": 1
            },
            "class_type": "EmptyLatentImage"
        }

        # 5. Sample
        sampler_id, sampler_node = self.create_sampler_node(
            model_connection, pos_id, neg_id, latent_id
        )
        workflow[sampler_id] = sampler_node

        # 6. VAE Decode
        vae_id = self.get_next_node_id()
        workflow[vae_id] = {
            "inputs": {
                "samples": [sampler_id, 0],
                "vae": [checkpoint_id, 2]
            },
            "class_type": "VAEDecode"
        }

        # 7. Save Image
        save_id = self.get_next_node_id()
        workflow[save_id] = {
            "inputs": {
                "filename_prefix": f"scene_{scene.scene_order}",
                "images": [vae_id, 0]
            },
            "class_type": "SaveImage"
        }

        return workflow

    def compile_multi_scene_workflow(self, request: VideoGenerationRequest) -> Dict:
        """Compile a complete multi-scene workflow with transitions"""
        workflow = {}
        self.node_counter = 1

        # Load base checkpoint
        checkpoint_id, checkpoint_node = self.create_checkpoint_loader(request.base_model)
        workflow[checkpoint_id] = checkpoint_node

        # Add AnimateDiff for motion
        animatediff_id, animatediff_node = self.create_animatediff_node(checkpoint_id)
        workflow[animatediff_id] = animatediff_node

        scene_latents = []

        # Process each scene
        for i, scene in enumerate(request.scenes):
            # Create prompts for this scene
            pos_id, neg_id, pos_node, neg_node = self.create_scene_prompt_node(scene, checkpoint_id)
            workflow[pos_id] = pos_node
            workflow[neg_id] = neg_node

            # Add character consistency if provided
            model_to_use = animatediff_id
            if request.character_refs:
                char_ref = request.character_refs[0]
                ip_id, ip_node = self.create_ip_adapter_node(char_ref, animatediff_id, pos_id)
                workflow[ip_id] = ip_node
                model_to_use = ip_id

            # Create latent for this scene
            latent_id = self.get_next_node_id()
            workflow[latent_id] = {
                "inputs": {
                    "width": request.resolution[0],
                    "height": request.resolution[1],
                    "batch_size": 16  # For AnimateDiff frames
                },
                "class_type": "EmptyLatentImage"
            }

            # Sample this scene
            sampler_id, sampler_node = self.create_sampler_node(
                model_to_use, pos_id, neg_id, latent_id
            )
            workflow[sampler_id] = sampler_node
            scene_latents.append(sampler_id)

        # Blend scenes together
        current_blend = scene_latents[0]
        for i in range(1, len(scene_latents)):
            blend_id, blend_node = self.create_latent_blend_node(
                current_blend, scene_latents[i],
                blend_factor=0.5
            )
            workflow[blend_id] = blend_node
            current_blend = blend_id

        # VAE Decode the final blended result
        vae_id = self.get_next_node_id()
        workflow[vae_id] = {
            "inputs": {
                "samples": [current_blend, 0],
                "vae": [checkpoint_id, 2]
            },
            "class_type": "VAEDecode"
        }

        # Save as video using VHS Video Combine
        video_combine_id = self.get_next_node_id()
        workflow[video_combine_id] = {
            "inputs": {
                "frame_rate": request.fps,
                "loop_count": 0,
                "filename_prefix": f"project_{request.project_id}_video",
                "format": "video/h264-mp4",
                "pingpong": False,
                "save_output": True,
                "images": [vae_id, 0]
            },
            "class_type": "VHS_VideoCombine"
        }

        return {"prompt": workflow}

    def compile_from_request(self, request: VideoGenerationRequest) -> Dict:
        """Main entry point - compiles request into workflow"""
        if len(request.scenes) == 1:
            return {"prompt": self.compile_single_scene(request.scenes[0], request)}
        else:
            return self.compile_multi_scene_workflow(request)

    def save_workflow(self, workflow: Dict, filename: str) -> str:
        """Save workflow to file for debugging"""
        filepath = self.template_dir / f"generated_{filename}.json"
        with open(filepath, 'w') as f:
            json.dump(workflow, f, indent=2)
        return str(filepath)

    def validate_workflow(self, workflow: Dict) -> Tuple[bool, List[str]]:
        """Validate that workflow has all required nodes"""
        errors = []

        # Check for required node types
        required_types = ["CheckpointLoaderSimple", "KSampler", "VAEDecode"]
        found_types = set()

        for node_id, node in workflow.get("prompt", workflow).items():
            if "class_type" in node:
                found_types.add(node["class_type"])

        for req_type in required_types:
            if req_type not in found_types:
                errors.append(f"Missing required node type: {req_type}")

        return len(errors) == 0, errors