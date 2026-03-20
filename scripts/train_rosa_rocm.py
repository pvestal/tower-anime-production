#!/usr/bin/env python3
"""
GPU-based SDXL LoRA training for Rosa on AMD RX 9070 XT (ROCm).
Adapted from train_lora_cpu.py — uses FP16 on GPU instead of FP32 on CPU.

Usage:
    HSA_OVERRIDE_GFX_VERSION=12.0.1 HIP_VISIBLE_DEVICES=0 CUDA_VISIBLE_DEVICES="" \
    /opt/ComfyUI/venv-rocm/bin/python3 train_rosa_rocm.py
"""

import gc
import logging
import random
import time
from pathlib import Path

import torch
from PIL import Image
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms
from diffusers import StableDiffusionXLPipeline, DDPMScheduler
from peft import LoraConfig, get_peft_model
from safetensors.torch import save_file

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Config
CHECKPOINT = "/opt/ComfyUI/models/checkpoints/juggernautXL_v9.safetensors"
DATASET_DIR = Path("/opt/anime-studio/datasets/rosa/images")
OUTPUT_DIR = Path("/opt/ComfyUI/models/loras")
RESOLUTION = 1024  # 16GB VRAM can handle 1024
DTYPE = torch.float16
DEVICE = "cuda"
RANK = 32
STEPS = 1000
LR = 1e-4
BATCH_SIZE = 1


class RosaDataset(Dataset):
    def __init__(self, img_dir: Path, resolution: int = 1024):
        self.images = sorted(img_dir.glob("*.png"))
        self.resolution = resolution
        self.transform = transforms.Compose([
            transforms.Resize(resolution, interpolation=transforms.InterpolationMode.LANCZOS),
            transforms.CenterCrop(resolution),
            transforms.ToTensor(),
            transforms.Normalize([0.5], [0.5]),
        ])
        self.fallback_caption = "photo of rosa, a beautiful mestiza woman in her early 30s, striking green eyes, warm brown skin with freckles, long dark hair, indigenous mexican features, high cheekbones, photorealistic"

    def __len__(self):
        return len(self.images)

    def __getitem__(self, idx):
        img = Image.open(self.images[idx]).convert("RGB")
        # Per-image caption from .txt file, fallback to generic
        txt_path = self.images[idx].with_suffix(".txt")
        if txt_path.exists():
            caption = txt_path.read_text().strip()
        else:
            caption = self.fallback_caption
        return {"pixel_values": self.transform(img), "caption": caption}


def save_lora(unet, path: Path):
    state_dict = {}
    for name, param in unet.named_parameters():
        if param.requires_grad and "lora" in name:
            clean_name = name.replace("base_model.model.", "")
            state_dict[clean_name] = param.detach().cpu().half()
    save_file(state_dict, str(path))
    logger.info(f"Saved LoRA: {path.name} ({len(state_dict)} tensors)")


