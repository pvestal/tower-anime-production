"""Wan 2.1/2.2 Text-to-Video workflow builder.

Wan 2.1 1.3B is ideal for environment/establishing shots where no source image
exists. Uses native ComfyUI Wan nodes + GGUF loader for low-VRAM operation.

Wan 2.2 5B adds LoRA support (e.g. furry LoRAs) and I2V mode via
Wan22FunControlToVideo. Uses 48-channel VAE (different from 2.1's 16-channel).

Wan 2.2 14B I2V is the highest-quality option. Uses dual high/low noise models
with split-step sampling. Supports lightx2v distill LoRA for 4x speedup.
Uses 16-channel VAE (wan_2.1_vae, same as 2.1) + CLIP Vision for source images.

VRAM: ~8GB at FP16, ~4-6GB with GGUF Q4/Q8 quantization.
Speed: Faster than FramePack for short clips.

Model files needed in ComfyUI/models/:
  Wan 2.1:
    - unet/: Wan2.1-T2V-1.3B-Q8_0.gguf (GGUF, recommended)
             OR wan2.1_t2v_1.3B_fp16.safetensors (standard)
    - text_encoders/: umt5_xxl_fp8_e4m3fn_scaled.safetensors (UMT5-XXL, NOT T5-XXL)
    - vae/: wan_2.1_vae.safetensors
  Wan 2.2 5B:
    - unet/: Wan2.2-TI2V-5B-Q4_K_S.gguf (GGUF Q4, ~3.1GB)
    - text_encoders/: umt5_xxl_fp8_e4m3fn_scaled.safetensors (shared with 2.1)
    - vae/: wan2.2_vae.safetensors (48-channel, NOT compatible with 2.1)
  Wan 2.2 14B I2V:
    - unet/: Wan2.2-I2V-A14B-HighNoise-Q4_K_M.gguf (high noise model)
             Wan2.2-I2V-A14B-LowNoise-Q4_K_M.gguf (low noise model)
    - text_encoders/: umt5_xxl_fp8_e4m3fn_scaled.safetensors (shared)
    - clip_vision/: clip_vision_h.safetensors (CLIP-ViT-H for I2V)
    - vae/: wan_2.1_vae.safetensors (16-channel, same as 2.1!)
    - loras/ (optional): lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors
"""

import json
import logging
import time

from fastapi import APIRouter, HTTPException

from packages.core.config import COMFYUI_URL, COMFYUI_OUTPUT_DIR

logger = logging.getLogger(__name__)

router = APIRouter()

# Wan model filenames (GGUF preferred for 12GB VRAM)
WAN_MODELS = {
    # The T2V 1.3B model — standard safetensors
    "unet": "wan2.1_t2v_1.3B_fp16.safetensors",
    # Text encoder — UMT5-XXL (different from LTX's T5-XXL!)
    "text_encoder": "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
    # VAE
    "vae": "wan_2.1_vae.safetensors",
}

# GGUF model (recommended for 12GB VRAM)
WAN_GGUF_MODELS = {
    "unet": "Wan2.1-T2V-1.3B-Q8_0.gguf",
}

# Wan 2.2 models — 5B with 48-channel VAE (LoRA-compatible)
WAN22_MODELS = {
    "unet_gguf": "Wan2.2-TI2V-5B-Q4_K_S.gguf",
    "text_encoder": "umt5_xxl_fp8_e4m3fn_scaled.safetensors",  # shared with 2.1
    "vae": "wan2.2_vae.safetensors",  # 48-channel, NOT compatible with 2.1
}

# Wan 2.2 14B I2V — dual high/low noise models (16-channel VAE, uses wan_2.1_vae)
WAN22_14B_MODELS = {
    "unet_high": "Wan2.2-I2V-A14B-HighNoise-Q4_K_M.gguf",
    "unet_low": "Wan2.2-I2V-A14B-LowNoise-Q4_K_M.gguf",
    "text_encoder": "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
    "clip_vision": "clip_vision_h.safetensors",
    "vae": "wan_2.1_vae.safetensors",  # 16-channel! Same as Wan 2.1
    "lightx2v_lora": "lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors",
    "relight_lora": "WanAnimate_relight_lora_fp16.safetensors",
    "arcshot_lora": "wan22_arcshot_high.safetensors",
    "walking_lora": "kxsr_walking_anim_v1-5.safetensors",
}


def _submit_comfyui_workflow(workflow: dict) -> str:
    """Submit a workflow to ComfyUI and return the prompt_id."""
    import urllib.request
    payload = json.dumps({"prompt": workflow}).encode()
    req = urllib.request.Request(
        f"{COMFYUI_URL}/prompt",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req, timeout=30)
    result = json.loads(resp.read())
    return result.get("prompt_id", "")


