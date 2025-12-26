#!/usr/bin/env python3
"""
Scene Director - Professional 15-Second Scene Production
Creates complete narrative scenes with multiple shots, camera movement, and timing
"""

import requests
import json
import time
import uuid
import os
import subprocess
import shutil
from typing import List, Dict, Any
from dataclasses import dataclass

# Proven parameters from validation system
PROVEN_PARAMETERS = {
    'sampling_steps': 30,  # 1.5x base
    'cfg_scale': 4.32,     # 0.6x base
    'sampler': 'dpmpp_2m',
    'scheduler': 'karras'
}

@dataclass
class Shot:
    """Professional shot definition"""
    id: str
    duration: float  # seconds
    description: str
    keyframes: int
    camera: str
    poses: List[str]

    @property
    def frames_count(self):
        return int(self.duration * 24)  # 24fps

class SceneDirector:
    """Professional scene production pipeline"""

    def __init__(self, title: str, total_duration: float = 15.0, fps: int = 24):
        self.title = title
        self.total_duration = total_duration
        self.fps = fps
        self.shots = []
        self.timestamp = int(time.time())
        self.output_dir = f"/mnt/1TB-storage/ComfyUI/output/scene_{self.timestamp}"

    def add_shot(self, shot_data: Dict[str, Any]):
        """Add a shot to the scene"""

        shot = Shot(
            id=shot_data['id'],
            duration=shot_data['duration'],
            description=shot_data['description'],
            keyframes=shot_data['keyframes'],
            camera=shot_data['camera'],
            poses=shot_data.get('poses', [])
        )

        self.shots.append(shot)
        print(f"📝 Added shot '{shot.id}': {shot.duration}s, {shot.keyframes} keyframes")

    def generate_shot_keyframes(self, shot: Shot, shot_number: int) -> List[str]:
        """Generate keyframes for a single shot"""

        print(f"\n🎬 SHOT {shot_number}: {shot.id.upper()}")
        print(f"   📋 {shot.description}")
        print(f"   ⏱️ Duration: {shot.duration}s")
        print(f"   🎭 Keyframes: {shot.keyframes}")
        print(f"   📷 Camera: {shot.camera}")

        base_prompt = "Ghost Ryker cyberpunk slayer, blue glowing cybernetic left arm visible, tactical helmet with red visor, black armor with red racing stripes"

        # Define camera-specific prompts
        camera_modifiers = {
            'static_wide': "wide shot, full body visible, stable camera angle",
            'close_up': "close-up portrait, facial details, shallow depth of field",
            'slow_zoom_in': "medium shot transitioning closer, dramatic focus",
            'dutch_angle': "tilted camera angle, dynamic composition, action oriented",
            'tracking_down': "camera following motion downward, smooth tracking movement",
            'low_angle': "low camera angle, powerful perspective, dramatic lighting"
        }

        camera_prompt = camera_modifiers.get(shot.camera, "standard camera angle")
        full_prompt = f"{base_prompt}, {camera_prompt}, anime style, high detail, consistent character design"

        shot_keyframes = []

        # Generate keyframes for this shot
        for frame_num in range(shot.keyframes):
            # Create specific pose description for this frame
            if shot.poses and frame_num < len(shot.poses):
                pose_description = shot.poses[frame_num]
            else:
                # Generate pose based on shot type and frame number
                progress = frame_num / max(1, shot.keyframes - 1)
                pose_description = self._generate_pose_for_shot(shot, progress)

            print(f"   🎭 Generating keyframe {frame_num + 1}/{shot.keyframes}: {pose_description[:60]}...")

            keyframe_path = self._generate_single_keyframe(
                full_prompt,
                pose_description,
                f"{shot.id}_{frame_num:02d}",
                shot_number,
                frame_num
            )

            if keyframe_path:
                shot_keyframes.append(keyframe_path)
                print(f"      ✅ Generated: {os.path.basename(keyframe_path)}")
            else:
                print(f"      ❌ Failed to generate keyframe {frame_num + 1}")

            time.sleep(1)  # Brief pause between generations

        print(f"   📊 Shot {shot_number} completed: {len(shot_keyframes)}/{shot.keyframes} keyframes")
        return shot_keyframes

    def _generate_pose_for_shot(self, shot: Shot, progress: float) -> str:
        """Generate pose description based on shot type and progress"""

        shot_poses = {
            'establishing': [
                "crouched on rooftop edge, scanning the area below",
                "turning head left, alert and focused",
                "looking right, checking for threats",
                "slowly standing up, maintaining vigilance",
                "final scan of the environment, ready for action"
            ],
            'close_up': [
                "eyes closed, preparing for cybernetic activation",
                "eyes opening, slight glow beginning",
                "cybernetic eye fully active, bright blue glow",
                "HUD targeting system active, focused expression"
            ],
            'action_prep': [
                "hand reaching for weapon holster",
                "drawing weapon smoothly",
                "weapon raised, checking ammunition",
                "weapon ready position, finger on trigger",
                "combat stance, weapon trained forward",
                "tactical reload motion",
                "weapon lowered slightly, confident pose",
                "ready for action, weapon at the ready"
            ],
            'descent': [
                "coiled position, preparing to leap",
                "pushing off from rooftop edge",
                "mid-air, arms extended for balance",
                "falling motion, controlled descent",
                "reaching for fire escape railing",
                "grabbing fire escape, momentum continuing",
                "swinging on fire escape",
                "controlled descent continues",
                "preparing for landing below",
                "extending legs for impact",
                "final descent motion",
                "touching down on ground level"
            ],
            'landing': [
                "impact with ground, knees bent",
                "absorbing impact, crouched low",
                "rising slightly, hand touching ground",
                "surveying the alley, head turning",
                "standing slowly, alert and ready",
                "final vigilant pose, mission ready"
            ]
        }

        if shot.id in shot_poses:
            poses = shot_poses[shot.id]
            pose_index = min(int(progress * len(poses)), len(poses) - 1)
            return poses[pose_index]
        else:
            return f"dynamic pose for {shot.description}, progress: {progress:.1%}"

    def _generate_single_keyframe(self, prompt: str, pose_description: str, frame_id: str, shot_num: int, frame_num: int) -> str:
        """Generate single keyframe using proven parameters"""

        workflow = {
            "1": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": f"{prompt}, {pose_description}",
                    "clip": ["4", 1]
                }
            },
            "2": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": "worst quality, low quality, blurry, deformed, bad anatomy, morphing, inconsistent",
                    "clip": ["4", 1]
                }
            },
            "3": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": int(time.time()) + shot_num * 1000 + frame_num,
                    "steps": PROVEN_PARAMETERS['sampling_steps'],
                    "cfg": PROVEN_PARAMETERS['cfg_scale'],
                    "sampler_name": PROVEN_PARAMETERS['sampler'],
                    "scheduler": PROVEN_PARAMETERS['scheduler'],
                    "denoise": 1.0,
                    "model": ["4", 0],
                    "positive": ["1", 0],
                    "negative": ["2", 0],
                    "latent_image": ["5", 0]
                }
            },
            "4": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {
                    "ckpt_name": "counterfeit_v3.safetensors"
                }
            },
            "5": {
                "class_type": "EmptyLatentImage",
                "inputs": {
                    "width": 512,
                    "height": 512,
                    "batch_size": 1
                }
            },
            "6": {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": ["3", 0],
                    "vae": ["4", 2]
                }
            },
            "7": {
                "class_type": "SaveImage",
                "inputs": {
                    "filename_prefix": f"scene_keyframes/shot_{shot_num:02d}_{frame_id}",
                    "images": ["6", 0]
                }
            }
        }

        try:
            client_id = str(uuid.uuid4())
            payload = {
                "prompt": workflow,
                "client_id": client_id
            }

            response = requests.post("http://localhost:8188/prompt", json=payload, timeout=60)

            if response.status_code != 200:
                return None

            result = response.json()
            prompt_id = result.get('prompt_id')

            if not prompt_id:
                return None

            # Wait for completion
            for attempt in range(60):
                time.sleep(2)
                history_response = requests.get(f"http://localhost:8188/history/{prompt_id}")

                if history_response.status_code == 200:
                    history = history_response.json()

                    if prompt_id in history and 'outputs' in history[prompt_id]:
                        outputs = history[prompt_id]['outputs']

                        for node_id, node_output in outputs.items():
                            if 'images' in node_output:
                                images = node_output['images']
                                if images:
                                    image_info = images[0]
                                    filename = image_info.get('filename')
                                    subfolder = image_info.get('subfolder', '')

                                    if subfolder:
                                        image_path = f"/mnt/1TB-storage/ComfyUI/output/{subfolder}/{filename}"
                                    else:
                                        image_path = f"/mnt/1TB-storage/ComfyUI/output/{filename}"

                                    return image_path

            return None

        except Exception as e:
            print(f"      ❌ Error: {e}")
            return None

    def create_scene_video(self, shot_videos: List[str]) -> str:
        """Combine shot videos into final scene"""

        print(f"\n🎬 CREATING FINAL SCENE VIDEO")

        scene_video = f"/mnt/1TB-storage/ComfyUI/output/{self.title.lower().replace(' ', '_')}_{self.timestamp}.mp4"

        # Create temporary file list for ffmpeg
        concat_file = f"/tmp/scene_concat_{self.timestamp}.txt"

        with open(concat_file, 'w') as f:
            for video in shot_videos:
                f.write(f"file '{video}'\n")

        # Concatenate all shots
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_file,
            "-c", "copy",
            scene_video
        ]

        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)

            # Clean up
            os.remove(concat_file)

            print(f"✅ Scene video created: {os.path.basename(scene_video)}")
            return scene_video

        except subprocess.CalledProcessError as e:
            print(f"❌ Video concatenation failed: {e.stderr}")
            return None

    def generate_complete_scene(self):
        """Generate complete 15-second scene with all shots"""

        print(f"🎬 PROFESSIONAL SCENE PRODUCTION")
        print("=" * 60)
        print(f"Title: {self.title}")
        print(f"Duration: {self.total_duration}s")
        print(f"Shots: {len(self.shots)}")
        print(f"Output: {self.output_dir}")
        print("=" * 60)

        os.makedirs(self.output_dir, exist_ok=True)

        shot_videos = []
        total_keyframes = 0

        # Generate each shot
        for i, shot in enumerate(self.shots, 1):
            print(f"\n📽️ PROCESSING SHOT {i}/{len(self.shots)}")

            # Generate keyframes for this shot
            shot_keyframes = self.generate_shot_keyframes(shot, i)
            total_keyframes += len(shot_keyframes)

            if len(shot_keyframes) >= 4:  # Need minimum keyframes for interpolation
                # Create shot directory
                shot_dir = f"/mnt/1TB-storage/ComfyUI/output/scene_keyframes/shot_{i:02d}"

                # Run RIFE interpolation for this shot
                print(f"   🔥 RIFE interpolating shot {i}...")
                from rife_interpolation import interpolate_keyframes_rife, create_rife_video

                interp_dir = f"{self.output_dir}/shot_{i:02d}_interpolated"
                frames = interpolate_keyframes_rife(shot_dir, interp_dir, shot.frames_count)

                if frames:
                    # Create video for this shot
                    shot_video = f"{self.output_dir}/shot_{i:02d}_{shot.id}.mp4"
                    video_result = create_rife_video(interp_dir, shot_video, self.fps)

                    if video_result:
                        shot_videos.append(video_result)
                        print(f"   ✅ Shot {i} video: {os.path.basename(shot_video)}")
                    else:
                        print(f"   ❌ Shot {i} video creation failed")
                else:
                    print(f"   ❌ Shot {i} interpolation failed")
            else:
                print(f"   ❌ Shot {i} insufficient keyframes: {len(shot_keyframes)}")

        # Create final scene video
        if len(shot_videos) >= 3:  # Need at least 3 shots for a scene
            final_video = self.create_scene_video(shot_videos)

            if final_video:
                file_size = os.path.getsize(final_video)
                filename = os.path.basename(final_video)
                web_link = f"https://192.168.50.135/videos/{filename}"

                print("\n" + "=" * 60)
                print("🎉 PROFESSIONAL SCENE COMPLETE")
                print("=" * 60)
                print(f"✅ {len(self.shots)}-shot narrative scene")
                print(f"🎬 Duration: {self.total_duration}s @ {self.fps}fps")
                print(f"📊 Total keyframes generated: {total_keyframes}")
                print(f"📂 File size: {file_size:,} bytes")
                print(f"🌐 Web: {web_link}")
                print(f"\n📽️ Shot breakdown:")
                for i, shot in enumerate(self.shots, 1):
                    print(f"   Shot {i}: {shot.id} ({shot.duration}s) - {shot.description}")
                print("=" * 60)

                return final_video
            else:
                print("❌ Final scene video creation failed")
        else:
            print(f"❌ Insufficient shots completed: {len(shot_videos)}")

        return None

