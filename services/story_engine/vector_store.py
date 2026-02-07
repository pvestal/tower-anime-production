"""
Story Bible Vector Store
Embeds and indexes all story content in Qdrant for semantic retrieval.
Echo Brain's NarrationAgent and WritingAgent query this for context assembly.
"""

import hashlib
import json
import logging
from typing import Optional

import httpx
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

logger = logging.getLogger(__name__)

QDRANT_HOST = "localhost"
QDRANT_PORT = 6333
COLLECTION_NAME = "story_bible"

# Use mxbai-embed-large based on Phase 0 findings (available in Ollama)
EMBEDDING_MODEL = "mxbai-embed-large"
EMBEDDING_DIM = 1024


class StoryVectorStore:
    """Manages Qdrant vectors for all story bible content."""

    def __init__(self):
        self.client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
        self._ensure_collection()

    def _ensure_collection(self):
        """Create collection if it doesn't exist."""
        collections = [c.name for c in self.client.get_collections().collections]
        if COLLECTION_NAME not in collections:
            self.client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(
                    size=EMBEDDING_DIM,
                    distance=Distance.COSINE,
                ),
            )
            logger.info(f"Created Qdrant collection: {COLLECTION_NAME}")

    def _get_embedding(self, text: str) -> list[float]:
        """Get embedding from Ollama."""
        response = httpx.post(
            "http://localhost:11434/api/embeddings",
            json={"model": EMBEDDING_MODEL, "prompt": text},
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()["embedding"]

    def _content_hash(self, text: str) -> str:
        """SHA256 hash for deduplication / change detection."""
        return hashlib.sha256(text.encode()).hexdigest()[:16]

    def upsert_story_content(
        self,
        content_id: str,
        text: str,
        metadata: dict,
    ) -> str:
        """
        Embed and store story content.

        Args:
            content_id: Unique identifier like 'character:5' or 'scene:12:narrative'
            text: The text to embed
            metadata: Must include 'project_id', 'content_type', and any filtering fields
                      content_type: character, scene, episode, arc, world_rule, dialogue

        Returns:
            The point ID used in Qdrant
        """
        required_keys = {"project_id", "content_type"}
        if not required_keys.issubset(metadata.keys()):
            raise ValueError(f"metadata must include {required_keys}")

        embedding = self._get_embedding(text)
        content_hash = self._content_hash(text)

        # Deterministic point ID from content_id
        point_id = int(hashlib.md5(content_id.encode()).hexdigest()[:15], 16)

        point = PointStruct(
            id=point_id,
            vector=embedding,
            payload={
                "content_id": content_id,
                "text": text,
                "content_hash": content_hash,
                **metadata,
            },
        )

        self.client.upsert(collection_name=COLLECTION_NAME, points=[point])
        logger.info(f"Upserted vector: {content_id} (hash: {content_hash})")
        return str(point_id)

    def search(
        self,
        query: str,
        project_id: Optional[int] = None,
        content_type: Optional[str] = None,
        limit: int = 10,
        score_threshold: float = 0.5,
    ) -> list[dict]:
        """
        Semantic search across story bible.

        Returns list of dicts with 'content_id', 'text', 'score', and all metadata.
        """
        embedding = self._get_embedding(query)

        filters = []
        if project_id is not None:
            filters.append(FieldCondition(key="project_id", match=MatchValue(value=project_id)))
        if content_type is not None:
            filters.append(FieldCondition(key="content_type", match=MatchValue(value=content_type)))

        query_filter = Filter(must=filters) if filters else None

        # Use query_points method with query_filter
        results = self.client.query_points(
            collection_name=COLLECTION_NAME,
            query=embedding,
            query_filter=query_filter,
            limit=limit,
            score_threshold=score_threshold,
        )

        # results is a QueryResponse object with a 'points' attribute
        return [
            {
                "content_id": r.payload.get("content_id"),
                "text": r.payload.get("text"),
                "score": r.score,
                **{k: v for k, v in r.payload.items() if k not in ("content_id", "text", "content_hash")},
            }
            for r in results.points
        ]

    def find_contradictions(self, character_id: int, new_dialogue: str, project_id: int) -> list[dict]:
        """
        Check if new dialogue contradicts established character patterns.
        Returns similar past dialogue that might conflict.
        """
        return self.search(
            query=new_dialogue,
            project_id=project_id,
            content_type="dialogue",
            limit=5,
            score_threshold=0.7,
        )

    def find_thematic_scenes(self, theme: str, project_id: int) -> list[dict]:
        """Find scenes that share a thematic thread."""
        return self.search(
            query=theme,
            project_id=project_id,
            content_type="scene",
            limit=20,
            score_threshold=0.55,
        )

    def get_collection_stats(self) -> dict:
        """Return collection info for health checks."""
        try:
            info = self.client.get_collection(COLLECTION_NAME)
            return {
                "collection": COLLECTION_NAME,
                "points_count": info.points_count if hasattr(info, 'points_count') else 0,
                "vectors_count": info.vectors_count if hasattr(info, 'vectors_count') else info.points_count if hasattr(info, 'points_count') else 0,
                "status": str(info.status) if hasattr(info, 'status') else "ok",
            }
        except Exception as e:
            return {"collection": COLLECTION_NAME, "error": str(e)}