def build_wan_t2v_workflow(
    prompt_text: str,
    width: int = 480,
    height: int = 720,
    num_frames: int = 81,
    fps: int = 16,
    steps: int = 20,
    cfg: float = 6.0,
    seed: int | None = None,
    negative_text: str = "low quality, blurry, distorted, watermark, text, ugly",
    use_gguf: bool = False,
    output_prefix: str | None = None,
) -> tuple[dict, str]:
    """Build a Wan 2.1 T2V ComfyUI workflow for environment/establishing shots.

    Returns (workflow_dict, output_prefix).

    Args:
        prompt_text: Scene description for video generation.
        width: Video width (multiple of 16). 480 is safe for 12GB.
        height: Video height (multiple of 16).
        num_frames: Number of frames (81 = ~5s at 16fps).
        fps: Output frame rate (Wan native is 16fps).
        steps: Sampling steps.
        cfg: CFG guidance scale.
        seed: Random seed, auto-generated if None.
        negative_text: Negative prompt.
        use_gguf: Use GGUF quantized model (lower VRAM, slightly lower quality).
    """
    import random as _random
    if seed is None:
        seed = _random.randint(0, 2**63 - 1)

    workflow = {}
    nid = 1

    # Node 1: Load model (GGUF or standard)
    if use_gguf:
        model_node = str(nid)
        workflow[model_node] = {
            "class_type": "UnetLoaderGGUF",
            "inputs": {
                "unet_name": WAN_GGUF_MODELS["unet"],
            },
        }
    else:
        model_node = str(nid)
        workflow[model_node] = {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": WAN_MODELS["unet"],
                "weight_dtype": "default",
            },
        }
    nid += 1

    # Node 2: ModelSamplingSD3 — required for Wan to set sigma scaling
    sampling_node = str(nid)
    workflow[sampling_node] = {
        "class_type": "ModelSamplingSD3",
        "inputs": {
            "model": [model_node, 0],
            "shift": 8,
        },
    }
    nid += 1

    # Node 3: Text encoder (UMT5-XXL — NOT the T5-XXL from LTX)
    clip_node = str(nid)
    workflow[clip_node] = {
        "class_type": "CLIPLoader",
        "inputs": {
            "clip_name": WAN_MODELS["text_encoder"],
            "type": "wan",
        },
    }
    nid += 1

    # Node 4: VAE
    vae_node = str(nid)
    workflow[vae_node] = {
        "class_type": "VAELoader",
        "inputs": {"vae_name": WAN_MODELS["vae"]},
    }
    nid += 1

    # Node 5: Positive CLIP encode
    pos_node = str(nid)
    workflow[pos_node] = {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": prompt_text, "clip": [clip_node, 0]},
    }
    nid += 1

    # Node 6: Negative CLIP encode
    neg_node = str(nid)
    workflow[neg_node] = {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": negative_text, "clip": [clip_node, 0]},
    }
    nid += 1

    # Node 7: Empty video latent (EmptyHunyuanLatentVideo, NOT EmptyLatentImage)
    latent_node = str(nid)
    workflow[latent_node] = {
        "class_type": "EmptyHunyuanLatentVideo",
        "inputs": {
            "width": width,
            "height": height,
            "length": num_frames,
            "batch_size": 1,
        },
    }
    nid += 1

    # Node 8: KSampler (uni_pc/simple as per official Wan workflow)
    sampler_node = str(nid)
    workflow[sampler_node] = {
        "class_type": "KSampler",
        "inputs": {
            "model": [sampling_node, 0],
            "positive": [pos_node, 0],
            "negative": [neg_node, 0],
            "latent_image": [latent_node, 0],
            "seed": seed,
            "steps": steps,
            "cfg": cfg,
            "sampler_name": "uni_pc",
            "scheduler": "simple",
            "denoise": 1.0,
        },
    }
    nid += 1

    # Node 9: VAE Decode
    decode_node = str(nid)
    workflow[decode_node] = {
        "class_type": "VAEDecode",
        "inputs": {
            "samples": [sampler_node, 0],
            "vae": [vae_node, 0],
        },
    }
    nid += 1

    # Node 10: VHS_VideoCombine (output MP4)
    ts = int(time.time())
    prefix = output_prefix or f"wan_{ts}"
    output_node = str(nid)
    workflow[output_node] = {
        "class_type": "VHS_VideoCombine",
        "inputs": {
            "images": [decode_node, 0],
            "frame_rate": fps,
            "loop_count": 0,
            "filename_prefix": prefix,
            "format": "video/h264-mp4",
            "pix_fmt": "yuv420p",
            "crf": 19,
            "save_metadata": True,
            "trim_to_audio": False,
            "pingpong": False,
            "save_output": True,
        },
    }

    return workflow, prefix


def build_wan22_workflow(
    prompt_text: str,
    width: int = 480,
    height: int = 720,
    num_frames: int = 81,
    fps: int = 16,
    steps: int = 20,
    cfg: float = 6.0,
    seed: int | None = None,
    negative_text: str = "low quality, blurry, distorted, watermark, text, ugly",
    output_prefix: str | None = None,
    lora_name: str | None = None,
    lora_strength: float = 0.8,
    ref_image: str | None = None,
) -> tuple[dict, str]:
    """Build a Wan 2.2 5B ComfyUI workflow with LoRA and optional I2V support.

    Uses Wan22FunControlToVideo for correct 48-channel latent generation.
    The node outputs (positive, negative, latent) so KSampler connects to its
    outputs rather than directly to CLIPTextEncode.

    Args:
        prompt_text: Scene description for video generation.
        width: Video width (multiple of 16). 480 default for 12GB VRAM.
        height: Video height (multiple of 16).
        num_frames: Number of frames (81 = ~5s at 16fps).
        fps: Output frame rate.
        steps: Sampling steps.
        cfg: CFG guidance scale.
        seed: Random seed, auto-generated if None.
        negative_text: Negative prompt.
        output_prefix: Filename prefix for output.
        lora_name: LoRA filename (in ComfyUI/models/loras/). None to skip.
        lora_strength: LoRA strength (0.0-1.0).
        ref_image: Reference image filename (in ComfyUI/input/) for I2V mode.
    """
    import random as _random
    if seed is None:
        seed = _random.randint(0, 2**63 - 1)

    workflow = {}
    nid = 1

    # --- Model loading chain ---

    # Node: UnetLoaderGGUF (Wan 2.2 5B Q4_K_S)
    unet_node = str(nid)
    workflow[unet_node] = {
        "class_type": "UnetLoaderGGUF",
        "inputs": {
            "unet_name": WAN22_MODELS["unet_gguf"],
        },
    }
    nid += 1

    # Current model output — may be overridden by LoRA
    model_out_node = unet_node
    model_out_slot = 0

    # Node: LoraLoaderModelOnly (optional — LoRA injection)
    if lora_name:
        lora_node = str(nid)
        workflow[lora_node] = {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "model": [model_out_node, model_out_slot],
                "lora_name": lora_name,
                "strength_model": lora_strength,
            },
        }
        model_out_node = lora_node
        model_out_slot = 0
        nid += 1

    # Node: ModelSamplingSD3 — sigma scaling for Wan
    sampling_node = str(nid)
    workflow[sampling_node] = {
        "class_type": "ModelSamplingSD3",
        "inputs": {
            "model": [model_out_node, model_out_slot],
            "shift": 8,
        },
    }
    nid += 1

    # --- Text encoding ---

    # Node: CLIPLoader (UMT5-XXL, shared with Wan 2.1)
    clip_node = str(nid)
    workflow[clip_node] = {
        "class_type": "CLIPLoader",
        "inputs": {
            "clip_name": WAN22_MODELS["text_encoder"],
            "type": "wan",
        },
    }
    nid += 1

    # Node: Positive CLIP encode
    pos_node = str(nid)
    workflow[pos_node] = {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": prompt_text, "clip": [clip_node, 0]},
    }
    nid += 1

    # Node: Negative CLIP encode
    neg_node = str(nid)
    workflow[neg_node] = {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": negative_text, "clip": [clip_node, 0]},
    }
    nid += 1

    # --- VAE ---

    vae_node = str(nid)
    workflow[vae_node] = {
        "class_type": "VAELoader",
        "inputs": {"vae_name": WAN22_MODELS["vae"]},
    }
    nid += 1

    # --- Latent generation via Wan22FunControlToVideo ---
    # This node reads vae.latent_channels dynamically (48 for Wan 2.2)
    # and outputs (positive, negative, latent) — wrapping the conditioning.

    fun_node = str(nid)
    fun_inputs = {
        "positive": [pos_node, 0],
        "negative": [neg_node, 0],
        "vae": [vae_node, 0],
        "width": width,
        "height": height,
        "length": num_frames,
        "batch_size": 1,
    }
    nid += 1

    # Optional: load reference image for I2V mode
    if ref_image:
        load_img_node = str(nid)
        workflow[load_img_node] = {
            "class_type": "LoadImage",
            "inputs": {"image": ref_image},
        }
        fun_inputs["ref_image"] = [load_img_node, 0]
        nid += 1

    workflow[fun_node] = {
        "class_type": "Wan22FunControlToVideo",
        "inputs": fun_inputs,
    }

    # --- Sampling ---
    # KSampler uses outputs from Wan22FunControlToVideo:
    #   slot 0 = positive conditioning, slot 1 = negative conditioning, slot 2 = latent

    sampler_node = str(nid)
    workflow[sampler_node] = {
        "class_type": "KSampler",
        "inputs": {
            "model": [sampling_node, 0],
            "positive": [fun_node, 0],
            "negative": [fun_node, 1],
            "latent_image": [fun_node, 2],
            "seed": seed,
            "steps": steps,
            "cfg": cfg,
            "sampler_name": "uni_pc",
            "scheduler": "simple",
            "denoise": 1.0,
        },
    }
    nid += 1

    # --- Decode + output ---

    decode_node = str(nid)
    workflow[decode_node] = {
        "class_type": "VAEDecode",
        "inputs": {
            "samples": [sampler_node, 0],
            "vae": [vae_node, 0],
        },
    }
    nid += 1

    ts = int(time.time())
    prefix = output_prefix or f"wan22_{ts}"
    output_node = str(nid)
    workflow[output_node] = {
        "class_type": "VHS_VideoCombine",
        "inputs": {
            "images": [decode_node, 0],
            "frame_rate": fps,
            "loop_count": 0,
            "filename_prefix": prefix,
            "format": "video/h264-mp4",
            "pix_fmt": "yuv420p",
            "crf": 19,
            "save_metadata": True,
            "trim_to_audio": False,
            "pingpong": False,
            "save_output": True,
        },
    }

    return workflow, prefix


