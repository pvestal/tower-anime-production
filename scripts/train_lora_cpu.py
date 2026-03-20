#!/usr/bin/env python3
"""
CPU-based SDXL LoRA training for anime characters.
Runs on CPU so the GPU stays free for ComfyUI video generation.

Usage:
    python3 train_lora_cpu.py --character roxy --steps 1000
    python3 train_lora_cpu.py --character gem --steps 800 --rank 16
    python3 train_lora_cpu.py --all-fury  # Train all Fury characters with enough images
"""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

import torch
from PIL import Image
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms
from diffusers import StableDiffusionXLPipeline, AutoencoderKL, UNet2DConditionModel
from diffusers.utils import convert_state_dict_to_diffusers
from transformers import CLIPTextModel, CLIPTokenizer, CLIPTextModelWithProjection
from peft import LoraConfig, get_peft_model
from safetensors.torch import save_file, load_file

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Paths
CHECKPOINT = "/opt/ComfyUI/models/checkpoints/waiIllustriousSDXL_v160.safetensors"
DATASETS_DIR = Path("/opt/anime-studio/datasets")
OUTPUT_DIR = Path("/opt/ComfyUI/models/loras")
RESOLUTION = 768
DTYPE = torch.float32  # CPU needs FP32


class CharacterDataset(Dataset):
    """Load character images + captions for LoRA training."""

    def __init__(self, character_name: str, resolution: int = 768):
        self.img_dir = DATASETS_DIR / character_name / "images"
        self.resolution = resolution
        self.transform = transforms.Compose([
            transforms.Resize(resolution, interpolation=transforms.InterpolationMode.LANCZOS),
            transforms.CenterCrop(resolution),
            transforms.ToTensor(),
            transforms.Normalize([0.5], [0.5]),
        ])

        # Load approval status
        approval_file = DATASETS_DIR / character_name / "approval_status.json"
        approved_set = set()
        if approval_file.exists():
            approvals = json.loads(approval_file.read_text())
            for fname, info in approvals.items():
                if isinstance(info, dict) and info.get('status') == 'approved':
                    approved_set.add(fname)
                elif isinstance(info, str) and info == 'approved':
                    approved_set.add(fname)

        # Collect image files — if no approval file, use all images
        self.samples = []
        if not self.img_dir.exists():
            raise FileNotFoundError(f"No dataset at {self.img_dir}")

        for img_path in sorted(self.img_dir.glob("*.png")):
            # Use approved images if we have approvals, otherwise use all
            if approved_set and img_path.name not in approved_set:
                continue

            caption_path = img_path.with_suffix('.txt')
            caption = caption_path.read_text().strip() if caption_path.exists() else ""
            self.samples.append((img_path, caption))

        if not self.samples:
            # Fallback: use all images if approval filtering gave 0
            for img_path in sorted(self.img_dir.glob("*.png")):
                caption_path = img_path.with_suffix('.txt')
                caption = caption_path.read_text().strip() if caption_path.exists() else ""
                self.samples.append((img_path, caption))

        logger.info(f"Dataset '{character_name}': {len(self.samples)} images")

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        img_path, caption = self.samples[idx]
        image = Image.open(img_path).convert("RGB")
        image = self.transform(image)
        return {"pixel_values": image, "caption": caption}


