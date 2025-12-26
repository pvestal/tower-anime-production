"""
Character Consistency System for Animation Production
Maintains visual consistency of characters across generations using IPAdapter and embeddings
"""

import json
import uuid
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass
import numpy as np
from pathlib import Path
import hashlib

from PIL import Image
import torch
from transformers import CLIPProcessor, CLIPModel

from .unified_embedding_pipeline import UnifiedEmbeddingPipeline, EmbeddingType
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, Distance, VectorParams, Filter, FieldCondition, MatchValue

logger = logging.getLogger(__name__)


@dataclass
class CharacterProfile:
    """Complete character profile with visual references"""
    character_id: str
    name: str
    description: str
    reference_images: List[str]  # Paths to reference images
    embedding_ids: List[str]     # Qdrant embedding IDs
    visual_traits: Dict[str, Any]  # Extracted visual characteristics
    style_preferences: List[str]   # Preferred art styles
    generation_count: int = 0
    created_at: datetime = None
    updated_at: datetime = None
    metadata: Dict[str, Any] = None


class CharacterConsistencyManager:
    """
    Manages character consistency across all generations.
    Uses IPAdapter for visual consistency and maintains character embedding library.
    """

    def __init__(self,
                 embedding_pipeline: UnifiedEmbeddingPipeline,
                 qdrant_client: QdrantClient,
                 storage_path: str = "/opt/tower-anime-production/character_library"):

        self.embedding_pipeline = embedding_pipeline
        self.qdrant_client = qdrant_client
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

        # Character cache
        self.character_cache: Dict[str, CharacterProfile] = {}

        # Initialize CLIP for visual analysis
        self._init_clip_model()

        # Ensure character collection exists
        self._ensure_character_collection()

    def _init_clip_model(self):
        """Initialize CLIP model for visual analysis"""
        self.clip_model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
        self.clip_processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")

        if torch.cuda.is_available():
            self.clip_model = self.clip_model.cuda()
        self.clip_model.eval()

    def _ensure_character_collection(self):
        """Ensure dedicated character collection exists in Qdrant"""
        collection_name = "character_library"

        existing = [col.name for col in self.qdrant_client.get_collections().collections]

        if collection_name not in existing:
            logger.info(f"Creating character library collection")
            self.qdrant_client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=512,  # CLIP dimension
                    distance=Distance.COSINE
                )
            )

    async def create_character_profile(self,
                                      name: str,
                                      description: str,
                                      reference_images: List[str],
                                      style_preferences: List[str] = None) -> CharacterProfile:
        """
        Create a new character profile with visual embeddings

        Args:
            name: Character name
            description: Text description of character
            reference_images: List of reference image paths
            style_preferences: Preferred generation styles

        Returns:
            Complete character profile
        """
        character_id = str(uuid.uuid4())

        # Extract visual traits from reference images
        visual_traits = await self._extract_visual_traits(reference_images)

        # Generate embeddings for each reference image
        embedding_ids = []
        for img_path in reference_images:
            embedding_result = self.embedding_pipeline.generate_embedding(
                source=img_path,
                embedding_type=EmbeddingType.CHARACTER,
                metadata={
                    "character_id": character_id,
                    "character_name": name,
                    "image_path": img_path
                }
            )
            embedding_ids.append(embedding_result.embedding_id)

            # Store in character library
            self._store_character_embedding(
                character_id=character_id,
                character_name=name,
                embedding_id=embedding_result.embedding_id,
                vector=embedding_result.vector,
                image_path=img_path
            )

        # Create profile
        profile = CharacterProfile(
            character_id=character_id,
            name=name,
            description=description,
            reference_images=reference_images,
            embedding_ids=embedding_ids,
            visual_traits=visual_traits,
            style_preferences=style_preferences or [],
            created_at=datetime.now(),
            updated_at=datetime.now(),
            metadata={}
        )

        # Save to disk
        self._save_character_profile(profile)

        # Cache
        self.character_cache[character_id] = profile

        logger.info(f"Created character profile: {name} ({character_id})")
        return profile

    async def _extract_visual_traits(self, reference_images: List[str]) -> Dict[str, Any]:
        """Extract visual characteristics from reference images"""
        traits = {
            "hair_colors": [],
            "eye_colors": [],
            "clothing_styles": [],
            "accessories": [],
            "facial_features": [],
            "body_type": None,
            "age_appearance": None,
            "distinctive_marks": []
        }

        # Analyze each image with CLIP
        for img_path in reference_images:
            image = Image.open(img_path).convert('RGB')

            # Define trait prompts
            trait_prompts = {
                "hair_color": [
                    "black hair", "blonde hair", "brown hair", "red hair",
                    "blue hair", "pink hair", "white hair", "silver hair"
                ],
                "eye_color": [
                    "blue eyes", "brown eyes", "green eyes", "red eyes",
                    "purple eyes", "gold eyes", "heterochromia"
                ],
                "age": [
                    "child", "teenager", "young adult", "adult", "elderly"
                ],
                "clothing": [
                    "school uniform", "casual clothes", "formal wear",
                    "fantasy outfit", "military uniform", "traditional clothing"
                ]
            }

            # Compute similarities for each trait category
            for trait_type, prompts in trait_prompts.items():
                inputs = self.clip_processor(
                    text=prompts,
                    images=[image] * len(prompts),
                    return_tensors="pt",
                    padding=True
                )

                if torch.cuda.is_available():
                    inputs = {k: v.cuda() for k, v in inputs.items()}

                with torch.no_grad():
                    outputs = self.clip_model(**inputs)
                    logits = outputs.logits_per_image[0]
                    probs = logits.softmax(dim=-1).cpu().numpy()

                # Get top matches
                top_idx = np.argmax(probs)
                if probs[top_idx] > 0.3:  # Confidence threshold
                    detected_trait = prompts[top_idx]

                    if trait_type == "hair_color" and detected_trait not in traits["hair_colors"]:
                        traits["hair_colors"].append(detected_trait)
                    elif trait_type == "eye_color" and detected_trait not in traits["eye_colors"]:
                        traits["eye_colors"].append(detected_trait)
                    elif trait_type == "age":
                        traits["age_appearance"] = detected_trait
                    elif trait_type == "clothing" and detected_trait not in traits["clothing_styles"]:
                        traits["clothing_styles"].append(detected_trait)

        return traits

    def _store_character_embedding(self,
                                  character_id: str,
                                  character_name: str,
                                  embedding_id: str,
                                  vector: np.ndarray,
                                  image_path: str):
        """Store character embedding in dedicated collection"""
        point = PointStruct(
            id=embedding_id,
            vector=vector.tolist(),
            payload={
                "character_id": character_id,
                "character_name": character_name,
                "image_path": image_path,
                "created_at": datetime.now().isoformat()
            }
        )

        self.qdrant_client.upsert(
            collection_name="character_library",
            points=[point]
        )

    def get_character_profile(self, character_id: str) -> Optional[CharacterProfile]:
        """Retrieve character profile by ID"""
        # Check cache first
        if character_id in self.character_cache:
            return self.character_cache[character_id]

        # Load from disk
        profile_path = self.storage_path / f"{character_id}.json"
        if profile_path.exists():
            with open(profile_path, 'r') as f:
                data = json.load(f)
                profile = CharacterProfile(**data)
                self.character_cache[character_id] = profile
                return profile

        return None

    def _save_character_profile(self, profile: CharacterProfile):
        """Save character profile to disk"""
        profile_path = self.storage_path / f"{profile.character_id}.json"

        # Convert to dict for JSON serialization
        data = {
            "character_id": profile.character_id,
            "name": profile.name,
            "description": profile.description,
            "reference_images": profile.reference_images,
            "embedding_ids": profile.embedding_ids,
            "visual_traits": profile.visual_traits,
            "style_preferences": profile.style_preferences,
            "generation_count": profile.generation_count,
            "created_at": profile.created_at.isoformat() if profile.created_at else None,
            "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
            "metadata": profile.metadata or {}
        }

        with open(profile_path, 'w') as f:
            json.dump(data, f, indent=2)

    def get_character_embeddings(self, character_id: str) -> List[np.ndarray]:
        """Get all embeddings for a character"""
        profile = self.get_character_profile(character_id)
        if not profile:
            return []

        embeddings = []
        for embedding_id in profile.embedding_ids:
            points = self.qdrant_client.retrieve(
                collection_name="character_library",
                ids=[embedding_id]
            )
            if points:
                embeddings.append(np.array(points[0].vector))

        return embeddings

    def get_best_reference_for_pose(self,
                                   character_id: str,
                                   pose_description: str) -> Optional[str]:
        """
        Find the best reference image for a specific pose

        Args:
            character_id: Character ID
            pose_description: Description of desired pose

        Returns:
            Path to best matching reference image
        """
        profile = self.get_character_profile(character_id)
        if not profile or not profile.reference_images:
            return None

        # Use CLIP to find best matching reference
        best_score = -1
        best_image = None

        for img_path in profile.reference_images:
            image = Image.open(img_path).convert('RGB')

            inputs = self.clip_processor(
                text=[pose_description],
                images=image,
                return_tensors="pt"
            )

            if torch.cuda.is_available():
                inputs = {k: v.cuda() for k, v in inputs.items()}

            with torch.no_grad():
                outputs = self.clip_model(**inputs)
                score = outputs.logits_per_image[0, 0].cpu().item()

            if score > best_score:
                best_score = score
                best_image = img_path

        return best_image

    def create_consistency_prompt(self, character_id: str) -> str:
        """
        Create a detailed prompt that maintains character consistency

        Args:
            character_id: Character ID

        Returns:
            Consistency prompt string
        """
        profile = self.get_character_profile(character_id)
        if not profile:
            return ""

        prompt_parts = [profile.description]

        # Add visual traits
        if profile.visual_traits:
            traits = profile.visual_traits

            if traits.get("hair_colors"):
                prompt_parts.append(", ".join(traits["hair_colors"]))

            if traits.get("eye_colors"):
                prompt_parts.append(", ".join(traits["eye_colors"]))

            if traits.get("age_appearance"):
                prompt_parts.append(traits["age_appearance"])

            if traits.get("distinctive_marks"):
                prompt_parts.extend(traits["distinctive_marks"])

        return ", ".join(prompt_parts)

    def update_character_with_generation(self,
                                        character_id: str,
                                        generated_image_path: str,
                                        add_to_references: bool = False):
        """
        Update character profile with new generation

        Args:
            character_id: Character ID
            generated_image_path: Path to newly generated image
            add_to_references: Whether to add as new reference image
        """
        profile = self.get_character_profile(character_id)
        if not profile:
            return

        profile.generation_count += 1
        profile.updated_at = datetime.now()

        if add_to_references:
            # Add to reference images
            profile.reference_images.append(generated_image_path)

            # Generate embedding for new reference
            embedding_result = self.embedding_pipeline.generate_embedding(
                source=generated_image_path,
                embedding_type=EmbeddingType.CHARACTER,
                metadata={
                    "character_id": character_id,
                    "character_name": profile.name,
                    "image_path": generated_image_path,
                    "is_generated": True
                }
            )

            profile.embedding_ids.append(embedding_result.embedding_id)

            # Store in character library
            self._store_character_embedding(
                character_id=character_id,
                character_name=profile.name,
                embedding_id=embedding_result.embedding_id,
                vector=embedding_result.vector,
                image_path=generated_image_path
            )

        # Save updated profile
        self._save_character_profile(profile)

        logger.info(f"Updated character {profile.name} with new generation")

    def find_similar_characters(self,
                               query_image: str,
                               limit: int = 5) -> List[Tuple[str, float]]:
        """
        Find characters similar to a query image

        Args:
            query_image: Path to query image
            limit: Maximum number of results

        Returns:
            List of (character_id, similarity_score) tuples
        """
        # Generate embedding for query
        query_embedding = self.embedding_pipeline.generate_embedding(
            source=query_image,
            embedding_type=EmbeddingType.CHARACTER
        )

        # Search in character library
        from qdrant_client.models import SearchRequest

        response = self.qdrant_client.http.points_api.search_points(
            collection_name="character_library",
            consistency=None,
            search_request=SearchRequest(
                vector=query_embedding.vector.tolist(),
                limit=limit * 3,  # Get more to aggregate by character
                with_payload=True
            )
        )

        # Aggregate scores by character
        character_scores = {}

        if hasattr(response, 'result') and response.result:
            for point in response.result:
                char_id = point.payload.get("character_id")
                if char_id:
                    if char_id not in character_scores:
                        character_scores[char_id] = []
                    character_scores[char_id].append(point.score)

        # Average scores per character
        character_avg_scores = [
            (char_id, np.mean(scores))
            for char_id, scores in character_scores.items()
        ]

        # Sort by score and return top results
        character_avg_scores.sort(key=lambda x: x[1], reverse=True)

        return character_avg_scores[:limit]

    def list_all_characters(self) -> List[CharacterProfile]:
        """List all available character profiles"""
        profiles = []

        for profile_file in self.storage_path.glob("*.json"):
            with open(profile_file, 'r') as f:
                data = json.load(f)
                profile = CharacterProfile(**data)
                profiles.append(profile)

        return profiles