def build_wan22_14b_i2v_workflow(
    prompt_text: str,
    ref_image: str,
    width: int = 480,
    height: int = 720,
    num_frames: int = 81,
    fps: int = 16,
    total_steps: int = 6,
    split_steps: int = 3,
    cfg: float = 3.5,
    seed: int | None = None,
    negative_text: str = "low quality, blurry, distorted, watermark, text, ugly",
    output_prefix: str | None = None,
    use_lightx2v: bool = True,
    motion_lora: str | None = None,
    motion_lora_strength: float = 0.8,
    content_lora_high: str | None = None,
    content_lora_low: str | None = None,
    content_lora_strength: float = 0.8,
) -> tuple[dict, str]:
    """Build a Wan 2.2 14B I2V ComfyUI workflow with dual high/low noise models.

    Uses split-step KSamplerAdvanced: first N steps with high noise model,
    remaining steps with low noise model. Supports lightx2v distill LoRA
    for 4x speedup and optional motion/camera LoRAs.

    The 14B I2V model uses the 16-channel VAE (wan_2.1_vae) + CLIP Vision
    for source image encoding — different from the 5B model which uses
    48-channel VAE.

    Args:
        prompt_text: Scene description for video generation.
        ref_image: Source image filename in ComfyUI/input/ (REQUIRED for I2V).
        width: Video width (multiple of 16). 480 safe for 12GB VRAM.
        height: Video height (multiple of 16).
        num_frames: Number of frames (81 = ~5s at 16fps).
        fps: Output frame rate.
        total_steps: Total sampling steps. With lightx2v: 4. Without: 6-8.
        split_steps: Steps for high noise model. With lightx2v: 2. Without: 3-4.
        cfg: CFG guidance scale. lightx2v uses 1.0. Standard uses 3.5.
        seed: Random seed, auto-generated if None.
        negative_text: Negative prompt.
        output_prefix: Filename prefix for output.
        use_lightx2v: Use lightx2v distill LoRA for 4x speed (changes steps/cfg).
        motion_lora: Optional motion/camera LoRA filename (applied to high noise model).
        motion_lora_strength: Strength for motion LoRA (0.0-1.0).
        content_lora_high: Optional content LoRA for high noise model (e.g. wan22_cowgirl_HIGH).
        content_lora_low: Optional content LoRA for low noise model (e.g. wan22_cowgirl_LOW).
        content_lora_strength: Strength for content LoRAs (0.0-1.0).
    """
    import random as _random
    if seed is None:
        seed = _random.randint(0, 2**63 - 1)

    # Note: lightx2v step/cfg overrides are now handled by the motion_intensity
    # system in builder.py. Callers pass explicit steps/split/cfg values.
    # Legacy callers using defaults (6/3/3.5) with use_lightx2v=True get
    # the standard lightx2v speedup.
    if use_lightx2v and total_steps == 6 and split_steps == 3 and cfg == 3.5:
        total_steps = 4
        split_steps = 2
        cfg = 1.0

    workflow = {}
    nid = 1

    # --- Load dual models ---

    # High noise model (GGUF)
    high_unet_node = str(nid)
    workflow[high_unet_node] = {
        "class_type": "UnetLoaderGGUF",
        "inputs": {"unet_name": WAN22_14B_MODELS["unet_high"]},
    }
    nid += 1

    # Low noise model (GGUF)
    low_unet_node = str(nid)
    workflow[low_unet_node] = {
        "class_type": "UnetLoaderGGUF",
        "inputs": {"unet_name": WAN22_14B_MODELS["unet_low"]},
    }
    nid += 1

    # Track model output chains (may have LoRAs applied)
    high_model_node, high_model_slot = high_unet_node, 0
    low_model_node, low_model_slot = low_unet_node, 0

    # --- Optional: lightx2v distill LoRA (applied to BOTH models) ---

    if use_lightx2v:
        from pathlib import Path
        lightx2v_path = Path("/opt/ComfyUI/models/loras") / WAN22_14B_MODELS["lightx2v_lora"]
        if lightx2v_path.exists():
            # Apply to high noise model
            lora_high_node = str(nid)
            workflow[lora_high_node] = {
                "class_type": "LoraLoaderModelOnly",
                "inputs": {
                    "model": [high_model_node, high_model_slot],
                    "lora_name": WAN22_14B_MODELS["lightx2v_lora"],
                    "strength_model": 1.0,
                },
            }
            high_model_node, high_model_slot = lora_high_node, 0
            nid += 1

            # Apply to low noise model
            lora_low_node = str(nid)
            workflow[lora_low_node] = {
                "class_type": "LoraLoaderModelOnly",
                "inputs": {
                    "model": [low_model_node, low_model_slot],
                    "lora_name": WAN22_14B_MODELS["lightx2v_lora"],
                    "strength_model": 1.0,
                },
            }
            low_model_node, low_model_slot = lora_low_node, 0
            nid += 1
        else:
            logger.warning("lightx2v LoRA not found, running without acceleration")

    # --- DR34ML4Y I2V LoRA (applied to low noise model for anime style preservation) ---
    # Skip for photorealistic/live-action content — the anime LoRA fights realism

    from pathlib import Path as _P
    _prompt_lower = prompt_text.lower()
    _is_photorealistic = any(kw in _prompt_lower for kw in (
        "photorealistic", "live action", "realistic", "real photo", "photography",
    ))
    _dr34mlay_path = _P("/opt/ComfyUI/models/loras/DR34ML4Y_I2V_14B_LOW_V2.safetensors")
    if _dr34mlay_path.exists() and not _is_photorealistic:
        dr34mlay_node = str(nid)
        workflow[dr34mlay_node] = {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "model": [low_model_node, low_model_slot],
                "lora_name": "DR34ML4Y_I2V_14B_LOW_V2.safetensors",
                "strength_model": 0.6,
            },
        }
        low_model_node, low_model_slot = dr34mlay_node, 0
        nid += 1
        logger.info("Wan22 14B: DR34ML4Y anime style LoRA applied to low noise model @ 0.6")
    elif _is_photorealistic:
        logger.info("Wan22 14B: DR34ML4Y skipped (photorealistic content detected)")

    # --- Optional: motion/camera LoRA (applied to high noise model only) ---

    if motion_lora:
        motion_lora_node = str(nid)
        workflow[motion_lora_node] = {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "model": [high_model_node, high_model_slot],
                "lora_name": motion_lora,
                "strength_model": motion_lora_strength,
            },
        }
        high_model_node, high_model_slot = motion_lora_node, 0
        nid += 1

    # --- Optional: content LoRA pair (HIGH on high noise, LOW on low noise) ---

    if content_lora_high:
        _clh_path = _P(f"/opt/ComfyUI/models/loras/{content_lora_high}")
        if not _clh_path.exists():
            _clh_path = _P(f"/opt/ComfyUI/models/loras/wan22_nsfw/{content_lora_high}")
        if _clh_path.exists():
            _clh_node = str(nid)
            # Use path relative to loras dir
            _clh_name = str(_clh_path.relative_to(_P("/opt/ComfyUI/models/loras")))
            workflow[_clh_node] = {
                "class_type": "LoraLoaderModelOnly",
                "inputs": {
                    "model": [high_model_node, high_model_slot],
                    "lora_name": _clh_name,
                    "strength_model": content_lora_strength,
                },
            }
            high_model_node, high_model_slot = _clh_node, 0
            nid += 1
            logger.info(f"Wan22 14B: content LoRA HIGH '{_clh_name}' applied @ {content_lora_strength}")
        else:
            logger.warning(f"Content LoRA HIGH not found: {content_lora_high}")

    if content_lora_low:
        _cll_path = _P(f"/opt/ComfyUI/models/loras/{content_lora_low}")
        if not _cll_path.exists():
            _cll_path = _P(f"/opt/ComfyUI/models/loras/wan22_nsfw/{content_lora_low}")
        if _cll_path.exists():
            _cll_node = str(nid)
            _cll_name = str(_cll_path.relative_to(_P("/opt/ComfyUI/models/loras")))
            workflow[_cll_node] = {
                "class_type": "LoraLoaderModelOnly",
                "inputs": {
                    "model": [low_model_node, low_model_slot],
                    "lora_name": _cll_name,
                    "strength_model": content_lora_strength,
                },
            }
            low_model_node, low_model_slot = _cll_node, 0
            nid += 1
            logger.info(f"Wan22 14B: content LoRA LOW '{_cll_name}' applied @ {content_lora_strength}")
        else:
            logger.warning(f"Content LoRA LOW not found: {content_lora_low}")

    # --- ModelSamplingSD3 for sigma scaling ---

    high_sampling_node = str(nid)
    workflow[high_sampling_node] = {
        "class_type": "ModelSamplingSD3",
        "inputs": {"model": [high_model_node, high_model_slot], "shift": 8},
    }
    nid += 1

    low_sampling_node = str(nid)
    workflow[low_sampling_node] = {
        "class_type": "ModelSamplingSD3",
        "inputs": {"model": [low_model_node, low_model_slot], "shift": 8},
    }
    nid += 1

    # --- Text encoding ---

    clip_node = str(nid)
    workflow[clip_node] = {
        "class_type": "CLIPLoader",
        "inputs": {"clip_name": WAN22_14B_MODELS["text_encoder"], "type": "wan"},
    }
    nid += 1

    pos_node = str(nid)
    workflow[pos_node] = {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": prompt_text, "clip": [clip_node, 0]},
    }
    nid += 1

    neg_node = str(nid)
    workflow[neg_node] = {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": negative_text, "clip": [clip_node, 0]},
    }
    nid += 1

    # --- CLIP Vision (for I2V source image encoding) ---

    clip_vision_node = str(nid)
    workflow[clip_vision_node] = {
        "class_type": "CLIPVisionLoader",
        "inputs": {"clip_name": WAN22_14B_MODELS["clip_vision"]},
    }
    nid += 1

    load_img_node = str(nid)
    workflow[load_img_node] = {
        "class_type": "LoadImage",
        "inputs": {"image": ref_image},
    }
    nid += 1

    clip_vision_encode_node = str(nid)
    workflow[clip_vision_encode_node] = {
        "class_type": "CLIPVisionEncode",
        "inputs": {
            "clip_vision": [clip_vision_node, 0],
            "image": [load_img_node, 0],
            "crop": "center",
        },
    }
    nid += 1

    # --- VAE (16-channel, same as Wan 2.1) ---

    vae_node = str(nid)
    workflow[vae_node] = {
        "class_type": "VAELoader",
        "inputs": {"vae_name": WAN22_14B_MODELS["vae"]},
    }
    nid += 1

    # --- WanImageToVideo (conditioning + latent generation) ---

    i2v_node = str(nid)
    workflow[i2v_node] = {
        "class_type": "WanImageToVideo",
        "inputs": {
            "positive": [pos_node, 0],
            "negative": [neg_node, 0],
            "vae": [vae_node, 0],
            "width": width,
            "height": height,
            "length": num_frames,
            "batch_size": 1,
            "clip_vision_output": [clip_vision_encode_node, 0],
            "start_image": [load_img_node, 0],
        },
    }
    nid += 1

    # --- Dual KSamplerAdvanced (split-step sampling) ---

    # Pass 1: High noise model (steps 0 → split_steps)
    sampler_high_node = str(nid)
    workflow[sampler_high_node] = {
        "class_type": "KSamplerAdvanced",
        "inputs": {
            "model": [high_sampling_node, 0],
            "positive": [i2v_node, 0],
            "negative": [i2v_node, 1],
            "latent_image": [i2v_node, 2],
            "seed": seed,
            "steps": total_steps,
            "cfg": cfg,
            "sampler_name": "euler",
            "scheduler": "simple",
            "start_at_step": 0,
            "end_at_step": split_steps,
            "add_noise": "enable",
            "return_with_leftover_noise": "enable",
            "noise_seed": seed,
        },
    }
    nid += 1

    # Pass 2: Low noise model (steps split_steps → total_steps)
    sampler_low_node = str(nid)
    workflow[sampler_low_node] = {
        "class_type": "KSamplerAdvanced",
        "inputs": {
            "model": [low_sampling_node, 0],
            "positive": [i2v_node, 0],
            "negative": [i2v_node, 1],
            "latent_image": [sampler_high_node, 0],
            "seed": seed,
            "steps": total_steps,
            "cfg": cfg,
            "sampler_name": "euler",
            "scheduler": "simple",
            "start_at_step": split_steps,
            "end_at_step": total_steps,
            "add_noise": "disable",
            "return_with_leftover_noise": "disable",
            "noise_seed": seed,
        },
    }
    nid += 1

    # --- Decode + output ---

    decode_node = str(nid)
    workflow[decode_node] = {
        "class_type": "VAEDecode",
        "inputs": {
            "samples": [sampler_low_node, 0],
            "vae": [vae_node, 0],
        },
    }
    nid += 1

    ts = int(time.time())
    prefix = output_prefix or f"wan22_14b_{ts}"
    output_node = str(nid)
    workflow[output_node] = {
        "class_type": "VHS_VideoCombine",
        "inputs": {
            "images": [decode_node, 0],
            "frame_rate": fps,
            "loop_count": 0,
            "filename_prefix": prefix,
            "format": "video/h264-mp4",
            "pix_fmt": "yuv420p",
            "crf": 19,
            "save_metadata": True,
            "trim_to_audio": False,
            "pingpong": False,
            "save_output": True,
        },
    }

    return workflow, prefix