def train_lora(
    character_name: str,
    steps: int = 1000,
    rank: int = 32,
    lr: float = 1e-4,
    batch_size: int = 1,
):
    """Train a LoRA on CPU for a character dataset."""

    output_path = OUTPUT_DIR / f"{character_name}_ill_lora.safetensors"
    if output_path.exists():
        logger.warning(f"Output {output_path} already exists — will overwrite")

    # Load dataset
    dataset = CharacterDataset(character_name, RESOLUTION)
    if len(dataset) < 5:
        logger.error(f"Only {len(dataset)} images for {character_name} — need at least 5")
        return False

    dataloader = DataLoader(dataset, batch_size=batch_size, shuffle=True, num_workers=0)
    num_epochs = max(1, steps // len(dataset))
    total_steps = num_epochs * len(dataset)
    logger.info(f"Training {character_name}: {len(dataset)} images, {num_epochs} epochs, ~{total_steps} steps, rank={rank}")

    # Load pipeline on CPU
    logger.info("Loading SDXL pipeline on CPU (this takes ~2 minutes)...")
    t0 = time.time()

    pipe = StableDiffusionXLPipeline.from_single_file(
        CHECKPOINT,
        torch_dtype=DTYPE,
        use_safetensors=True,
    )
    pipe.to("cpu")
    logger.info(f"Pipeline loaded in {time.time()-t0:.0f}s")

    # Extract components
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

    # Add LoRA to UNet
    lora_config = LoraConfig(
        r=rank,
        lora_alpha=rank,
        target_modules=["to_q", "to_k", "to_v", "to_out.0"],
        lora_dropout=0.0,
    )
    unet = get_peft_model(unet, lora_config)
    trainable_params = sum(p.numel() for p in unet.parameters() if p.requires_grad)
    total_params = sum(p.numel() for p in unet.parameters())
    logger.info(f"LoRA params: {trainable_params:,} / {total_params:,} ({100*trainable_params/total_params:.2f}%)")

    # Optimizer
    optimizer = torch.optim.AdamW(
        [p for p in unet.parameters() if p.requires_grad],
        lr=lr,
        weight_decay=1e-2,
    )

    # Training loop
    unet.train()
    from diffusers import DDPMScheduler
    noise_scheduler = DDPMScheduler.from_config(pipe.scheduler.config)
    step = 0
    best_loss = float('inf')

    # Pre-encode all latents and text embeddings to save time
    logger.info("Pre-encoding latents and text embeddings...")
    cached_data = []
    vae.eval()
    text_encoder.eval()
    text_encoder_2.eval()
    for batch in DataLoader(dataset, batch_size=1, shuffle=False, num_workers=0):
        with torch.no_grad():
            pixel_values = batch["pixel_values"].to(DTYPE)
            captions = batch["caption"]

            # Encode image to latent
            latent = vae.encode(pixel_values).latent_dist.sample()
            latent = latent * vae.config.scaling_factor

            # Encode text with both encoders
            tokens1 = tokenizer(
                captions, padding="max_length", max_length=77,
                truncation=True, return_tensors="pt"
            )
            text_embeds1 = text_encoder(tokens1.input_ids, output_hidden_states=True)
            hidden1 = text_embeds1.hidden_states[-2]  # penultimate

            tokens2 = tokenizer_2(
                captions, padding="max_length", max_length=77,
                truncation=True, return_tensors="pt"
            )
            text_out2 = text_encoder_2(tokens2.input_ids, output_hidden_states=True)
            hidden2 = text_out2.hidden_states[-2]  # penultimate
            pooled = text_out2.text_embeds  # [batch, proj_dim] pooled output

            encoder_hidden_states = torch.cat([hidden1, hidden2], dim=-1)

            cached_data.append({
                'latent': latent.detach(),
                'encoder_hidden_states': encoder_hidden_states.detach(),
                'pooled': pooled.detach(),
            })

    # Free VAE and text encoders from memory
    del vae, text_encoder, text_encoder_2, tokenizer, tokenizer_2
    import gc; gc.collect()
    logger.info(f"Pre-encoded {len(cached_data)} samples. Freed VAE+text encoders from RAM.")

    logger.info(f"Starting training on CPU — estimated ~{total_steps * 30 / 3600:.1f} hours")

    add_time_ids = torch.tensor([[RESOLUTION, RESOLUTION, 0, 0, RESOLUTION, RESOLUTION]], dtype=DTYPE)

    for epoch in range(num_epochs):
        epoch_loss = 0.0
        # Shuffle indices each epoch
        import random
        indices = list(range(len(cached_data)))
        random.shuffle(indices)

        for batch_idx, idx in enumerate(indices):
            data = cached_data[idx]
            latents = data['latent']
            encoder_hidden_states = data['encoder_hidden_states']
            pooled = data['pooled']

            # Add noise
            noise = torch.randn_like(latents)
            timesteps = torch.randint(0, noise_scheduler.config.num_train_timesteps, (latents.shape[0],), dtype=torch.long)
            noisy_latents = noise_scheduler.add_noise(latents, noise, timesteps)

            added_cond_kwargs = {
                "text_embeds": pooled,
                "time_ids": add_time_ids.repeat(latents.shape[0], 1),
            }

            # Predict noise
            noise_pred = unet(
                noisy_latents, timesteps, encoder_hidden_states,
                added_cond_kwargs=added_cond_kwargs,
            ).sample

            # Loss
            loss = torch.nn.functional.mse_loss(noise_pred.float(), noise.float(), reduction="mean")

            if torch.isnan(loss):
                logger.warning(f"  NaN loss at step {step+1}, skipping")
                optimizer.zero_grad()
                continue

            # Backward
            loss.backward()
            torch.nn.utils.clip_grad_norm_(unet.parameters(), 1.0)
            optimizer.step()
            optimizer.zero_grad()

            step += 1
            epoch_loss += loss.item()

            if step % 10 == 0:
                logger.info(f"  Step {step}/{total_steps} | Loss: {loss.item():.6f}")

            if step % 200 == 0:
                # Save checkpoint
                ckpt_path = OUTPUT_DIR / f"{character_name}_ill_lora_step{step}.safetensors"
                _save_lora(unet, ckpt_path)
                logger.info(f"  Checkpoint saved: {ckpt_path.name}")

        avg_loss = epoch_loss / max(1, batch_idx + 1)
        logger.info(f"Epoch {epoch+1}/{num_epochs} | Avg Loss: {avg_loss:.6f}")

        if avg_loss < best_loss:
            best_loss = avg_loss

    # Save final
    _save_lora(unet, output_path)
    logger.info(f"Training complete! Final LoRA saved to {output_path}")
    logger.info(f"Best loss: {best_loss:.6f}, Total steps: {step}")

    # Cleanup
    del pipe, unet, vae, text_encoder, text_encoder_2
    torch.cuda.empty_cache() if torch.cuda.is_available() else None

    return True


def _save_lora(unet, path: Path):
    """Extract and save LoRA weights in ComfyUI-compatible format."""
    state_dict = {}
    for name, param in unet.named_parameters():
        if param.requires_grad and "lora" in name:
            # Convert peft naming to ComfyUI/kohya format
            clean_name = name.replace("base_model.model.", "")
            clean_name = clean_name.replace(".default", "")
            state_dict[clean_name] = param.detach().cpu()

    save_file(state_dict, str(path))


def get_fury_characters():
    """Get Fury characters with enough images for training."""
    chars = []
    fury_chars = ["roxy", "buck", "zara", "gem", "fawn", "female_wolf", "lilith", "luna"]
    for name in fury_chars:
        img_dir = DATASETS_DIR / name / "images"
        if img_dir.exists():
            count = len(list(img_dir.glob("*.png")))
            existing_lora = OUTPUT_DIR / f"{name}_ill_lora.safetensors"
            xl_lora = OUTPUT_DIR / f"{name}_xl_lora.safetensors"
            has_lora = existing_lora.exists() or xl_lora.exists()
            if count >= 10 and not has_lora:
                chars.append((name, count))
    return chars


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CPU LoRA Training for Anime Characters")
    parser.add_argument("--character", type=str, help="Character name to train")
    parser.add_argument("--all-fury", action="store_true", help="Train all untrained Fury characters")
    parser.add_argument("--steps", type=int, default=1000, help="Training steps (default: 1000)")
    parser.add_argument("--rank", type=int, default=32, help="LoRA rank (default: 32)")
    parser.add_argument("--lr", type=float, default=1e-4, help="Learning rate (default: 1e-4)")
    parser.add_argument("--batch-size", type=int, default=1, help="Batch size (default: 1)")
    args = parser.parse_args()

    if args.all_fury:
        chars = get_fury_characters()
        if not chars:
            logger.info("All Fury characters already have LoRAs or insufficient images")
            sys.exit(0)
        logger.info(f"Training {len(chars)} Fury characters: {', '.join(f'{n} ({c} imgs)' for n,c in chars)}")
        for name, count in chars:
            logger.info(f"\n{'='*60}")
            logger.info(f"Training {name} ({count} images)")
            logger.info(f"{'='*60}")
            train_lora(name, steps=args.steps, rank=args.rank, lr=args.lr, batch_size=args.batch_size)
    elif args.character:
        train_lora(args.character, steps=args.steps, rank=args.rank, lr=args.lr, batch_size=args.batch_size)
    else:
        parser.print_help()
