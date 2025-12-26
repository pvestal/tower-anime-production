"""
ComfyUI API Client for Dynamic Workflow Orchestration
Provides programmatic control over ComfyUI workflows with placeholder injection
"""

import json
import uuid
import asyncio
import aiohttp
import websocket
from typing import Dict, Any, List, Optional, Tuple, Generator
from pathlib import Path
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class ComfyUIAPIClient:
    """
    Advanced ComfyUI API client for dynamic workflow orchestration
    """

    def __init__(self, base_url: str = "http://127.0.0.1:8188"):
        self.base_url = base_url
        self.client_id = str(uuid.uuid4())
        self.ws = None
        self.session = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
        if self.ws:
            self.ws.close()

    def connect_websocket(self) -> websocket.WebSocket:
        """Establish WebSocket connection for real-time updates"""
        ws_url = f"ws://{self.base_url.replace('http://', '').replace('https://', '')}/ws?clientId={self.client_id}"
        self.ws = websocket.create_connection(ws_url)
        return self.ws

    async def get_system_stats(self) -> Dict[str, Any]:
        """Get ComfyUI system statistics"""
        async with self.session.get(f"{self.base_url}/system_stats") as response:
            return await response.json()

    async def get_queue(self) -> Dict[str, Any]:
        """Get current queue status"""
        async with self.session.get(f"{self.base_url}/queue") as response:
            return await response.json()

    async def get_history(self, prompt_id: Optional[str] = None) -> Dict[str, Any]:
        """Get execution history"""
        url = f"{self.base_url}/history"
        if prompt_id:
            url += f"/{prompt_id}"
        async with self.session.get(url) as response:
            return await response.json()

    async def upload_image(self, image_path: str, subfolder: str = "") -> Dict[str, Any]:
        """Upload image to ComfyUI input directory"""
        with open(image_path, 'rb') as f:
            data = aiohttp.FormData()
            data.add_field('image', f, filename=Path(image_path).name)
            if subfolder:
                data.add_field('subfolder', subfolder)

            async with self.session.post(f"{self.base_url}/upload/image", data=data) as response:
                return await response.json()

    async def execute_workflow(self, workflow: Dict[str, Any]) -> str:
        """
        Execute a workflow and return the prompt ID

        Args:
            workflow: Complete workflow dictionary with all nodes

        Returns:
            prompt_id for tracking execution
        """
        payload = {
            "prompt": workflow,
            "client_id": self.client_id
        }

        async with self.session.post(f"{self.base_url}/prompt", json=payload) as response:
            result = await response.json()
            return result.get('prompt_id')

    async def interrupt_execution(self) -> bool:
        """Interrupt current execution"""
        async with self.session.post(f"{self.base_url}/interrupt") as response:
            return response.status == 200

    async def clear_queue(self) -> Dict[str, Any]:
        """Clear the execution queue"""
        payload = {"clear": True}
        async with self.session.post(f"{self.base_url}/queue", json=payload) as response:
            return await response.json()

    async def delete_from_queue(self, prompt_id: str) -> bool:
        """Delete specific item from queue"""
        payload = {"delete": [prompt_id]}
        async with self.session.post(f"{self.base_url}/queue", json=payload) as response:
            return response.status == 200

    def inject_placeholder(self, workflow: Dict[str, Any], placeholders: Dict[str, Any]) -> Dict[str, Any]:
        """
        Inject values into workflow placeholders

        Args:
            workflow: Template workflow with placeholders
            placeholders: Dict of placeholder_name -> value

        Returns:
            Workflow with injected values
        """
        workflow_str = json.dumps(workflow)

        for key, value in placeholders.items():
            placeholder = f"{{{{PLACEHOLDER_{key.upper()}}}}}"

            # Handle different value types
            if isinstance(value, str):
                replacement = json.dumps(value)
            elif isinstance(value, (int, float, bool)):
                replacement = str(value)
            elif isinstance(value, (list, dict)):
                replacement = json.dumps(value)
            else:
                replacement = str(value)

            workflow_str = workflow_str.replace(placeholder, replacement)

        return json.loads(workflow_str)

    async def wait_for_completion(self, prompt_id: str, timeout: int = 300) -> Dict[str, Any]:
        """
        Wait for workflow completion with timeout

        Args:
            prompt_id: The prompt ID to wait for
            timeout: Maximum time to wait in seconds

        Returns:
            Execution results
        """
        start_time = asyncio.get_event_loop().time()

        while (asyncio.get_event_loop().time() - start_time) < timeout:
            history = await self.get_history(prompt_id)

            if prompt_id in history:
                if history[prompt_id].get('status', {}).get('completed', False):
                    return history[prompt_id]

            await asyncio.sleep(1)

        raise TimeoutError(f"Workflow {prompt_id} did not complete within {timeout} seconds")

    def get_progress_updates(self, prompt_id: str) -> Generator[Dict[str, Any], None, None]:
        """
        Generator for real-time progress updates via WebSocket

        Args:
            prompt_id: The prompt ID to monitor

        Yields:
            Progress update dictionaries
        """
        if not self.ws:
            self.connect_websocket()

        while True:
            try:
                message = json.loads(self.ws.recv())

                if message.get('type') == 'progress' and message.get('data', {}).get('prompt_id') == prompt_id:
                    yield {
                        'node': message['data'].get('node'),
                        'value': message['data'].get('value', 0),
                        'max': message['data'].get('max', 100)
                    }
                elif message.get('type') == 'executed' and message.get('data', {}).get('prompt_id') == prompt_id:
                    yield {
                        'status': 'completed',
                        'node': message['data'].get('node'),
                        'output': message['data'].get('output')
                    }
                    break
                elif message.get('type') == 'execution_error' and message.get('data', {}).get('prompt_id') == prompt_id:
                    yield {
                        'status': 'error',
                        'error': message['data'].get('exception_message')
                    }
                    break

            except websocket.WebSocketTimeoutException:
                continue
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                break