def check_wan22_14b_ready() -> tuple[bool, str]:
    """Check if Wan 2.2 14B I2V models are available."""
    from pathlib import Path
    base = Path("/opt/ComfyUI/models")
    missing = []
    for key in ("unet_high", "unet_low"):
        if not (base / "unet" / WAN22_14B_MODELS[key]).exists():
            missing.append(f"{key}: {WAN22_14B_MODELS[key]}")
    if not (base / "text_encoders" / WAN22_14B_MODELS["text_encoder"]).exists():
        missing.append(f"text_encoder: {WAN22_14B_MODELS['text_encoder']}")
    if not (base / "clip_vision" / WAN22_14B_MODELS["clip_vision"]).exists():
        # Also check alternative name
        alt = base / "clip_vision" / "CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors"
        if not alt.exists():
            missing.append(f"clip_vision: {WAN22_14B_MODELS['clip_vision']}")
    if not (base / "vae" / WAN22_14B_MODELS["vae"]).exists():
        missing.append(f"vae: {WAN22_14B_MODELS['vae']}")
    if missing:
        return False, f"Missing Wan 2.2 14B models: {', '.join(missing)}"
    return True, "All Wan 2.2 14B I2V models available"


def check_wan_models_available() -> dict:
    """Check which Wan model files are present in ComfyUI directories."""
    from pathlib import Path
    base = Path("/opt/ComfyUI/models")

    # Each model type → list of directories to check
    search_dirs = {
        "unet": ["diffusion_models", "unet"],
        "text_encoder": ["text_encoders", "clip"],
        "vae": ["vae"],
    }

    status = {}
    for key, filename in WAN_MODELS.items():
        dirs = search_dirs.get(key, ["diffusion_models", "unet", "text_encoders", "clip", "vae"])
        found = any((base / d / filename).exists() for d in dirs)
        status[key] = {"filename": filename, "available": found}

    # GGUF unet (Wan 2.1)
    gguf_found = any(
        (base / d / WAN_GGUF_MODELS["unet"]).exists()
        for d in ["diffusion_models", "unet"]
    )
    status["unet_gguf"] = {
        "filename": WAN_GGUF_MODELS["unet"],
        "available": gguf_found,
    }

    # Wan 2.2 models
    wan22_unet_found = any(
        (base / d / WAN22_MODELS["unet_gguf"]).exists()
        for d in ["diffusion_models", "unet"]
    )
    status["wan22_unet_gguf"] = {
        "filename": WAN22_MODELS["unet_gguf"],
        "available": wan22_unet_found,
    }
    wan22_vae_found = (base / "vae" / WAN22_MODELS["vae"]).exists()
    status["wan22_vae"] = {
        "filename": WAN22_MODELS["vae"],
        "available": wan22_vae_found,
    }
    return status