def main():
    logger.info(f"Device: {torch.cuda.get_device_name(0)}, VRAM: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f}GB")

    dataset = RosaDataset(DATASET_DIR, RESOLUTION)
    logger.info(f"Dataset: {len(dataset)} images at {RESOLUTION}px")
    if len(dataset) < 5:
        logger.error("Need at least 5 images")
        return

    num_epochs = max(1, STEPS // len(dataset))
    total_steps = num_epochs * len(dataset)

    # Load pipeline
    logger.info("Loading Juggernaut XL pipeline on GPU...")
    t0 = time.time()
    pipe = StableDiffusionXLPipeline.from_single_file(
        CHECKPOINT, torch_dtype=DTYPE, use_safetensors=True,
    )
    pipe.to(DEVICE)
    logger.info(f"Pipeline loaded in {time.time()-t0:.0f}s")

    unet = pipe.unet
    vae = pipe.vae
    text_encoder = pipe.text_encoder
    text_encoder_2 = pipe.text_encoder_2
    tokenizer = pipe.tokenizer
    tokenizer_2 = pipe.tokenizer_2

    # Freeze everything except LoRA
    vae.requires_grad_(False)
    text_encoder.requires_grad_(False)
    text_encoder_2.requires_grad_(False)
    unet.requires_grad_(False)

    # Add LoRA
    lora_config = LoraConfig(
        r=RANK, lora_alpha=RANK,
        target_modules=["to_q", "to_k", "to_v", "to_out.0"],
        lora_dropout=0.0,
    )
    unet = get_peft_model(unet, lora_config)
    trainable = sum(p.numel() for p in unet.parameters() if p.requires_grad)
    total = sum(p.numel() for p in unet.parameters())
    logger.info(f"LoRA params: {trainable:,} / {total:,} ({100*trainable/total:.2f}%)")

    # Pre-encode all latents and text
    logger.info("Pre-encoding latents and text embeddings...")
    cached_data = []
    vae.eval()
    text_encoder.eval()
    text_encoder_2.eval()

    for batch in DataLoader(dataset, batch_size=1, shuffle=False, num_workers=0):
        with torch.no_grad():
            pixel_values = batch["pixel_values"].to(DEVICE, dtype=DTYPE)
            captions = batch["caption"]

            latent = vae.encode(pixel_values).latent_dist.sample()
            latent = latent * vae.config.scaling_factor

            tokens1 = tokenizer(captions, padding="max_length", max_length=77, truncation=True, return_tensors="pt").to(DEVICE)
            text_out1 = text_encoder(tokens1.input_ids, output_hidden_states=True)
            hidden1 = text_out1.hidden_states[-2]

            tokens2 = tokenizer_2(captions, padding="max_length", max_length=77, truncation=True, return_tensors="pt").to(DEVICE)
            text_out2 = text_encoder_2(tokens2.input_ids, output_hidden_states=True)
            hidden2 = text_out2.hidden_states[-2]
            pooled = text_out2.text_embeds

            encoder_hidden_states = torch.cat([hidden1, hidden2], dim=-1)
            cached_data.append({
                'latent': latent.detach(),
                'encoder_hidden_states': encoder_hidden_states.detach(),
                'pooled': pooled.detach(),
            })

    # Free VAE + text encoders from VRAM
    del vae, text_encoder, text_encoder_2, tokenizer, tokenizer_2
    pipe.vae = None
    pipe.text_encoder = None
    pipe.text_encoder_2 = None
    gc.collect()
    torch.cuda.empty_cache()
    logger.info(f"Pre-encoded {len(cached_data)} samples. Freed VAE+text from VRAM.")
    logger.info(f"VRAM after freeing: {torch.cuda.memory_allocated()/1024**3:.1f}GB / {torch.cuda.get_device_properties(0).total_memory/1024**3:.1f}GB")

    # Optimizer
    optimizer = torch.optim.AdamW(
        [p for p in unet.parameters() if p.requires_grad],
        lr=LR, weight_decay=1e-2,
    )

    noise_scheduler = DDPMScheduler.from_config(pipe.scheduler.config)
    add_time_ids = torch.tensor([[RESOLUTION, RESOLUTION, 0, 0, RESOLUTION, RESOLUTION]], dtype=DTYPE, device=DEVICE)

    unet.train()
    step = 0
    best_loss = float('inf')
    t_start = time.time()

    logger.info(f"Training: {total_steps} steps, {num_epochs} epochs, rank={RANK}, lr={LR}")

    for epoch in range(num_epochs):
        epoch_loss = 0.0
        indices = list(range(len(cached_data)))
        random.shuffle(indices)

        for batch_idx, idx in enumerate(indices):
            data = cached_data[idx]
            latents = data['latent']
            encoder_hidden_states = data['encoder_hidden_states']
            pooled = data['pooled']

            noise = torch.randn_like(latents)
            timesteps = torch.randint(0, noise_scheduler.config.num_train_timesteps, (latents.shape[0],), device=DEVICE, dtype=torch.long)
            noisy_latents = noise_scheduler.add_noise(latents, noise, timesteps)

            added_cond_kwargs = {
                "text_embeds": pooled,
                "time_ids": add_time_ids.repeat(latents.shape[0], 1),
            }

            with torch.autocast(device_type="cuda", dtype=DTYPE):
                noise_pred = unet(
                    noisy_latents, timesteps, encoder_hidden_states,
                    added_cond_kwargs=added_cond_kwargs,
                ).sample

            loss = torch.nn.functional.mse_loss(noise_pred.float(), noise.float(), reduction="mean")

            if torch.isnan(loss):
                logger.warning(f"NaN loss at step {step+1}, skipping")
                optimizer.zero_grad()
                continue

            loss.backward()
            torch.nn.utils.clip_grad_norm_(unet.parameters(), 1.0)
            optimizer.step()
            optimizer.zero_grad()

            step += 1
            epoch_loss += loss.item()

            if step % 10 == 0:
                elapsed = time.time() - t_start
                steps_per_sec = step / elapsed
                eta = (total_steps - step) / max(steps_per_sec, 0.001)
                logger.info(f"Step {step}/{total_steps} | Loss: {loss.item():.6f} | {steps_per_sec:.1f} steps/s | ETA: {eta/60:.1f}min")

            if step % 200 == 0:
                ckpt_path = OUTPUT_DIR / f"rosa_jugg_lora_step{step}.safetensors"
                save_lora(unet, ckpt_path)

        avg_loss = epoch_loss / max(1, batch_idx + 1)
        logger.info(f"Epoch {epoch+1}/{num_epochs} | Avg Loss: {avg_loss:.6f}")
        if avg_loss < best_loss:
            best_loss = avg_loss

    # Save final
    final_path = OUTPUT_DIR / "rosa_jugg_lora.safetensors"
    save_lora(unet, final_path)
    elapsed = time.time() - t_start
    logger.info(f"Training complete! {elapsed/60:.1f} minutes, {step} steps, best loss: {best_loss:.6f}")
    logger.info(f"Final LoRA: {final_path}")

    del pipe, unet
    gc.collect()
    torch.cuda.empty_cache()


if __name__ == "__main__":
    main()
