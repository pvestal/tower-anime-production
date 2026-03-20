"""RunPod burst video generation — overflow to cloud A100 GPUs.

Submits ComfyUI workflows to a RunPod pod running ComfyUI with WAN 2.2 14B.
Downloads completed videos back to local storage.

Architecture:
  1. Reuse existing RUNNING or EXITED pod (never create new ones automatically)
  2. Upload keyframe image to pod
  3. Submit ComfyUI workflow via pod's ComfyUI API
  4. Poll for completion, download video
  5. Pod stays running for next batch (manual stop only)

Requirements:
  - runpodctl installed and configured (~/.runpod/config.toml)
  - Pod with ComfyUI + WAN 2.2 14B models pre-loaded
  - SSH key configured on pod

Usage:
    from packages.scene_generation.runpod_burst import RunPodBurst

    burst = await RunPodBurst.connect()
    video_path = await burst.generate_video(
        keyframe_path="/opt/ComfyUI/output/keyframe.png",
        prompt="woman dancing",
        lora_high="wan22_nsfw/wan22_cowgirl_HIGH.safetensors",
        motion_tier="high",
    )
"""

import asyncio
import json
import logging
import subprocess
import time
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Cost tracking ─────────────────────────────────────────────────────
# A100 80GB costs ~$1.15/hr on RunPod community cloud
A100_COST_PER_HOUR = 1.15
AVG_VIDEO_TIME_MINUTES = 3.0  # average WAN 2.2 14B I2V on A100
EST_COST_PER_VIDEO = A100_COST_PER_HOUR * (AVG_VIDEO_TIME_MINUTES / 60)