def check_wan22_ready() -> tuple[bool, str]:
    """Check if all Wan 2.2 models are available. Returns (ready, message)."""
    status = check_wan_models_available()
    missing = []
    if not status["wan22_unet_gguf"]["available"]:
        missing.append(f"unet: {WAN22_MODELS['unet_gguf']}")
    if not status["text_encoder"]["available"]:
        missing.append(f"text_encoder: {WAN22_MODELS['text_encoder']}")
    if not status["wan22_vae"]["available"]:
        missing.append(f"vae: {WAN22_MODELS['vae']}")
    if missing:
        return False, f"Missing Wan 2.2 models: {', '.join(missing)}"
    return True, "All Wan 2.2 models available"


@router.get("/generate/wan/models")
async def check_wan_models():
    """Check availability of all Wan model files (2.1, 2.2 5B, 2.2 14B)."""
    status = check_wan_models_available()
    all_ready = all(v["available"] for k, v in status.items() if k not in ("unet_gguf", "wan22_unet_gguf", "wan22_vae"))
    gguf_ready = (
        status["unet_gguf"]["available"]
        and status["text_encoder"]["available"]
        and status["vae"]["available"]
    )
    wan22_ready, wan22_msg = check_wan22_ready()
    wan22_14b_ready, wan22_14b_msg = check_wan22_14b_ready()

    # Check LoRA availability
    lora_status = {}
    for key in ("lightx2v_lora", "relight_lora", "arcshot_lora", "walking_lora"):
        lora_path = Path("/opt/ComfyUI/models/loras") / WAN22_14B_MODELS.get(key, "")
        lora_status[key] = {
            "filename": WAN22_14B_MODELS.get(key, ""),
            "available": lora_path.exists() and lora_path.stat().st_size > 0,
        }

    return {
        "models": status,
        "standard_ready": all_ready,
        "gguf_ready": gguf_ready,
        "wan22_ready": wan22_ready,
        "wan22_message": wan22_msg,
        "wan22_14b_ready": wan22_14b_ready,
        "wan22_14b_message": wan22_14b_msg,
        "motion_loras": lora_status,
        "download_instructions": {
            "unet_gguf": "wget -O /opt/ComfyUI/models/unet/Wan2.1-T2V-1.3B-Q8_0.gguf https://huggingface.co/samuelchristlie/Wan2.1-T2V-1.3B-GGUF/resolve/main/Wan2.1-T2V-1.3B-Q8_0.gguf",
            "vae": "wget -O /opt/ComfyUI/models/vae/wan_2.1_vae.safetensors https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/vae/wan_2.1_vae.safetensors",
            "text_encoder": "wget -O /opt/ComfyUI/models/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors",
            "wan22_unet_gguf": "wget -O /opt/ComfyUI/models/unet/Wan2.2-TI2V-5B-Q4_K_S.gguf https://huggingface.co/QuantStack/Wan2.2-TI2V-5B-GGUF/resolve/main/Wan2.2-TI2V-5B-Q4_K_S.gguf",
            "wan22_vae": "wget -O /opt/ComfyUI/models/vae/wan2.2_vae.safetensors https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/vae/wan2.2_vae.safetensors",
            "wan22_14b_high": "wget -O /opt/ComfyUI/models/unet/Wan2.2-I2V-A14B-HighNoise-Q4_K_M.gguf https://huggingface.co/QuantStack/Wan2.2-I2V-A14B-GGUF/resolve/main/HighNoise/Wan2.2-I2V-A14B-HighNoise-Q4_K_M.gguf",
            "wan22_14b_low": "wget -O /opt/ComfyUI/models/unet/Wan2.2-I2V-A14B-LowNoise-Q4_K_M.gguf https://huggingface.co/QuantStack/Wan2.2-I2V-A14B-GGUF/resolve/main/LowNoise/Wan2.2-I2V-A14B-LowNoise-Q4_K_M.gguf",
            "civitai_models": "/opt/ComfyUI/download_civitai_models.sh",
        },
    }


