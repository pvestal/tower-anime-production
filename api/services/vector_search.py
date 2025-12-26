"""
Vector Search Service for Project Chimera
Implements semantic search using Qdrant vector database
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import numpy as np

from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
    Filter, FieldCondition, MatchValue,
    SearchRequest, ScoredPoint
)

logger = logging.getLogger(__name__)

class VectorSearchService:
    """
    Manages vector embeddings and semantic search for character generations
    """

    def __init__(
        self,
        qdrant_url: str = "http://localhost:6333",
        collection_name: str = "character_embeddings",
        model_name: str = "all-MiniLM-L6-v2"
    ):
        self.qdrant_url = qdrant_url
        self.collection_name = collection_name
        self.client = QdrantClient(url=qdrant_url)
        self.embedder = SentenceTransformer(model_name)
        self.embedding_dim = 384  # all-MiniLM-L6-v2 dimension

        # Ensure collection exists
        self._ensure_collection()

    def _ensure_collection(self):
        """Ensure the Qdrant collection exists with proper configuration"""
        try:
            collections = self.client.get_collections().collections
            collection_names = [col.name for col in collections]

            if self.collection_name not in collection_names:
                logger.info(f"Creating collection: {self.collection_name}")
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=self.embedding_dim,
                        distance=Distance.COSINE
                    )
                )
                logger.info(f"Collection {self.collection_name} created")
            else:
                logger.info(f"Collection {self.collection_name} already exists")

        except Exception as e:
            logger.error(f"Error ensuring collection: {e}")
            raise

    def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding vector for given text

        Args:
            text: Text to embed

        Returns:
            List of float values representing the embedding
        """
        try:
            embedding = self.embedder.encode(text)
            return embedding.tolist()
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            raise

    def add_character(
        self,
        character_id: int,
        character_name: str,
        prompt: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Add a character to the vector database

        Args:
            character_id: Unique ID for the character
            character_name: Name of the character
            prompt: Character description prompt
            metadata: Additional metadata to store

        Returns:
            True if successful, False otherwise
        """
        try:
            # Generate embedding from character info
            text = f"{character_name}: {prompt}"
            embedding = self.generate_embedding(text)

            # Prepare payload
            payload = {
                "character_id": character_id,
                "character_name": character_name,
                "prompt": prompt,
                "indexed_at": datetime.now().isoformat()
            }

            if metadata:
                payload.update(metadata)

            # Create point
            point = PointStruct(
                id=character_id,
                vector=embedding,
                payload=payload
            )

            # Upsert to Qdrant
            self.client.upsert(
                collection_name=self.collection_name,
                points=[point]
            )

            logger.info(f"Added character {character_name} (ID: {character_id}) to vector database")
            return True

        except Exception as e:
            logger.error(f"Error adding character to vector database: {e}")
            return False

    def search_characters(
        self,
        query: str,
        limit: int = 10,
        score_threshold: float = 0.0,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for characters using semantic similarity

        Args:
            query: Search query text
            limit: Maximum number of results
            score_threshold: Minimum similarity score (0-1)
            filters: Optional filters for the search

        Returns:
            List of search results with scores and metadata
        """
        try:
            # Generate query embedding
            query_embedding = self.generate_embedding(query)

            # Build filter if provided
            qdrant_filter = None
            if filters:
                conditions = []
                for key, value in filters.items():
                    conditions.append(
                        FieldCondition(
                            key=key,
                            match=MatchValue(value=value)
                        )
                    )
                if conditions:
                    qdrant_filter = Filter(must=conditions)

            # Perform search using the client query_points method
            response = self.client.query_points(
                collection_name=self.collection_name,
                query=query_embedding,
                limit=limit,
                query_filter=qdrant_filter,
                score_threshold=score_threshold if score_threshold > 0 else None,
                with_payload=True
            )

            # Get search results from response
            search_results = response.points if hasattr(response, 'points') else []

            # Parse results
            results = []
            if search_results:
                for point in search_results:
                    result = {
                        "id": point.id,
                        "score": point.score,
                        **point.payload
                    }
                    results.append(result)

            logger.info(f"Search query '{query}' returned {len(results)} results")
            return results

        except Exception as e:
            logger.error(f"Error searching characters: {e}")
            return []

    def find_similar_characters(
        self,
        character_id: int,
        limit: int = 10,
        exclude_self: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Find characters similar to a given character

        Args:
            character_id: ID of the character to find similar ones for
            limit: Maximum number of results
            exclude_self: Whether to exclude the input character from results

        Returns:
            List of similar characters
        """
        try:
            # Get the character's vector
            character = self.client.retrieve(
                collection_name=self.collection_name,
                ids=[character_id]
            )

            if not character:
                logger.warning(f"Character {character_id} not found in vector database")
                return []

            # Use the character's vector for search
            vector = character[0].vector

            # Search for similar
            response = self.client.query_points(
                collection_name=self.collection_name,
                query=vector,
                limit=limit + 1 if exclude_self else limit,
                with_payload=True
            )

            # Get search results from response
            search_results = response.points if hasattr(response, 'points') else []

            # Parse results
            results = []
            if search_results:
                for point in search_results:
                    if exclude_self and point.id == character_id:
                        continue
                    result = {
                        "id": point.id,
                        "score": point.score,
                        **point.payload
                    }
                    results.append(result)

            return results[:limit]

        except Exception as e:
            logger.error(f"Error finding similar characters: {e}")
            return []

    def update_character_embedding(
        self,
        character_id: int,
        character_name: str,
        prompt: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Update the embedding for an existing character

        Args:
            character_id: ID of the character to update
            character_name: Updated character name
            prompt: Updated prompt
            metadata: Updated metadata

        Returns:
            True if successful, False otherwise
        """
        # This is the same as add_character since we use upsert
        return self.add_character(character_id, character_name, prompt, metadata)

    def delete_character(self, character_id: int) -> bool:
        """
        Delete a character from the vector database

        Args:
            character_id: ID of the character to delete

        Returns:
            True if successful, False otherwise
        """
        try:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=[character_id]
            )
            logger.info(f"Deleted character {character_id} from vector database")
            return True
        except Exception as e:
            logger.error(f"Error deleting character: {e}")
            return False

    def get_collection_info(self) -> Dict[str, Any]:
        """
        Get information about the vector collection

        Returns:
            Dictionary with collection statistics
        """
        try:
            info = self.client.get_collection(self.collection_name)
            return {
                "name": self.collection_name,
                "vectors_count": info.vectors_count,
                "points_count": info.points_count,
                "indexed_vectors_count": info.indexed_vectors_count,
                "status": info.status,
                "config": {
                    "vector_size": info.config.params.vectors.size,
                    "distance": str(info.config.params.vectors.distance)
                }
            }
        except Exception as e:
            logger.error(f"Error getting collection info: {e}")
            return {}