class DynamicWorkflowBuilder:
    """
    Builder for creating dynamic ComfyUI workflows with placeholders
    """

    def __init__(self):
        self.nodes = {}
        self.node_counter = 0

    def add_node(self, node_type: str, inputs: Dict[str, Any],
                 node_id: Optional[str] = None) -> str:
        """
        Add a node to the workflow

        Args:
            node_type: ComfyUI node class name
            inputs: Node input parameters
            node_id: Optional custom node ID

        Returns:
            Node ID for reference
        """
        if node_id is None:
            node_id = str(self.node_counter)
            self.node_counter += 1

        self.nodes[node_id] = {
            "inputs": inputs,
            "class_type": node_type
        }

        return node_id

    def add_checkpoint_loader(self, model_name: str = "{{PLACEHOLDER_MODEL}}") -> str:
        """Add a checkpoint loader node with placeholder support"""
        return self.add_node("CheckpointLoaderSimple", {
            "ckpt_name": model_name
        })

    def add_clip_text_encode(self, text: str = "{{PLACEHOLDER_PROMPT}}",
                             clip_input: Tuple[str, int] = None) -> str:
        """Add a CLIP text encoder node"""
        inputs = {"text": text}
        if clip_input:
            inputs["clip"] = clip_input

        return self.add_node("CLIPTextEncode", inputs)

    def add_ksampler(self, model_input: Tuple[str, int],
                     positive: Tuple[str, int],
                     negative: Tuple[str, int],
                     latent: Tuple[str, int],
                     seed: int = -1,
                     steps: int = 30,
                     cfg: float = 7.0,
                     sampler: str = "euler_ancestral",
                     scheduler: str = "normal",
                     denoise: float = 1.0) -> str:
        """Add a KSampler node for generation"""
        return self.add_node("KSampler", {
            "seed": seed if seed != -1 else "{{PLACEHOLDER_SEED}}",
            "steps": steps,
            "cfg": cfg,
            "sampler_name": sampler,
            "scheduler": scheduler,
            "denoise": denoise,
            "model": model_input,
            "positive": positive,
            "negative": negative,
            "latent_image": latent
        })

    def add_empty_latent(self, width: int = 512, height: int = 768,
                         batch_size: int = 1) -> str:
        """Add an empty latent image node"""
        return self.add_node("EmptyLatentImage", {
            "width": width,
            "height": height,
            "batch_size": batch_size
        })

    def add_vae_decode(self, samples: Tuple[str, int], vae: Tuple[str, int]) -> str:
        """Add a VAE decoder node"""
        return self.add_node("VAEDecode", {
            "samples": samples,
            "vae": vae
        })

    def add_image_save(self, images: Tuple[str, int],
                       filename_prefix: str = "{{PLACEHOLDER_PREFIX}}") -> str:
        """Add an image save node"""
        return self.add_node("SaveImage", {
            "images": images,
            "filename_prefix": filename_prefix
        })

    def add_controlnet_loader(self, control_net_name: str) -> str:
        """Add a ControlNet loader node"""
        return self.add_node("ControlNetLoader", {
            "control_net_name": control_net_name
        })

    def add_controlnet_apply(self, conditioning: Tuple[str, int],
                             control_net: Tuple[str, int],
                             image: Tuple[str, int],
                             strength: float = 1.0) -> str:
        """Add a ControlNet apply node"""
        return self.add_node("ControlNetApply", {
            "conditioning": conditioning,
            "control_net": control_net,
            "image": image,
            "strength": strength
        })

    def add_ipadapter(self, model: Tuple[str, int],
                      ipadapter: Tuple[str, int],
                      image: Tuple[str, int],
                      weight: float = 1.0,
                      weight_type: str = "standard") -> str:
        """Add an IPAdapter node for character consistency"""
        return self.add_node("IPAdapterApply", {
            "model": model,
            "ipadapter": ipadapter,
            "image": image,
            "weight": weight,
            "weight_type": weight_type
        })

    def add_video_combine(self, images: Tuple[str, int],
                         frame_rate: int = 8,
                         format: str = "video/h264-mp4") -> str:
        """Add a video combine node for animation"""
        return self.add_node("VHS_VideoCombine", {
            "images": images,
            "frame_rate": frame_rate,
            "loop_count": 0,
            "filename_prefix": "{{PLACEHOLDER_VIDEO_PREFIX}}",
            "format": format,
            "pingpong": False,
            "save_output": True
        })

    def link(self, from_node: str, from_index: int = 0) -> Tuple[str, int]:
        """Create a link reference for connecting nodes"""
        return [from_node, from_index]

    def build(self) -> Dict[str, Any]:
        """Build the complete workflow"""
        return self.nodes

    def save_template(self, filepath: str):
        """Save workflow as a template file"""
        with open(filepath, 'w') as f:
            json.dump(self.nodes, f, indent=2)

    def load_template(self, filepath: str):
        """Load workflow from template file"""
        with open(filepath, 'r') as f:
            self.nodes = json.load(f)