@router.post("/generate/wan")
async def generate_wan_video(
    prompt: str,
    width: int = 480,
    height: int = 720,
    num_frames: int = 81,
    fps: int = 16,
    steps: int = 20,
    cfg: float = 6.0,
    seed: int | None = None,
    use_gguf: bool = True,
):
    """Generate a Wan T2V environment video (no source image needed)."""
    status = check_wan_models_available()
    if use_gguf and not status["unet_gguf"]["available"]:
        raise HTTPException(status_code=503, detail="Wan GGUF model not downloaded. GET /generate/wan/models for instructions.")
    if not use_gguf and not status["unet"]["available"]:
        raise HTTPException(status_code=503, detail="Wan model not downloaded. GET /generate/wan/models for instructions.")
    if not status["text_encoder"]["available"]:
        raise HTTPException(status_code=503, detail="T5-XXL text encoder not found.")

    workflow, prefix = build_wan_t2v_workflow(
        prompt_text=prompt,
        width=width,
        height=height,
        num_frames=num_frames,
        fps=fps,
        steps=steps,
        cfg=cfg,
        seed=seed,
        use_gguf=use_gguf,
    )

    try:
        prompt_id = _submit_comfyui_workflow(workflow)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"ComfyUI submission failed: {e}")

    seconds = num_frames / fps

    return {
        "prompt_id": prompt_id,
        "engine": "wan-t2v-1.3b" + ("-gguf" if use_gguf else ""),
        "mode": "t2v",
        "seconds": round(seconds, 1),
        "resolution": f"{width}x{height}",
        "prefix": prefix,
    }


@router.post("/generate/wan22")
async def generate_wan22_video(
    prompt: str,
    width: int = 480,
    height: int = 720,
    num_frames: int = 81,
    fps: int = 16,
    steps: int = 20,
    cfg: float = 6.0,
    seed: int | None = None,
    lora_name: str | None = None,
    lora_strength: float = 0.8,
    ref_image: str | None = None,
):
    """Generate a Wan 2.2 5B video with optional LoRA and I2V mode."""
    ready, msg = check_wan22_ready()
    if not ready:
        raise HTTPException(status_code=503, detail=msg + ". GET /generate/wan/models for instructions.")

    if lora_name:
        from pathlib import Path
        lora_path = Path("/opt/ComfyUI/models/loras") / lora_name
        if not lora_path.exists():
            raise HTTPException(status_code=404, detail=f"LoRA not found: {lora_name}")

    workflow, prefix = build_wan22_workflow(
        prompt_text=prompt,
        width=width,
        height=height,
        num_frames=num_frames,
        fps=fps,
        steps=steps,
        cfg=cfg,
        seed=seed,
        lora_name=lora_name,
        lora_strength=lora_strength,
        ref_image=ref_image,
    )

    try:
        prompt_id = _submit_comfyui_workflow(workflow)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"ComfyUI submission failed: {e}")

    seconds = num_frames / fps
    mode = "i2v" if ref_image else "t2v"

    return {
        "prompt_id": prompt_id,
        "engine": "wan22-5b-gguf",
        "mode": mode,
        "lora": lora_name,
        "seconds": round(seconds, 1),
        "resolution": f"{width}x{height}",
        "prefix": prefix,
    }


@router.post("/generate/wan22-14b")
async def generate_wan22_14b_video(
    prompt: str,
    ref_image: str,
    width: int = 480,
    height: int = 720,
    num_frames: int = 81,
    fps: int = 16,
    total_steps: int = 6,
    split_steps: int = 3,
    cfg: float = 3.5,
    seed: int | None = None,
    use_lightx2v: bool = True,
    motion_lora: str | None = None,
    motion_lora_strength: float = 0.8,
    content_lora_high: str | None = None,
    content_lora_low: str | None = None,
    content_lora_strength: float = 0.85,
):
    """Generate a Wan 2.2 14B I2V video with dual high/low noise models.

    Highest quality video generation. Supports:
    - lightx2v distill LoRA for 4x speed (default on)
    - Optional motion/camera LoRAs (arcshot, relight, etc.)
    - Requires source image (I2V only)
    """
    ready, msg = check_wan22_14b_ready()
    if not ready:
        raise HTTPException(status_code=503, detail=msg + ". GET /generate/wan/models for instructions.")

    if motion_lora:
        lora_path = Path("/opt/ComfyUI/models/loras") / motion_lora
        if not lora_path.exists():
            raise HTTPException(status_code=404, detail=f"Motion LoRA not found: {motion_lora}")

    workflow, prefix = build_wan22_14b_i2v_workflow(
        prompt_text=prompt,
        ref_image=ref_image,
        width=width,
        height=height,
        num_frames=num_frames,
        fps=fps,
        total_steps=total_steps,
        split_steps=split_steps,
        cfg=cfg,
        seed=seed,
        use_lightx2v=use_lightx2v,
        motion_lora=motion_lora,
        motion_lora_strength=motion_lora_strength,
        content_lora_high=content_lora_high,
        content_lora_low=content_lora_low,
        content_lora_strength=content_lora_strength,
    )

    try:
        prompt_id = _submit_comfyui_workflow(workflow)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"ComfyUI submission failed: {e}")

    seconds = num_frames / fps

    return {
        "prompt_id": prompt_id,
        "engine": "wan22-14b-i2v-gguf",
        "mode": "i2v",
        "lightx2v": use_lightx2v,
        "motion_lora": motion_lora,
        "steps": f"{total_steps} total ({split_steps} high + {total_steps - split_steps} low)",
        "seconds": round(seconds, 1),
        "resolution": f"{width}x{height}",
        "prefix": prefix,
    }


