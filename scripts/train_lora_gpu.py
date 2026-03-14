#!/usr/bin/env python3
"""
GPU-based SDXL LoRA training for anime characters.
Runs on NVIDIA RTX 3060 (12GB) with FP16 — ~18x faster than CPU.

IMPORTANT: Stop ComfyUI first to free VRAM:
    sudo systemctl stop comfyui

Usage:
    python3 train_lora_gpu.py --character static_hopper --steps 1000
    python3 train_lora_gpu.py --character static_hopper --steps 800 --rank 16
    python3 train_lora_gpu.py --all-needing  # Train all characters needing LoRAs
"""

import argparse
import gc
import json
import logging
import os
import random
import sys
import time
from pathlib import Path

import torch
from PIL import Image
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms
from diffusers import StableDiffusionXLPipeline
from diffusers import DDPMScheduler
from peft import LoraConfig, get_peft_model
from safetensors.torch import save_file

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Paths
CHECKPOINT = "/opt/ComfyUI/models/checkpoints/waiIllustriousSDXL_v160.safetensors"
DATASETS_DIR = Path("/opt/anime-studio/datasets")
OUTPUT_DIR = Path("/opt/ComfyUI/models/loras")
DEVICE = "cuda"
DTYPE = torch.float16  # FP16 for 12GB VRAM
RESOLUTION = 768  # Safe for 12GB


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

        self.samples = []
        if not self.img_dir.exists():
            raise FileNotFoundError(f"No dataset at {self.img_dir}")

        for img_path in sorted(self.img_dir.glob("*.png")):
            if approved_set and img_path.name not in approved_set:
                continue
            # Validate image is readable
            try:
                with Image.open(img_path) as img:
                    img.verify()
            except Exception as e:
                logger.warning(f"Skipping corrupt image {img_path.name}: {e}")
                continue
            caption_path = img_path.with_suffix('.txt')
            caption = caption_path.read_text().strip() if caption_path.exists() else ""
            self.samples.append((img_path, caption))

        if not self.samples:
            for img_path in sorted(self.img_dir.glob("*.png")):
                caption_path = img_path.with_suffix('.txt')
                caption = caption_path.read_text().strip() if caption_path.exists() else ""
                self.samples.append((img_path, caption))

        logger.info(f"Dataset '{character_name}': {len(self.samples)} images")

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        img_path, caption = self.samples[idx]
        try:
            image = Image.open(img_path).convert("RGB")
        except Exception as e:
            logger.warning(f"Corrupt image {img_path}: {e} — using blank placeholder")
            image = Image.new("RGB", (self.resolution, self.resolution), (128, 128, 128))
        image = self.transform(image)
        return {"pixel_values": image, "caption": caption}


