#!/usr/bin/env python3
"""
Intelligent Generation Workflow
Complete system that generates, checks quality, learns, and retries intelligently
"""

import json
import cv2
import requests
import time
import logging
from typing import Dict, List, Optional
from pathlib import Path

from dynamic_prompt_system import DynamicPromptSystem
from multi_person_detector import MultiPersonDetector

logger = logging.getLogger(__name__)

class IntelligentGenerationWorkflow:
    """Complete intelligent generation workflow with learning and adaptation"""

    def __init__(self):
        self.prompt_system = DynamicPromptSystem()
        self.qc_detector = MultiPersonDetector()
        self.comfyui_url = "http://localhost:8188"
        self.max_retries = 3
        self.output_dir = Path("/mnt/1TB-storage/ComfyUI/output")

    def generate_character_intelligently(self, character_name: str, scene_context: str = "portrait",
                                       attempt_number: int = 1) -> Dict:
        """Generate character with intelligent retries and learning"""

        logger.info(f"Starting intelligent generation for {character_name} (attempt {attempt_number})")

        # Get failure history for this character
        previous_failures = self.get_recent_failures(character_name)

        # Build dynamic prompt
        prompt_config = self.prompt_system.build_dynamic_prompt(
            character_name, scene_context, previous_failures
        )

        logger.info(f"Generated strategy: {prompt_config['generation_strategy']}")

        # Generate with ComfyUI
        generation_result = self.generate_with_comfyui(prompt_config)

        if generation_result.get('error'):
            return {'error': f"Generation failed: {generation_result['error']}"}

        # Wait for completion
        image_path = self.wait_for_generation(generation_result['prompt_id'])

        if not image_path:
            return {'error': "Generation timed out or failed"}

        # Quality check
        qc_result = self.perform_quality_check(image_path, prompt_config)

        # Record result for learning
        self.record_generation_result(prompt_config, qc_result, image_path)

        if qc_result['passes_qc']:
            logger.info(f"✅ SUCCESS: {character_name} generated successfully on attempt {attempt_number}")
            return {
                'success': True,
                'image_path': image_path,
                'prompt_config': prompt_config,
                'qc_result': qc_result,
                'attempt_number': attempt_number
            }
        else:
            logger.warning(f"❌ QC FAILED: {character_name} attempt {attempt_number} - {qc_result['failure_reason']}")

            # Retry if under limit
            if attempt_number < self.max_retries:
                logger.info(f"🔄 RETRYING: {character_name} attempt {attempt_number + 1}")
                return self.generate_character_intelligently(
                    character_name, scene_context, attempt_number + 1
                )
            else:
                logger.error(f"💥 FAILED: {character_name} exceeded max retries")
                return {
                    'success': False,
                    'error': f"Failed after {self.max_retries} attempts",
                    'final_qc_result': qc_result,
                    'image_path': image_path,
                    'attempt_number': attempt_number
                }

    def generate_with_comfyui(self, prompt_config: Dict) -> Dict:
        """Generate image using ComfyUI API"""
        try:
            # Build ComfyUI workflow
            workflow = self.build_comfyui_workflow(prompt_config)

            # Submit to ComfyUI
            response = requests.post(
                f"{self.comfyui_url}/api/prompt",
                json={"prompt": workflow},
                timeout=10
            )

            if response.status_code == 200:
                result = response.json()
                return {'prompt_id': result.get('prompt_id')}
            else:
                return {'error': f"ComfyUI API error: {response.status_code}"}

        except Exception as e:
            logger.error(f"ComfyUI generation error: {e}")
            return {'error': str(e)}

    def build_comfyui_workflow(self, prompt_config: Dict) -> Dict:
        """Build ComfyUI workflow from prompt configuration"""
        params = prompt_config['parameters']

        return {
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": "realisticVision_v51.safetensors"}
            },
            "2": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": prompt_config['enhanced_prompt'],
                    "clip": ["1", 1]
                }
            },
            "3": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": prompt_config['negative_prompt'],
                    "clip": ["1", 1]
                }
            },
            "4": {
                "class_type": "EmptyLatentImage",
                "inputs": {
                    "width": params['width'],
                    "height": params['height'],
                    "batch_size": 1
                }
            },
            "5": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": params['seed'],
                    "steps": params['steps'],
                    "cfg": params['cfg'],
                    "sampler_name": params['sampler'],
                    "scheduler": "karras",
                    "denoise": 1.0,
                    "model": ["1", 0],
                    "positive": ["2", 0],
                    "negative": ["3", 0],
                    "latent_image": ["4", 0]
                }
            },
            "6": {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": ["5", 0],
                    "vae": ["1", 2]
                }
            },
            "7": {
                "class_type": "SaveImage",
                "inputs": {
                    "filename_prefix": f"intelligent_{prompt_config['character_name'].lower().replace(' ', '_')}",
                    "images": ["6", 0]
                }
            }
        }

    def wait_for_generation(self, prompt_id: str, timeout: int = 120) -> Optional[str]:
        """Wait for ComfyUI generation to complete and return image path"""
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                # Check history for completion
                response = requests.get(f"{self.comfyui_url}/history/{prompt_id}")
                if response.status_code == 200:
                    history = response.json()
                    if prompt_id in history:
                        # Find output image path
                        outputs = history[prompt_id].get('outputs', {})
                        for node_id, node_output in outputs.items():
                            if 'images' in node_output:
                                for img_info in node_output['images']:
                                    filename = img_info.get('filename')
                                    if filename:
                                        return str(self.output_dir / filename)

                # Check if still running
                queue_response = requests.get(f"{self.comfyui_url}/queue")
                if queue_response.status_code == 200:
                    queue_data = queue_response.json()
                    running_ids = [item[1][1] for item in queue_data.get('queue_running', [])]
                    if prompt_id not in running_ids:
                        # Not running but not in history - likely failed
                        break

                time.sleep(2)

            except Exception as e:
                logger.error(f"Error checking generation status: {e}")
                time.sleep(2)

        logger.error(f"Generation timeout or failure for prompt {prompt_id}")
        return None

    def perform_quality_check(self, image_path: str, prompt_config: Dict) -> Dict:
        """Perform comprehensive quality check"""
        try:
            # Multi-person detection
            detection_result = self.qc_detector.detect_multiple_people(image_path)

            if detection_result.get('error'):
                return {'passes_qc': False, 'failure_reason': f"QC error: {detection_result['error']}"}

            # Check against expected criteria
            success_criteria = prompt_config['expected_result']
            detected_faces = detection_result['face_count']
            expected_faces = success_criteria['expected_faces']

            # Determine if passes QC
            passes_qc = True
            failure_reasons = []

            if expected_faces and detected_faces != expected_faces:
                passes_qc = False
                failure_reasons.append(f"Expected {expected_faces} faces, detected {detected_faces}")

            if detected_faces > success_criteria.get('max_acceptable_faces', 1):
                passes_qc = False
                failure_reasons.append(f"Too many faces: {detected_faces}")

            return {
                'passes_qc': passes_qc,
                'detected_faces': detected_faces,
                'expected_faces': expected_faces,
                'failure_reason': '; '.join(failure_reasons) if failure_reasons else None,
                'qc_confidence': detection_result.get('confidence_score', 0.5),
                'detection_details': detection_result
            }

        except Exception as e:
            logger.error(f"Quality check error: {e}")
            return {'passes_qc': False, 'failure_reason': f"QC system error: {e}"}

    def get_recent_failures(self, character_name: str, limit: int = 10) -> List[Dict]:
        """Get recent failures for this character for learning"""
        # This would query the database for recent failures
        # For now, return empty list
        return []

    def record_generation_result(self, prompt_config: Dict, qc_result: Dict, image_path: str):
        """Record generation result for learning"""
        try:
            self.prompt_system.record_result(
                prompt_config,
                success=qc_result['passes_qc'],
                detected_faces=qc_result.get('detected_faces', 0),
                failure_reason=qc_result.get('failure_reason'),
                image_path=image_path
            )
        except Exception as e:
            logger.error(f"Failed to record result: {e}")

def test_intelligent_workflow():
    """Test the complete intelligent workflow"""
    workflow = IntelligentGenerationWorkflow()

    print("=== Intelligent Generation Workflow Test ===")

    # Test with Yuki Tanaka
    result = workflow.generate_character_intelligently("Yuki Tanaka", "portrait")

    if result.get('success'):
        print(f"✅ SUCCESS: Generated {result['image_path']}")
        print(f"Attempts: {result['attempt_number']}")
        print(f"QC Score: {result['qc_result']['qc_confidence']}")
    else:
        print(f"❌ FAILED: {result.get('error', 'Unknown error')}")
        if result.get('final_qc_result'):
            print(f"Final QC: {result['final_qc_result']['failure_reason']}")

if __name__ == "__main__":
    test_intelligent_workflow()