@router.post("/generate/wan22-14b/roll-forward")
async def generate_wan22_14b_roll_forward(
    prompt: str,
    ref_image: str,
    target_seconds: float = 15.0,
    segment_seconds: float = 5.0,
    crossfade_seconds: float = 0.3,
    width: int = 480,
    height: int = 720,
    fps: int = 16,
    steps: int = 4,
    seed: int | None = None,
    use_lightx2v: bool = True,
    motion_lora: str | None = None,
    motion_lora_strength: float = 0.8,
):
    """Generate a long WAN 2.2 14B video by chaining segments (Pattern C).

    Generates multiple 5s clips, extracts last frame from each to seed the next,
    then crossfade-stitches them into one continuous video.
    """
    ready, msg = check_wan22_14b_ready()
    if not ready:
        raise HTTPException(status_code=503, detail=msg)

    from .builder import roll_forward_wan_shot

    result = await roll_forward_wan_shot(
        prompt_text=prompt,
        ref_image=ref_image,
        target_seconds=target_seconds,
        segment_seconds=segment_seconds,
        crossfade_seconds=crossfade_seconds,
        width=width, height=height,
        fps=fps, steps=steps, seed=seed,
        output_prefix=f"rollforward_{int(__import__('time').time())}",
        use_lightx2v=use_lightx2v,
        motion_lora=motion_lora,
        motion_lora_strength=motion_lora_strength,
    )

    if not result["video_path"]:
        raise HTTPException(status_code=500, detail="Roll-forward failed — no segments completed")

    return {
        "engine": "wan22-14b-roll-forward",
        "video_path": result["video_path"],
        "last_frame": result["last_frame"],
        "segments": result["segment_count"],
        "total_duration": round(result["total_duration"], 1),
        "target_seconds": target_seconds,
        "resolution": f"{width}x{height}",
    }