def create_night_market_scene():
    """Create the 'Night Market Protocol' scene"""

    scene = SceneDirector(
        title="Night Market Protocol - Scene 1",
        total_duration=15.0,
        fps=24
    )

    # Shot 1: Establishing shot
    scene.add_shot({
        'id': 'establishing',
        'duration': 3.0,
        'description': 'Ghost Ryker scans neon market from rooftop',
        'keyframes': 5,
        'camera': 'static_wide'
    })

    # Shot 2: Close-up activation
    scene.add_shot({
        'id': 'close_up',
        'duration': 2.5,
        'description': 'Close-up: cybernetic eye activates with HUD',
        'keyframes': 4,
        'camera': 'slow_zoom_in'
    })

    # Shot 3: Action preparation
    scene.add_shot({
        'id': 'action_prep',
        'duration': 3.0,
        'description': 'Draws weapon, checks ammunition',
        'keyframes': 8,
        'camera': 'dutch_angle'
    })

    # Shot 4: Descent action
    scene.add_shot({
        'id': 'descent',
        'duration': 4.0,
        'description': 'Leaps from rooftop to fire escape',
        'keyframes': 12,
        'camera': 'tracking_down'
    })

    # Shot 5: Landing resolution
    scene.add_shot({
        'id': 'landing',
        'duration': 2.5,
        'description': 'Silent landing in alley, rain-slicked ground',
        'keyframes': 6,
        'camera': 'low_angle'
    })

    return scene.generate_complete_scene()

if __name__ == "__main__":
    try:
        result = create_night_market_scene()
        if result:
            print(f"\n🚀 SUCCESS: Professional 15-second scene completed!")
            print(f"🎬 First multi-shot narrative with professional animation pipeline")
        else:
            print(f"\n💥 FAILED: Scene production incomplete")
    except Exception as e:
        print(f"\n💥 Error: {e}")
        import traceback
        traceback.print_exc()