def train_lora(
    character_name: str,
    steps: int = 1000,
    rank: int = 32,
    lr: float = 1e-4,
    batch_size: int = 1,
    checkpoint: str = None,
):
    """Train a LoRA on GPU (CUDA) for a character dataset."""

    # Check GPU availability
    if not torch.cuda.is_available():
        logger.error("CUDA not available! Use train_lora_cpu.py instead.")
        return False

    vram_gb = torch.cuda.get_device_properties(0).total_memory / 1024**3
    logger.info(f"GPU: {torch.cuda.get_device_name(0)} ({vram_gb:.1f}GB VRAM)")

    output_path = OUTPUT_DIR / f"{character_name}_ill_lora.safetensors"
    if output_path.exists():
        logger.warning(f"Output {output_path} already exists — will overwrite")

    # Load dataset
    dataset = CharacterDataset(character_name, RESOLUTION)
    if len(dataset) < 5:
        logger.error(f"Only {len(dataset)} images for {character_name} — need at least 5")
        return False

    num_epochs = max(1, steps // len(dataset))
    total_steps = num_epochs * len(dataset)
    logger.info(f"Training {character_name}: {len(dataset)} images, {num_epochs} epochs, ~{total_steps} steps, rank={rank}")

    # Load pipeline on CPU first, then move components to GPU individually
    logger.info("Loading SDXL pipeline...")
    t0 = time.time()

    ckpt = checkpoint or CHECKPOINT
    logger.info(f"Using checkpoint: {ckpt}")
    pipe = StableDiffusionXLPipeline.from_single_file(
        ckpt,
        torch_dtype=DTYPE,
        use_safetensors=True,
    )
    logger.info(f"Pipeline loaded in {time.time()-t0:.0f}s")

    # Extract components
    vae = pipe.vae
    text_encoder = pipe.text_encoder
    text_encoder_2 = pipe.text_encoder_2
    tokenizer = pipe.tokenizer
    tokenizer_2 = pipe.tokenizer_2
    unet = pipe.unet

    # Phase 1: Pre-encode all latents and text embeddings on GPU
    # Move VAE + text encoders to GPU, encode everything, then free them
    logger.info("Phase 1: Pre-encoding latents and text embeddings on GPU...")

    vae.to(DEVICE)
    vae.eval()
    vae.requires_grad_(False)

    text_encoder.to(DEVICE)
    text_encoder.eval()
    text_encoder.requires_grad_(False)

    text_encoder_2.to(DEVICE)
    text_encoder_2.eval()
    text_encoder_2.requires_grad_(False)

    cached_data = []
    for batch in DataLoader(dataset, batch_size=1, shuffle=False, num_workers=0):
        with torch.no_grad():
            pixel_values = batch["pixel_values"].to(DEVICE, dtype=DTYPE)
            captions = batch["caption"]

            latent = vae.encode(pixel_values).latent_dist.sample()
            latent = latent * vae.config.scaling_factor

            tokens1 = tokenizer(
                captions, padding="max_length", max_length=77,
                truncation=True, return_tensors="pt"
            )
            text_embeds1 = text_encoder(tokens1.input_ids.to(DEVICE), output_hidden_states=True)
            hidden1 = text_embeds1.hidden_states[-2]

            tokens2 = tokenizer_2(
                captions, padding="max_length", max_length=77,
                truncation=True, return_tensors="pt"
            )
            text_out2 = text_encoder_2(tokens2.input_ids.to(DEVICE), output_hidden_states=True)
            hidden2 = text_out2.hidden_states[-2]
            pooled = text_out2.text_embeds

            encoder_hidden_states = torch.cat([hidden1, hidden2], dim=-1)

            # Store on CPU to free GPU for UNet
            cached_data.append({
                'latent': latent.detach().cpu(),
                'encoder_hidden_states': encoder_hidden_states.detach().cpu(),
                'pooled': pooled.detach().cpu(),
            })

    logger.info(f"Pre-encoded {len(cached_data)} samples")

    # Free VAE and text encoders from GPU
    del vae, text_encoder, text_encoder_2, tokenizer, tokenizer_2
    pipe.vae = None
    pipe.text_encoder = None
    pipe.text_encoder_2 = None
    del pipe
    gc.collect()
    torch.cuda.empty_cache()

    vram_after_encode = torch.cuda.memory_allocated() / 1024**3
    logger.info(f"Freed encoders. GPU memory: {vram_after_encode:.2f}GB")

    # Phase 2: Train UNet LoRA on GPU
    logger.info("Phase 2: UNet LoRA training on GPU...")

    unet.to(DEVICE)
    unet.requires_grad_(False)
    unet.enable_gradient_checkpointing()  # Save VRAM

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

    vram_with_unet = torch.cuda.memory_allocated() / 1024**3
    logger.info(f"UNet on GPU: {vram_with_unet:.2f}GB VRAM used")

    optimizer = torch.optim.AdamW(
        [p for p in unet.parameters() if p.requires_grad],
        lr=lr,
        weight_decay=1e-2,
    )

    # Use GradScaler for mixed precision stability
    scaler = torch.amp.GradScaler('cuda')

    noise_scheduler = DDPMScheduler(
        num_train_timesteps=1000,
        beta_start=0.00085,
        beta_end=0.012,
        beta_schedule="scaled_linear",
    )

    add_time_ids = torch.tensor(
        [[RESOLUTION, RESOLUTION, 0, 0, RESOLUTION, RESOLUTION]], dtype=DTYPE
    ).to(DEVICE)

    unet.train()
    step = 0
    best_loss = float('inf')
    t_start = time.time()

    logger.info(f"Starting GPU training — estimated ~{total_steps * 1.5 / 60:.0f} minutes")

    for epoch in range(num_epochs):
        epoch_loss = 0.0
        indices = list(range(len(cached_data)))
        random.shuffle(indices)

        for batch_idx, idx in enumerate(indices):
            data = cached_data[idx]
            latents = data['latent'].to(DEVICE)
            encoder_hidden_states = data['encoder_hidden_states'].to(DEVICE)
            pooled = data['pooled'].to(DEVICE)

            noise = torch.randn_like(latents)
            timesteps = torch.randint(
                0, noise_scheduler.config.num_train_timesteps,
                (latents.shape[0],), device=DEVICE, dtype=torch.long
            )
            noisy_latents = noise_scheduler.add_noise(latents, noise, timesteps)

            added_cond_kwargs = {
                "text_embeds": pooled,
                "time_ids": add_time_ids.repeat(latents.shape[0], 1),
            }

            with torch.amp.autocast('cuda', dtype=DTYPE):
                noise_pred = unet(
                    noisy_latents, timesteps, encoder_hidden_states,
                    added_cond_kwargs=added_cond_kwargs,
                ).sample

            loss = torch.nn.functional.mse_loss(noise_pred.float(), noise.float(), reduction="mean")

            if torch.isnan(loss):
                logger.warning(f"  NaN loss at step {step+1}, skipping")
                optimizer.zero_grad()
                continue

            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(unet.parameters(), 1.0)
            scaler.step(optimizer)
            scaler.update()
            optimizer.zero_grad()

            step += 1
            epoch_loss += loss.item()

            if step % 10 == 0:
                elapsed = time.time() - t_start
                steps_per_sec = step / elapsed
                eta = (total_steps - step) / steps_per_sec if steps_per_sec > 0 else 0
                logger.info(
                    f"  Step {step}/{total_steps} | Loss: {loss.item():.6f} | "
                    f"{steps_per_sec:.1f} steps/s | ETA: {eta/60:.0f}min"
                )

            if step % 200 == 0:
                ckpt_path = OUTPUT_DIR / f"{character_name}_ill_lora_step{step}.safetensors"
                _save_lora(unet, ckpt_path)
                logger.info(f"  Checkpoint saved: {ckpt_path.name}")

        avg_loss = epoch_loss / max(1, batch_idx + 1)
        logger.info(f"Epoch {epoch+1}/{num_epochs} | Avg Loss: {avg_loss:.6f}")

        if avg_loss < best_loss:
            best_loss = avg_loss

    # Save final
    _save_lora(unet, output_path)
    elapsed_total = time.time() - t_start
    logger.info(f"Training complete! Final LoRA saved to {output_path}")
    logger.info(f"Best loss: {best_loss:.6f}, Total steps: {step}, Time: {elapsed_total/60:.1f}min")

    # Record training metadata — what images were used, when, loss
    _save_training_record(character_name, dataset, output_path, step, best_loss, elapsed_total, rank)

    del unet, optimizer, scaler
    gc.collect()
    torch.cuda.empty_cache()

    return True


def _save_training_record(character_name, dataset, output_path, steps, best_loss, elapsed, rank):
    """Save a training manifest so we know what the LoRA was trained on."""
    from datetime import datetime, timezone
    import hashlib

    # Record every image used in training (for staleness detection)
    image_hashes = []
    for img_path, caption in dataset.samples:
        h = hashlib.md5(img_path.read_bytes()).hexdigest()[:12] if img_path.exists() else "missing"
        image_hashes.append({"file": img_path.name, "hash": h})

    manifest = {
        "character": character_name,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "lora_path": str(output_path),
        "image_count": len(dataset),
        "images": image_hashes,
        "steps": steps,
        "rank": rank,
        "best_loss": best_loss,
        "training_time_min": round(elapsed / 60, 1),
        "checkpoint": str(dataset.samples[0][0].parent.parent.parent / "checkpoints") if dataset.samples else "",
    }

    manifest_path = output_path.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2))
    logger.info(f"Training manifest saved: {manifest_path}")

    # Also write to DB if available
    try:
        import psycopg2
        conn = psycopg2.connect(dbname="anime_production", user="patrick",
                                password="RP78eIrW7cI2jYvL5akt1yurE")
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO lora_training_status
                (status, model_path, training_started_at, training_completed_at,
                 training_steps, final_loss, version)
            VALUES ('completed', %s, NOW() - INTERVAL '%s seconds', NOW(), %s, %s,
                    COALESCE((SELECT MAX(version) FROM lora_training_status
                              WHERE model_path = %s), 0) + 1)
        """, (str(output_path), int(elapsed), steps, best_loss, str(output_path)))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logger.warning(f"Could not write training record to DB: {e}")


def _save_lora(unet, path: Path):
    """Extract and save LoRA weights in ComfyUI-compatible format."""
    state_dict = {}
    for name, param in unet.named_parameters():
        if param.requires_grad and "lora" in name:
            clean_name = name.replace("base_model.model.", "")
            clean_name = clean_name.replace(".default", "")
            state_dict[clean_name] = param.detach().cpu()

    save_file(state_dict, str(path))


ROLE_THRESHOLDS = {
    "protagonist": 30,
    "lead": 30,
    "antagonist": 20,
    "supporting": 20,
    "mentor": 20,
    "ai_character": 20,
    "comic_relief": 15,
}
DEFAULT_THRESHOLD = 15


def _get_character_roles() -> dict[str, str]:
    """Query character_role from DB, keyed by dataset folder name (lowercased, underscored)."""
    import psycopg2
    roles = {}
    try:
        conn = psycopg2.connect(dbname="anime_production", user="patrick",
                                password="RP78eIrW7cI2jYvL5akt1yurE")
        cur = conn.cursor()
        cur.execute("""
            SELECT REGEXP_REPLACE(LOWER(REPLACE(c.name, ' ', '_')), '[^a-z0-9_-]', '', 'g'),
                   c.character_role
            FROM characters c
            WHERE c.character_role IS NOT NULL
        """)
        for slug, role in cur.fetchall():
            roles[slug] = role.strip().lower()
        cur.close()
        conn.close()
    except Exception as e:
        logger.warning(f"Could not fetch character roles from DB: {e}")
    return roles


def get_characters_needing_lora(min_approved: int = None):
    """Get all characters with enough approved images but no LoRA yet.

    Uses role-based thresholds from DB:
      protagonist/lead: 30, antagonist/supporting/mentor: 20, other: 15
    If min_approved is set, it overrides role-based thresholds for all characters.
    """
    roles = _get_character_roles()
    chars = []
    for char_dir in sorted(DATASETS_DIR.iterdir()):
        if not char_dir.is_dir():
            continue
        img_dir = char_dir / "images"
        if not img_dir.exists():
            continue

        name = char_dir.name
        existing_lora = OUTPUT_DIR / f"{name}_ill_lora.safetensors"
        xl_lora = OUTPUT_DIR / f"{name}_xl_lora.safetensors"
        if existing_lora.exists() or xl_lora.exists():
            continue

        # Count approved
        approval_file = char_dir / "approval_status.json"
        approved = 0
        if approval_file.exists():
            data = json.loads(approval_file.read_text())
            for fname, info in data.items():
                if isinstance(info, dict) and info.get('status') == 'approved':
                    approved += 1
                elif isinstance(info, str) and info == 'approved':
                    approved += 1

        # Determine threshold from role or override
        if min_approved is not None:
            threshold = min_approved
        else:
            role = roles.get(name, "")
            threshold = ROLE_THRESHOLDS.get(role, DEFAULT_THRESHOLD)

        if approved >= threshold:
            role_label = roles.get(name, "unknown")
            chars.append((name, approved, role_label, threshold))

    chars.sort(key=lambda x: -x[1])
    return chars


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GPU LoRA Training for Anime Characters (RTX 3060)")
    parser.add_argument("--character", type=str, help="Character name to train")
    parser.add_argument("--all-needing", action="store_true", help="Train all characters needing LoRAs")
    parser.add_argument("--steps", type=int, default=1000, help="Training steps (default: 1000)")
    parser.add_argument("--rank", type=int, default=32, help="LoRA rank (default: 32)")
    parser.add_argument("--lr", type=float, default=1e-4, help="Learning rate (default: 1e-4)")
    parser.add_argument("--batch-size", type=int, default=1, help="Batch size (default: 1)")
    parser.add_argument("--checkpoint", type=str, default=None, help="Override checkpoint path")
    parser.add_argument("--min-approved", type=int, default=None,
                        help="Override minimum approved images (default: role-based thresholds)")
    args = parser.parse_args()

    if args.all_needing:
        chars = get_characters_needing_lora(args.min_approved)
        if not chars:
            logger.info("All characters already have LoRAs or insufficient images")
            sys.exit(0)
        logger.info(f"Training {len(chars)} characters:")
        for n, c, role, thresh in chars:
            logger.info(f"  {n}: {c} approved (role={role}, threshold={thresh})")
        failed = []
        for name, count, role, thresh in chars:
            logger.info(f"\n{'='*60}")
            logger.info(f"Training {name} ({count} images)")
            logger.info(f"{'='*60}")
            try:
                success = train_lora(name, steps=args.steps, rank=args.rank, lr=args.lr,
                                     batch_size=args.batch_size, checkpoint=args.checkpoint)
                if not success:
                    failed.append(name)
            except Exception as e:
                logger.error(f"FAILED training {name}: {e}")
                failed.append(name)
                gc.collect()
                torch.cuda.empty_cache()
        if failed:
            logger.warning(f"Failed characters: {', '.join(failed)}")
            sys.exit(1)
    elif args.character:
        train_lora(args.character, steps=args.steps, rank=args.rank, lr=args.lr,
                   batch_size=args.batch_size, checkpoint=args.checkpoint)
    else:
        parser.print_help()
