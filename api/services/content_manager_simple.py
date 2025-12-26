"""
Simplified Content Manager - Personal Use
No safety restrictions, just content organization and model selection
"""
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Literal
from pathlib import Path

logger = logging.getLogger(__name__)

class ContentManager:
    """
    Simple content manager for personal use.
    Handles model selection and organization without restrictions.
    """

    def __init__(self):
        self.output_base = Path("/mnt/1TB-storage/outputs")
        self.models_base = Path("/mnt/1TB-storage/models")

    def classify_prompt(self, prompt: str) -> str:
        """
        Simple classification for organization purposes only.
        No blocking or restrictions.
        """
        prompt_lower = prompt.lower()

        # Just for organizing outputs
        if any(word in prompt_lower for word in ["nude", "naked", "explicit", "xxx"]):
            return "explicit"
        elif any(word in prompt_lower for word in ["lingerie", "bikini", "sensual", "bedroom"]):
            return "suggestive"
        elif any(word in prompt_lower for word in ["flirty", "cute", "sexy"]):
            return "mild"
        else:
            return "general"

    def get_optimal_model(self, content_type: str, style: str = "realistic") -> Dict:
        """
        Get the best model for the content type.
        """
        models = {
            "general": {
                "checkpoint": "realisticVision_v51.safetensors",
                "loras": [],
            },
            "suggestive": {
                "checkpoint": "dreamshaper_8.safetensors",
                "loras": [("add_detail.safetensors", 0.3)],
            },
            "explicit_realistic": {
                "checkpoint": "chilloutmix_NiPrunedFp32Fix.safetensors",
                "loras": [
                    ("add_detail.safetensors", 0.4),
                    ("more_details.safetensors", 0.2)
                ],
            },
            "explicit_anime": {
                "checkpoint": "Counterfeit-V2.5.safetensors",
                "loras": [("more_details.safetensors", 0.3)],
            }
        }

        if content_type == "explicit":
            return models["explicit_realistic"] if style == "realistic" else models["explicit_anime"]
        elif content_type == "suggestive":
            return models["suggestive"]
        else:
            return models["general"]

    def enhance_prompt(self, prompt: str, content_type: str) -> Dict:
        """
        Add quality tags and optimizations to prompt.
        """
        # Quality tags
        quality_tags = "masterpiece, best quality, highly detailed, sharp focus"

        # Content-specific enhancements
        if content_type == "explicit":
            enhanced = f"{prompt}, {quality_tags}, photorealistic, detailed skin texture, professional lighting"
        elif content_type == "suggestive":
            enhanced = f"{prompt}, {quality_tags}, professional photography, artistic composition"
        else:
            enhanced = f"{prompt}, {quality_tags}"

        # Standard negative prompt
        negative = "bad anatomy, bad hands, missing fingers, extra digits, worst quality, low quality"

        return {
            "positive": enhanced,
            "negative": negative
        }

    def get_storage_path(self, content_type: str) -> Path:
        """
        Get organized storage path (optional organization).
        """
        paths = {
            "general": self.output_base / "general",
            "mild": self.output_base / "mild",
            "suggestive": self.output_base / "suggestive",
            "explicit": self.output_base / "explicit"
        }

        path = paths.get(content_type, self.output_base / "general")
        path.mkdir(exist_ok=True, parents=True)
        return path

    def log_generation(self, prompt: str, content_type: str, model: str):
        """
        Simple logging for tracking what was generated.
        """
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "prompt": prompt[:100],  # First 100 chars
            "content_type": content_type,
            "model": model
        }

        log_file = self.output_base / "generation_log.jsonl"
        with open(log_file, 'a') as f:
            f.write(json.dumps(log_entry) + "\n")


# Global instance
content_manager = ContentManager()