class RunPodBurst:
    """Manages burst video generation on RunPod pods."""

    def __init__(self, pod_id: str, pod_ip: str, comfyui_port: int = 8188):
        self.pod_id = pod_id
        self.pod_ip = pod_ip
        self.comfyui_port = comfyui_port
        self.comfyui_url = f"http://{pod_ip}:{comfyui_port}"
        self.ssh_port = 22

    @classmethod
    async def connect(cls, pod_name: str = "tower-moto-lora") -> "RunPodBurst | None":
        """Find and connect to an existing RunPod pod.

        NEVER creates new pods — per user directive.
        Restarts EXITED pods instead of deleting them.
        """
        # Get pod list
        result = subprocess.run(
            ["runpodctl", "get", "pod"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            logger.error(f"runpodctl failed: {result.stderr}")
            return None

        # Parse pod list
        lines = result.stdout.strip().split("\n")
        if len(lines) < 2:
            logger.error("No RunPod pods found")
            return None

        target_pod = None
        for line in lines[1:]:  # skip header
            parts = line.split("\t")
            if len(parts) >= 4:
                pid, name, gpu, image, status = (
                    parts[0].strip(), parts[1].strip(), parts[2].strip(),
                    parts[3].strip(), parts[4].strip() if len(parts) > 4 else "",
                )
                if pod_name in name:
                    target_pod = {"id": pid, "name": name, "status": status}
                    break

        if not target_pod:
            logger.error(f"Pod '{pod_name}' not found")
            return None

        # Restart if EXITED (never delete — per feedback)
        if target_pod["status"] == "EXITED":
            logger.info(f"Restarting EXITED pod {target_pod['id']}...")
            subprocess.run(
                ["runpodctl", "start", "pod", target_pod["id"]],
                capture_output=True, timeout=15,
            )
            # Wait for pod to come up
            for _ in range(30):
                await asyncio.sleep(10)
                check = subprocess.run(
                    ["runpodctl", "get", "pod"],
                    capture_output=True, text=True, timeout=15,
                )
                if "RUNNING" in check.stdout and target_pod["id"] in check.stdout:
                    break
            else:
                logger.error("Pod failed to start within 5 minutes")
                return None

        if target_pod["status"] not in ("RUNNING",):
            # Re-check after restart attempt
            pass

        # Get pod IP via RunPod API
        pod_ip = await cls._get_pod_ip(target_pod["id"])
        if not pod_ip:
            logger.error("Could not determine pod IP")
            return None

        burst = cls(target_pod["id"], pod_ip)
        logger.info(f"Connected to RunPod pod {target_pod['name']} ({pod_ip})")
        return burst

    @staticmethod
    async def _get_pod_ip(pod_id: str) -> str | None:
        """Get pod public IP from RunPod API."""
        try:
            import tomllib
            with open(Path.home() / ".runpod" / "config.toml", "rb") as f:
                config = tomllib.load(f)
            api_key = config.get("apikey", "")

            query = """
            query {{
              pod(input: {{ podId: "{pod_id}" }}) {{
                runtime {{ ports {{ ip privatePort publicPort }} }}
              }}
            }}
            """.replace("{pod_id}", pod_id)

            data = json.dumps({"query": query}).encode()
            req = urllib.request.Request(
                "https://api.runpod.io/graphql",
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
            )
            resp = urllib.request.urlopen(req, timeout=15)
            result = json.loads(resp.read())
            ports = result.get("data", {}).get("pod", {}).get("runtime", {}).get("ports", [])
            for p in ports:
                if p.get("privatePort") == 8188:
                    return f"{p['ip']}:{p['publicPort']}"
            # Fallback: return first IP
            if ports:
                return ports[0].get("ip")
        except Exception as e:
            logger.warning(f"Could not get pod IP: {e}")
        return None

    async def is_ready(self) -> bool:
        """Check if ComfyUI on the pod is responding."""
        try:
            req = urllib.request.Request(f"{self.comfyui_url}/system_stats")
            resp = urllib.request.urlopen(req, timeout=10)
            return resp.status == 200
        except Exception:
            return False

    def upload_file(self, local_path: str, remote_path: str) -> bool:
        """Upload a file to the pod via SCP."""
        try:
            result = subprocess.run(
                ["scp", "-o", "StrictHostKeyChecking=no",
                 local_path, f"root@{self.pod_ip}:{remote_path}"],
                capture_output=True, timeout=120,
            )
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Upload failed: {e}")
            return False

    def download_file(self, remote_path: str, local_path: str) -> bool:
        """Download a file from the pod via SCP."""
        try:
            result = subprocess.run(
                ["scp", "-o", "StrictHostKeyChecking=no",
                 f"root@{self.pod_ip}:{remote_path}", local_path],
                capture_output=True, timeout=120,
            )
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Download failed: {e}")
            return False

    def submit_workflow(self, workflow: dict) -> str | None:
        """Submit a ComfyUI workflow to the pod."""
        try:
            data = json.dumps({"prompt": workflow}).encode()
            req = urllib.request.Request(
                f"{self.comfyui_url}/prompt",
                data=data,
                headers={"Content-Type": "application/json"},
            )
            resp = urllib.request.urlopen(req, timeout=30)
            return json.loads(resp.read()).get("prompt_id")
        except Exception as e:
            logger.error(f"Workflow submission failed: {e}")
            return None

    async def poll_completion(self, prompt_id: str, timeout: int = 600) -> dict | None:
        """Poll for workflow completion."""
        start = time.time()
        while time.time() - start < timeout:
            try:
                url = f"{self.comfyui_url}/history/{prompt_id}"
                resp = urllib.request.urlopen(urllib.request.Request(url), timeout=10)
                history = json.loads(resp.read())
                if prompt_id in history:
                    status = history[prompt_id].get("status", {})
                    if status.get("completed", False):
                        return history[prompt_id]
                    if status.get("status_str") == "error":
                        logger.error(f"Workflow failed: {status}")
                        return None
            except Exception:
                pass
            await asyncio.sleep(5)
        logger.warning(f"Workflow {prompt_id} timed out after {timeout}s")
        return None

    async def generate_video(
        self,
        keyframe_path: str,
        prompt: str,
        negative: str = "low quality, blurry, distorted",
        lora_high: str | None = None,
        lora_low: str | None = None,
        lora_strength: float = 0.85,
        motion_tier: str = "medium",
        width: int = 480,
        height: int = 720,
        num_frames: int = 49,
        fps: int = 16,
        seed: int | None = None,
    ) -> str | None:
        """Generate a video on RunPod and download the result.

        Returns local path to downloaded video, or None on failure.
        """
        from packages.scene_generation.motion_intensity import get_motion_params

        params = get_motion_params(motion_tier)
        total_steps = params.total_steps
        split_steps = params.split_steps
        cfg = params.cfg

        if seed is None:
            import random
            seed = random.randint(0, 2**32)

        # Upload keyframe
        remote_input = f"/opt/ComfyUI/input/{Path(keyframe_path).name}"
        if not self.upload_file(keyframe_path, remote_input):
            logger.error("Failed to upload keyframe")
            return None

        # Build WAN 2.2 14B workflow (FP16 on A100 — full precision, LoRAs work natively)
        workflow = self._build_wan_workflow(
            ref_image=Path(keyframe_path).name,
            prompt=prompt,
            negative=negative,
            lora_high=lora_high,
            lora_low=lora_low,
            lora_strength=lora_strength,
            width=width, height=height,
            num_frames=num_frames, fps=fps,
            total_steps=total_steps, split_steps=split_steps,
            cfg=cfg, seed=seed,
        )

        # Submit
        prompt_id = self.submit_workflow(workflow)
        if not prompt_id:
            return None

        logger.info(f"Submitted to RunPod: {prompt_id}")

        # Poll
        result = await self.poll_completion(prompt_id, timeout=600)
        if not result:
            return None

        # Find output video in result
        remote_video = None
        for node_id, output in result.get("outputs", {}).items():
            gifs = output.get("gifs", [])
            for g in gifs:
                if g.get("filename", "").endswith(".mp4"):
                    remote_video = f"/opt/ComfyUI/output/{g['filename']}"
                    break
            if remote_video:
                break

        if not remote_video:
            logger.error("No video output found in result")
            return None

        # Download
        local_video = f"/opt/ComfyUI/output/runpod_{Path(remote_video).name}"
        if self.download_file(remote_video, local_video):
            logger.info(f"Downloaded: {local_video}")
            return local_video

        return None

    @staticmethod
    def _build_wan_workflow(
        ref_image, prompt, negative,
        lora_high, lora_low, lora_strength,
        width, height, num_frames, fps,
        total_steps, split_steps, cfg, seed,
    ) -> dict:
        """Build WAN 2.2 14B I2V workflow for A100 (FP16, no GGUF needed)."""
        w = {}
        nid = 1

        # On A100: use FP16 safetensors (80GB VRAM = no problem)
        h = str(nid); nid += 1
        w[h] = {"class_type": "UNETLoader", "inputs": {
            "unet_name": "wan2.2_i2v_high_noise_14B_fp16.safetensors",
            "weight_dtype": "default"}}

        l = str(nid); nid += 1
        w[l] = {"class_type": "UNETLoader", "inputs": {
            "unet_name": "wan2.2_i2v_low_noise_14B_fp16.safetensors",
            "weight_dtype": "default"}}

        h_model, h_slot = h, 0
        l_model, l_slot = l, 0

        # LoRAs (FP16 on A100 = full LoRA support)
        if lora_high:
            ln = str(nid); nid += 1
            w[ln] = {"class_type": "LoraLoaderModelOnly", "inputs": {
                "model": [h_model, h_slot],
                "lora_name": lora_high,
                "strength_model": lora_strength}}
            h_model, h_slot = ln, 0

        if lora_low:
            ln = str(nid); nid += 1
            w[ln] = {"class_type": "LoraLoaderModelOnly", "inputs": {
                "model": [l_model, l_slot],
                "lora_name": lora_low,
                "strength_model": lora_strength}}
            l_model, l_slot = ln, 0

        # ModelSamplingSD3 shift
        hs = str(nid); nid += 1
        w[hs] = {"class_type": "ModelSamplingSD3", "inputs": {"model": [h_model, h_slot], "shift": 8}}
        ls = str(nid); nid += 1
        w[ls] = {"class_type": "ModelSamplingSD3", "inputs": {"model": [l_model, l_slot], "shift": 8}}

        # CLIP + text
        clip = str(nid); nid += 1
        w[clip] = {"class_type": "CLIPLoader", "inputs": {
            "clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors", "type": "wan"}}
        pos = str(nid); nid += 1
        w[pos] = {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": [clip, 0]}}
        neg_n = str(nid); nid += 1
        w[neg_n] = {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": [clip, 0]}}

        # CLIP Vision
        cv = str(nid); nid += 1
        w[cv] = {"class_type": "CLIPVisionLoader", "inputs": {"clip_name": "clip_vision_h.safetensors"}}
        li = str(nid); nid += 1
        w[li] = {"class_type": "LoadImage", "inputs": {"image": ref_image}}
        cve = str(nid); nid += 1
        w[cve] = {"class_type": "CLIPVisionEncode", "inputs": {
            "clip_vision": [cv, 0], "image": [li, 0], "crop": "center"}}

        # VAE
        vae = str(nid); nid += 1
        w[vae] = {"class_type": "VAELoader", "inputs": {"vae_name": "wan_2.1_vae.safetensors"}}

        # WanImageToVideo
        i2v = str(nid); nid += 1
        w[i2v] = {"class_type": "WanImageToVideo", "inputs": {
            "positive": [pos, 0], "negative": [neg_n, 0], "vae": [vae, 0],
            "width": width, "height": height, "length": num_frames, "batch_size": 1,
            "clip_vision_output": [cve, 0], "start_image": [li, 0]}}

        # Dual KSampler
        kh = str(nid); nid += 1
        w[kh] = {"class_type": "KSamplerAdvanced", "inputs": {
            "model": [hs, 0], "positive": [i2v, 0], "negative": [i2v, 1],
            "latent_image": [i2v, 2], "seed": seed, "steps": total_steps, "cfg": cfg,
            "sampler_name": "euler", "scheduler": "simple",
            "start_at_step": 0, "end_at_step": split_steps,
            "add_noise": "enable", "return_with_leftover_noise": "enable", "noise_seed": seed}}
        kl = str(nid); nid += 1
        w[kl] = {"class_type": "KSamplerAdvanced", "inputs": {
            "model": [ls, 0], "positive": [i2v, 0], "negative": [i2v, 1],
            "latent_image": [kh, 0], "seed": seed, "steps": total_steps, "cfg": cfg,
            "sampler_name": "euler", "scheduler": "simple",
            "start_at_step": split_steps, "end_at_step": total_steps,
            "add_noise": "disable", "return_with_leftover_noise": "disable", "noise_seed": seed}}

        # Decode + save
        dec = str(nid); nid += 1
        w[dec] = {"class_type": "VAEDecode", "inputs": {"samples": [kl, 0], "vae": [vae, 0]}}
        vid = str(nid); nid += 1
        w[vid] = {"class_type": "VHS_VideoCombine", "inputs": {
            "images": [dec, 0], "frame_rate": fps, "loop_count": 0,
            "filename_prefix": "runpod_burst", "format": "video/h264-mp4",
            "pingpong": False, "save_output": True}}

        return w

    async def stop_pod(self) -> bool:
        """Stop the pod to save cost. Pod can be restarted later."""
        try:
            result = subprocess.run(
                ["runpodctl", "stop", "pod", self.pod_id],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0:
                logger.info(f"Stopped RunPod pod {self.pod_id}")
                return True
            logger.error(f"Failed to stop pod: {result.stderr}")
        except Exception as e:
            logger.error(f"Error stopping pod: {e}")
        return False

    async def get_queue_depth(self) -> int:
        """Get number of items in the pod's ComfyUI queue."""
        try:
            resp = urllib.request.urlopen(
                urllib.request.Request(f"{self.comfyui_url}/queue"), timeout=5,
            )
            data = json.loads(resp.read())
            running = len(data.get("queue_running", []))
            pending = len(data.get("queue_pending", []))
            return running + pending
        except Exception:
            return 0

    def estimated_cost(self, video_count: int) -> float:
        """Estimate cost for N video generations."""
        return video_count * EST_COST_PER_VIDEO
