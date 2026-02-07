#!/usr/bin/env python3
"""
Quality Verification with CLIP
Compare generated images to reference images using CLIP embeddings
"""

import json
import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Optional
from PIL import Image
import requests
import torch

def verify_lora_quality(
    generated_image_path: str,
    character_name: str,
    reference_dir: Optional[str] = None
) -> Dict[str, Any]:
    """Compare generated image to reference images using CLIP"""

    try:
        # Try to use transformers CLIP if available
        from transformers import CLIPProcessor, CLIPModel

        model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
        processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")

        # Load generated image
        if not Path(generated_image_path).exists():
            raise FileNotFoundError(f"Generated image not found: {generated_image_path}")

        generated_img = Image.open(generated_image_path).convert("RGB")

        # Get image embedding
        gen_inputs = processor(images=generated_img, return_tensors="pt")
        with torch.no_grad():
            gen_embedding = model.get_image_features(**gen_inputs)
            gen_embedding = gen_embedding / gen_embedding.norm(dim=-1, keepdim=True)

        # Reference directory
        if reference_dir is None:
            reference_dir = f"/mnt/1TB-storage/character_references/{character_name}"

        ref_path = Path(reference_dir)
        if not ref_path.exists():
            # Fallback to training images
            ref_path = Path(f"/mnt/1TB-storage/comprehensive_seed_datasets/{character_name}/images")

        if not ref_path.exists():
            return {
                "status": "error",
                "error": f"No reference images found for {character_name}",
                "character_name": character_name,
                "generated_image": generated_image_path
            }

        # Compare with reference images
        similarities = []
        reference_files = []

        for ext in ["*.png", "*.jpg", "*.jpeg"]:
            reference_files.extend(ref_path.rglob(ext))

        if not reference_files:
            return {
                "status": "error",
                "error": f"No reference image files found in {ref_path}",
                "character_name": character_name
            }

        # Sample up to 10 reference images for comparison
        reference_files = reference_files[:10]

        for ref_file in reference_files:
            try:
                ref_img = Image.open(ref_file).convert("RGB")
                ref_inputs = processor(images=ref_img, return_tensors="pt")

                with torch.no_grad():
                    ref_embedding = model.get_image_features(**ref_inputs)
                    ref_embedding = ref_embedding / ref_embedding.norm(dim=-1, keepdim=True)

                # Calculate cosine similarity
                similarity = torch.cosine_similarity(gen_embedding, ref_embedding).item()
                similarities.append({
                    "reference_file": str(ref_file),
                    "similarity": similarity
                })

            except Exception as e:
                print(f"Error processing {ref_file}: {e}")
                continue

        if not similarities:
            return {
                "status": "error",
                "error": "Could not process any reference images",
                "character_name": character_name
            }

        # Calculate statistics
        similarity_scores = [s["similarity"] for s in similarities]
        avg_similarity = np.mean(similarity_scores)
        max_similarity = np.max(similarity_scores)
        min_similarity = np.min(similarity_scores)

        # Quality assessment
        if avg_similarity > 0.75:
            quality = "EXCELLENT"
        elif avg_similarity > 0.65:
            quality = "GOOD"
        elif avg_similarity > 0.50:
            quality = "ACCEPTABLE"
        else:
            quality = "POOR"

        return {
            "status": "success",
            "character_name": character_name,
            "generated_image": generated_image_path,
            "reference_directory": str(ref_path),
            "reference_count": len(similarities),
            "average_similarity": float(avg_similarity),
            "max_similarity": float(max_similarity),
            "min_similarity": float(min_similarity),
            "quality_assessment": quality,
            "similarity_threshold": {
                "excellent": "> 0.75",
                "good": "> 0.65",
                "acceptable": "> 0.50",
                "poor": "≤ 0.50"
            },
            "top_matches": sorted(similarities, key=lambda x: x["similarity"], reverse=True)[:3]
        }

    except ImportError:
        return {
            "status": "error",
            "error": "CLIP model not available. Install transformers and torch.",
            "character_name": character_name
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "character_name": character_name
        }

def text_similarity_check(
    generated_image_path: str,
    character_name: str,
    expected_prompts: List[str]
) -> Dict[str, Any]:
    """Check how well the generated image matches expected text prompts"""

    try:
        from transformers import CLIPProcessor, CLIPModel

        model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
        processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")

        # Load generated image
        generated_img = Image.open(generated_image_path).convert("RGB")

        # Test against expected prompts
        results = []
        for prompt in expected_prompts:
            inputs = processor(text=[prompt], images=generated_img, return_tensors="pt", padding=True)

            with torch.no_grad():
                outputs = model(**inputs)
                logits_per_image = outputs.logits_per_image
                probs = logits_per_image.softmax(dim=1)

            results.append({
                "prompt": prompt,
                "similarity_score": float(probs[0][0]),
                "confidence": float(probs.max())
            })

        avg_score = np.mean([r["similarity_score"] for r in results])

        return {
            "status": "success",
            "character_name": character_name,
            "generated_image": generated_image_path,
            "text_prompt_results": results,
            "average_text_similarity": float(avg_score),
            "text_quality": "GOOD" if avg_score > 0.3 else "NEEDS_IMPROVEMENT"
        }

    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "character_name": character_name
        }

def comprehensive_quality_check(
    generated_image_path: str,
    character_name: str,
    prompt_used: str
) -> Dict[str, Any]:
    """Run comprehensive quality verification"""

    results = {}

    # 1. CLIP similarity with reference images
    clip_result = verify_lora_quality(generated_image_path, character_name)
    results["clip_verification"] = clip_result

    # 2. Text-image alignment check
    expected_prompts = [
        f"{character_name}",
        f"{character_name} character",
        prompt_used
    ]

    if character_name == "mario":
        expected_prompts.extend([
            "mario super mario character",
            "red cap blue overalls",
            "nintendo character",
            "video game character"
        ])

    text_result = text_similarity_check(generated_image_path, character_name, expected_prompts)
    results["text_alignment"] = text_result

    # 3. Overall assessment
    overall_quality = "UNKNOWN"
    if clip_result["status"] == "success" and text_result["status"] == "success":
        clip_quality = clip_result["quality_assessment"]
        text_quality = text_result["text_quality"]

        if clip_quality in ["EXCELLENT", "GOOD"] and text_quality == "GOOD":
            overall_quality = "EXCELLENT"
        elif clip_quality in ["GOOD", "ACCEPTABLE"] and text_quality == "GOOD":
            overall_quality = "GOOD"
        elif clip_quality == "ACCEPTABLE":
            overall_quality = "ACCEPTABLE"
        else:
            overall_quality = "POOR"

    results["overall_assessment"] = {
        "quality": overall_quality,
        "character_name": character_name,
        "generated_image": generated_image_path,
        "verification_complete": True
    }

    return results

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage:")
        print("  python quality_verification.py <image_path> <character_name> [prompt]")
        print("  python quality_verification.py /path/to/mario.png mario")
        print("  python quality_verification.py /path/to/mario.png mario 'mario standing'")
        sys.exit(1)

    image_path = sys.argv[1]
    character = sys.argv[2]
    prompt = sys.argv[3] if len(sys.argv) > 3 else f"{character} character"

    print(f"Running quality verification for {character}...")
    print(f"Image: {image_path}")
    print(f"Prompt: {prompt}")
    print()

    result = comprehensive_quality_check(image_path, character, prompt)
    print(json.dumps(result, indent=2))