def build_dasiwa_i2v_workflow(
    prompt_text: str,
    ref_image: str,
    width: int = 480,
    height: int = 720,
    num_frames: int = 81,
    fps: int = 16,
    total_steps: int = 4,
    split_steps: int = 2,
    cfg: float = 1.0,
    seed: int | None = None,
    negative_text: str = "low quality, blurry, distorted, watermark, text, ugly",
    output_prefix: str | None = None,
    motion_lora: str | None = None,
    motion_lora_strength: float = 0.6,
    content_lora_high: str | None = None,
    content_lora_low: str | None = None,
    content_lora_strength: float = 0.6,
    skip_junk_frames: int = 6,
) -> tuple[dict, str]:
    """Build a DaSiWa TastySin v8 I2V workflow.

    Same dual-model architecture as vanilla Wan 2.2 14B but with pre-baked
    lightx2v distillation — no speed LoRA needed. Uses lower LoRA strengths
    (0.3-0.6) since the merge already bakes in quality improvements.

    Key differences from build_wan22_14b_i2v_workflow:
    - No lightx2v LoRA (distillation is baked in)
    - No DR34ML4Y style LoRA (TastySin has its own style baked in)
    - Lower LoRA strengths recommended (0.3-0.6 vs 0.8-1.0)
    - CFG=1 always, 4 steps always
    - Optional junk frame stripping (first N frames are often garbage)
    """
    import random as _random
    if seed is None:
        seed = _random.randint(0, 2**63 - 1)

    workflow = {}
    nid = 1

    # --- Load dual DaSiWa models ---

    high_unet_node = str(nid)
    workflow[high_unet_node] = {
        "class_type": "UnetLoaderGGUF",
        "inputs": {"unet_name": DASIWA_MODELS["unet_high"]},
    }
    nid += 1

    low_unet_node = str(nid)
    workflow[low_unet_node] = {
        "class_type": "UnetLoaderGGUF",
        "inputs": {"unet_name": DASIWA_MODELS["unet_low"]},
    }
    nid += 1

    high_model_node, high_model_slot = high_unet_node, 0
    low_model_node, low_model_slot = low_unet_node, 0

    # --- Optional: motion/camera LoRA (high noise model only, 0.3-0.6) ---

    if motion_lora:
        motion_lora_node = str(nid)
        workflow[motion_lora_node] = {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "model": [high_model_node, high_model_slot],
                "lora_name": motion_lora,
                "strength_model": min(motion_lora_strength, 0.6),
            },
        }
        high_model_node, high_model_slot = motion_lora_node, 0
        nid += 1

    # --- Optional: content LoRA pair (lower strength for DaSiWa) ---

    from pathlib import Path as _P

    # General NSFW LoRA stack (if content LoRA is present and isn't already the general NSFW LoRA)
    _nsfw_general_high = _P("/opt/ComfyUI/models/loras/wan22_nsfw/wan22_general_nsfw_v08_HIGH.safetensors")
    _nsfw_general_low = _P("/opt/ComfyUI/models/loras/wan22_nsfw/wan22_general_nsfw_v08_LOW.safetensors")
    _content_is_general = content_lora_high and "general_nsfw" in (content_lora_high or "")
    if content_lora_high and not _content_is_general and _nsfw_general_high.exists():
        _ngh_node = str(nid)
        workflow[_ngh_node] = {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "model": [high_model_node, high_model_slot],
                "lora_name": "wan22_nsfw/wan22_general_nsfw_v08_HIGH.safetensors",
                "strength_model": 0.35,
            },
        }
        high_model_node, high_model_slot = _ngh_node, 0
        nid += 1
        if _nsfw_general_low.exists():
            _ngl_node = str(nid)
            workflow[_ngl_node] = {
                "class_type": "LoraLoaderModelOnly",
                "inputs": {
                    "model": [low_model_node, low_model_slot],
                    "lora_name": "wan22_nsfw/wan22_general_nsfw_v08_LOW.safetensors",
                    "strength_model": 0.35,
                },
            }
            low_model_node, low_model_slot = _ngl_node, 0
            nid += 1

    if content_lora_high:
        _clh_path = _P(f"/opt/ComfyUI/models/loras/{content_lora_high}")
        if not _clh_path.exists():
            _clh_path = _P(f"/opt/ComfyUI/models/loras/wan22_nsfw/{content_lora_high}")
        if _clh_path.exists():
            _clh_name = str(_clh_path.relative_to(_P("/opt/ComfyUI/models/loras")))
            _clh_node = str(nid)
            workflow[_clh_node] = {
                "class_type": "LoraLoaderModelOnly",
                "inputs": {
                    "model": [high_model_node, high_model_slot],
                    "lora_name": _clh_name,
                    "strength_model": min(content_lora_strength, 0.6),
                },
            }
            high_model_node, high_model_slot = _clh_node, 0
            nid += 1
            logger.info(f"DaSiWa: content LoRA HIGH '{_clh_name}' @ {min(content_lora_strength, 0.6)}")

    if content_lora_low:
        _cll_path = _P(f"/opt/ComfyUI/models/loras/{content_lora_low}")
        if not _cll_path.exists():
            _cll_path = _P(f"/opt/ComfyUI/models/loras/wan22_nsfw/{content_lora_low}")
        if _cll_path.exists():
            _cll_name = str(_cll_path.relative_to(_P("/opt/ComfyUI/models/loras")))
            _cll_node = str(nid)
            workflow[_cll_node] = {
                "class_type": "LoraLoaderModelOnly",
                "inputs": {
                    "model": [low_model_node, low_model_slot],
                    "lora_name": _cll_name,
                    "strength_model": min(content_lora_strength, 0.6),
                },
            }
            low_model_node, low_model_slot = _cll_node, 0
            nid += 1

    # --- ModelSamplingSD3 ---

    high_sampling_node = str(nid)
    workflow[high_sampling_node] = {
        "class_type": "ModelSamplingSD3",
        "inputs": {"model": [high_model_node, high_model_slot], "shift": 8},
    }
    nid += 1

    low_sampling_node = str(nid)
    workflow[low_sampling_node] = {
        "class_type": "ModelSamplingSD3",
        "inputs": {"model": [low_model_node, low_model_slot], "shift": 8},
    }
    nid += 1

    # --- Text encoding ---

    clip_node = str(nid)
    workflow[clip_node] = {
        "class_type": "CLIPLoader",
        "inputs": {"clip_name": WAN22_14B_MODELS["text_encoder"], "type": "wan"},
    }
    nid += 1

    pos_node = str(nid)
    workflow[pos_node] = {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": prompt_text, "clip": [clip_node, 0]},
    }
    nid += 1

    neg_node = str(nid)
    workflow[neg_node] = {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": negative_text, "clip": [clip_node, 0]},
    }
    nid += 1

    # --- CLIP Vision ---

    clip_vision_node = str(nid)
    workflow[clip_vision_node] = {
        "class_type": "CLIPVisionLoader",
        "inputs": {"clip_name": WAN22_14B_MODELS["clip_vision"]},
    }
    nid += 1

    load_img_node = str(nid)
    workflow[load_img_node] = {
        "class_type": "LoadImage",
        "inputs": {"image": ref_image},
    }
    nid += 1

    clip_vision_encode_node = str(nid)
    workflow[clip_vision_encode_node] = {
        "class_type": "CLIPVisionEncode",
        "inputs": {
            "clip_vision": [clip_vision_node, 0],
            "image": [load_img_node, 0],
            "crop": "center",
        },
    }
    nid += 1

    # --- VAE (16-channel, same as Wan 2.1) ---

    vae_node = str(nid)
    workflow[vae_node] = {
        "class_type": "VAELoader",
        "inputs": {"vae_name": WAN22_14B_MODELS["vae"]},
    }
    nid += 1

    # --- WanImageToVideo ---

    i2v_node = str(nid)
    workflow[i2v_node] = {
        "class_type": "WanImageToVideo",
        "inputs": {
            "positive": [pos_node, 0],
            "negative": [neg_node, 0],
            "vae": [vae_node, 0],
            "width": width,
            "height": height,
            "length": num_frames + skip_junk_frames,
            "batch_size": 1,
            "clip_vision_output": [clip_vision_encode_node, 0],
            "start_image": [load_img_node, 0],
        },
    }
    nid += 1

    # --- Dual KSamplerAdvanced ---

    sampler_high_node = str(nid)
    workflow[sampler_high_node] = {
        "class_type": "KSamplerAdvanced",
        "inputs": {
            "model": [high_sampling_node, 0],
            "positive": [i2v_node, 0],
            "negative": [i2v_node, 1],
            "latent_image": [i2v_node, 2],
            "seed": seed,
            "steps": total_steps,
            "cfg": cfg,
            "sampler_name": "euler",
            "scheduler": "simple",
            "start_at_step": 0,
            "end_at_step": split_steps,
            "add_noise": "enable",
            "return_with_leftover_noise": "enable",
            "noise_seed": seed,
        },
    }
    nid += 1

    sampler_low_node = str(nid)
    workflow[sampler_low_node] = {
        "class_type": "KSamplerAdvanced",
        "inputs": {
            "model": [low_sampling_node, 0],
            "positive": [i2v_node, 0],
            "negative": [i2v_node, 1],
            "latent_image": [sampler_high_node, 0],
            "seed": seed,
            "steps": total_steps,
            "cfg": cfg,
            "sampler_name": "euler",
            "scheduler": "simple",
            "start_at_step": split_steps,
            "end_at_step": total_steps,
            "add_noise": "disable",
            "return_with_leftover_noise": "disable",
            "noise_seed": seed,
        },
    }
    nid += 1

    # --- Decode ---

    decode_node = str(nid)
    workflow[decode_node] = {
        "class_type": "VAEDecode",
        "inputs": {
            "samples": [sampler_low_node, 0],
            "vae": [vae_node, 0],
        },
    }
    nid += 1

    # --- Strip junk frames (first N frames are often garbage with distilled models) ---

    images_source = decode_node
    if skip_junk_frames > 0:
        trim_node = str(nid)
        workflow[trim_node] = {
            "class_type": "VHS_SplitImages",
            "inputs": {
                "images": [decode_node, 0],
                "split_index": skip_junk_frames,
            },
        }
        images_source = trim_node
        nid += 1

    # --- Output ---

    ts = int(time.time())
    prefix = output_prefix or f"dasiwa_{ts}"
    output_node = str(nid)
    workflow[output_node] = {
        "class_type": "VHS_VideoCombine",
        "inputs": {
            "images": [images_source, 2 if skip_junk_frames > 0 else 0],
            "frame_rate": fps,
            "loop_count": 0,
            "filename_prefix": prefix,
            "format": "video/h264-mp4",
            "pix_fmt": "yuv420p",
            "crf": 19,
            "save_metadata": True,
            "trim_to_audio": False,
            "pingpong": False,
            "save_output": True,
        },
    }

    return workflow, prefix


def check_dasiwa_ready() -> tuple[bool, str]:
    """Check if DaSiWa TastySin v8 models are available."""
    from pathlib import Path
    base = Path("/opt/ComfyUI/models/unet")
    missing = []
    for key, fname in DASIWA_MODELS.items():
        if not (base / fname).exists():
            missing.append(f"{key}: {fname}")
    if missing:
        return False, f"Missing DaSiWa models: {', '.join(missing)}"
    return True, "DaSiWa TastySin v8 ready"



