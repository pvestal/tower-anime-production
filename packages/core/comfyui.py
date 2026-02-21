"""Shared ComfyUI workflow builders — IP-Adapter, etc."""


def build_ipadapter_workflow(
    prompt_text: str,
    negative_text: str,
    checkpoint: str,
    ref_image_name: str,
    seed: int,
    steps: int,
    cfg: float,
    denoise: float,
    weight: float,
    width: int,
    height: int,
    filename_prefix: str,
    sampler_name: str = "dpmpp_2m",
    scheduler: str = "karras",
) -> dict:
    """Build IPAdapter img2img workflow using ComfyUI-IPAdapter-Plus nodes.

    Used by both /refine (ingest_router) and /variant (training_router).
    """
    return {
        "1": {
            "inputs": {"text": prompt_text, "clip": ["4", 1]},
            "class_type": "CLIPTextEncode",
        },
        "2": {
            "inputs": {"text": negative_text, "clip": ["4", 1]},
            "class_type": "CLIPTextEncode",
        },
        "3": {
            "inputs": {
                "seed": seed,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": sampler_name,
                "scheduler": scheduler,
                "denoise": denoise,
                "model": ["10", 0],
                "positive": ["1", 0],
                "negative": ["2", 0],
                "latent_image": ["8", 0],
            },
            "class_type": "KSampler",
        },
        "4": {
            "inputs": {"ckpt_name": checkpoint},
            "class_type": "CheckpointLoaderSimple",
        },
        "6": {
            "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
            "class_type": "VAEDecode",
        },
        "7": {
            "inputs": {"filename_prefix": filename_prefix, "images": ["6", 0]},
            "class_type": "SaveImage",
        },
        "8": {
            "inputs": {"pixels": ["9", 0], "vae": ["4", 2]},
            "class_type": "VAEEncode",
        },
        "9": {
            "inputs": {"image": ref_image_name},
            "class_type": "LoadImage",
        },
        "10": {
            "inputs": {
                "weight": weight,
                "weight_type": "linear",
                "combine_embeds": "concat",
                "start_at": 0.0,
                "end_at": 0.85,
                "embeds_scaling": "K+V",
                "unfold_batch": False,
                "model": ["11", 0],
                "ipadapter": ["11", 1],
                "image": ["9", 0],
            },
            "class_type": "IPAdapterAdvanced",
        },
        "11": {
            "inputs": {
                "model": ["4", 0],
                "preset": "PLUS (high strength)",
            },
            "class_type": "IPAdapterUnifiedLoader",
        },
    }
