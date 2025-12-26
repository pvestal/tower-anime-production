"""
Unified Embedding Pipeline for Character, Pose, and Style Vectors
Standardized process to convert any visual element into searchable embeddings
"""

import io
import base64
import hashlib
import logging
from typing import Dict, Any, List, Optional, Tuple, Union
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
import numpy as np
from PIL import Image
import torch
import torchvision.transforms as transforms

# CLIP for image embeddings
from transformers import CLIPProcessor, CLIPModel, CLIPVisionModel, CLIPTextModel

# Sentence transformers for text embeddings
from sentence_transformers import SentenceTransformer

# Database connections
import psycopg2
from psycopg2.extras import Json, RealDictCursor
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, Distance, VectorParams

logger = logging.getLogger(__name__)


class EmbeddingType(Enum):
    """Types of embeddings supported"""
    CHARACTER = "character"
    POSE = "pose"
    STYLE = "style"
    SCENE = "scene"
    EMOTION = "emotion"
    OBJECT = "object"
    COMPOSITION = "composition"


@dataclass
class EmbeddingResult:
    """Result of embedding generation"""
    embedding_id: str
    vector: np.ndarray
    embedding_type: EmbeddingType
    metadata: Dict[str, Any]
    source_hash: str
    created_at: datetime


class UnifiedEmbeddingPipeline:
    """
    Unified pipeline for generating and managing all types of embeddings
    """

    def __init__(self,
                 postgres_config: Dict[str, Any],
                 qdrant_url: str = "http://localhost:6333",
                 device: str = "cuda" if torch.cuda.is_available() else "cpu"):

        self.device = device
        self.postgres_config = postgres_config
        self.qdrant_client = QdrantClient(url=qdrant_url)

        # Initialize models
        self._initialize_models()

        # Initialize database connections
        self._initialize_databases()

        # Processing cache
        self.cache = {}

    def _initialize_models(self):
        """Initialize embedding models"""
        logger.info(f"Initializing embedding models on {self.device}")

        # CLIP for image embeddings (visual similarity)
        self.clip_model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
        self.clip_processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
        self.clip_model.to(self.device)
        self.clip_model.eval()

        # Sentence transformer for text embeddings (semantic search)
        self.text_embedder = SentenceTransformer('all-MiniLM-L6-v2')

        # Image transforms for preprocessing
        self.image_transform = transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406],
                               std=[0.229, 0.224, 0.225])
        ])

    def _initialize_databases(self):
        """Initialize database connections and ensure schema exists"""
        # PostgreSQL for metadata
        self.pg_conn = psycopg2.connect(**self.postgres_config)
        self.pg_cursor = self.pg_conn.cursor(cursor_factory=RealDictCursor)

        # Create embeddings table if not exists
        self.pg_cursor.execute("""
            CREATE TABLE IF NOT EXISTS unified_embeddings (
                embedding_id VARCHAR(64) PRIMARY KEY,
                embedding_type VARCHAR(50) NOT NULL,
                source_type VARCHAR(50) NOT NULL,
                source_data TEXT,
                source_hash VARCHAR(64) NOT NULL,
                metadata JSONB,
                vector_dimension INTEGER,
                collection_name VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(source_hash, embedding_type)
            );

            CREATE INDEX IF NOT EXISTS idx_embedding_type ON unified_embeddings(embedding_type);
            CREATE INDEX IF NOT EXISTS idx_source_hash ON unified_embeddings(source_hash);
            CREATE INDEX IF NOT EXISTS idx_created_at ON unified_embeddings(created_at DESC);
        """)
        self.pg_conn.commit()

        # Ensure Qdrant collections exist
        self._ensure_qdrant_collections()

    def _ensure_qdrant_collections(self):
        """Ensure Qdrant collections exist for each embedding type"""
        collections = {
            "character_embeddings": 512,  # CLIP dimension
            "pose_embeddings": 512,
            "style_embeddings": 512,
            "scene_embeddings": 384,  # Text embeddings
            "unified_embeddings": 768  # Combined embeddings
        }

        existing = [col.name for col in self.qdrant_client.get_collections().collections]

        for collection_name, dimension in collections.items():
            if collection_name not in existing:
                logger.info(f"Creating Qdrant collection: {collection_name}")
                self.qdrant_client.create_collection(
                    collection_name=collection_name,
                    vectors_config=VectorParams(
                        size=dimension,
                        distance=Distance.COSINE
                    )
                )

    def generate_embedding(self,
                          source: Union[str, Image.Image, np.ndarray],
                          embedding_type: EmbeddingType,
                          metadata: Optional[Dict[str, Any]] = None) -> EmbeddingResult:
        """
        Generate embedding for any source type

        Args:
            source: Image path, PIL Image, numpy array, or text
            embedding_type: Type of embedding to generate
            metadata: Additional metadata to store

        Returns:
            EmbeddingResult with embedding vector and metadata
        """
        # Generate source hash for deduplication
        source_hash = self._generate_source_hash(source, embedding_type)

        # Check cache
        cache_key = f"{source_hash}_{embedding_type.value}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        # Check if embedding already exists in database
        existing = self._get_existing_embedding(source_hash, embedding_type)
        if existing:
            return existing

        # Generate new embedding
        if isinstance(source, str) and source.endswith(('.jpg', '.png', '.jpeg')):
            # Image file path
            vector = self._generate_image_embedding_from_path(source)
            source_type = "image_path"
        elif isinstance(source, Image.Image):
            # PIL Image
            vector = self._generate_image_embedding(source)
            source_type = "pil_image"
        elif isinstance(source, np.ndarray):
            # Numpy array (image)
            image = Image.fromarray(source)
            vector = self._generate_image_embedding(image)
            source_type = "numpy_array"
        elif isinstance(source, str):
            # Text
            vector = self._generate_text_embedding(source)
            source_type = "text"
        else:
            raise ValueError(f"Unsupported source type: {type(source)}")

        # Create embedding ID
        embedding_id = hashlib.sha256(
            f"{source_hash}_{embedding_type.value}_{datetime.now().isoformat()}".encode()
        ).hexdigest()[:16]

        # Prepare metadata
        if metadata is None:
            metadata = {}

        metadata.update({
            "embedding_type": embedding_type.value,
            "source_type": source_type,
            "vector_dimension": len(vector)
        })

        # Store in database
        result = EmbeddingResult(
            embedding_id=embedding_id,
            vector=vector,
            embedding_type=embedding_type,
            metadata=metadata,
            source_hash=source_hash,
            created_at=datetime.now()
        )

        self._store_embedding(result)

        # Cache result
        self.cache[cache_key] = result

        return result

    def _generate_image_embedding_from_path(self, image_path: str) -> np.ndarray:
        """Generate embedding from image file path"""
        image = Image.open(image_path).convert('RGB')
        return self._generate_image_embedding(image)

    def _generate_image_embedding(self, image: Image.Image) -> np.ndarray:
        """Generate CLIP embedding for image"""
        with torch.no_grad():
            inputs = self.clip_processor(images=image, return_tensors="pt")
            inputs = {k: v.to(self.device) for k, v in inputs.items()}

            # Get image features from CLIP
            image_features = self.clip_model.get_image_features(**inputs)

            # Normalize features
            image_features = image_features / image_features.norm(dim=-1, keepdim=True)

            # Convert to numpy
            embedding = image_features.cpu().numpy().squeeze()

        return embedding

    def _generate_text_embedding(self, text: str) -> np.ndarray:
        """Generate text embedding using sentence transformer"""
        embedding = self.text_embedder.encode(text)
        return embedding

    def _generate_source_hash(self, source: Any, embedding_type: EmbeddingType) -> str:
        """Generate hash for source data"""
        if isinstance(source, str):
            # For text or file paths
            hash_input = source.encode()
        elif isinstance(source, Image.Image):
            # For PIL images
            buffer = io.BytesIO()
            source.save(buffer, format='PNG')
            hash_input = buffer.getvalue()
        elif isinstance(source, np.ndarray):
            # For numpy arrays
            hash_input = source.tobytes()
        else:
            hash_input = str(source).encode()

        return hashlib.sha256(hash_input).hexdigest()

    def _get_existing_embedding(self, source_hash: str,
                               embedding_type: EmbeddingType) -> Optional[EmbeddingResult]:
        """Check if embedding already exists in database"""
        self.pg_cursor.execute("""
            SELECT embedding_id, metadata, created_at
            FROM unified_embeddings
            WHERE source_hash = %s AND embedding_type = %s
        """, (source_hash, embedding_type.value))

        row = self.pg_cursor.fetchone()
        if row:
            # Retrieve vector from Qdrant
            collection_name = self._get_collection_name(embedding_type)

            try:
                points = self.qdrant_client.retrieve(
                    collection_name=collection_name,
                    ids=[row['embedding_id']]
                )

                if points:
                    vector = np.array(points[0].vector)

                    return EmbeddingResult(
                        embedding_id=row['embedding_id'],
                        vector=vector,
                        embedding_type=embedding_type,
                        metadata=row['metadata'],
                        source_hash=source_hash,
                        created_at=row['created_at']
                    )
            except Exception as e:
                logger.error(f"Error retrieving existing embedding: {e}")

        return None

    def _store_embedding(self, result: EmbeddingResult):
        """Store embedding in both PostgreSQL and Qdrant"""
        # Store metadata in PostgreSQL
        self.pg_cursor.execute("""
            INSERT INTO unified_embeddings (
                embedding_id, embedding_type, source_type, source_hash,
                metadata, vector_dimension, collection_name
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (source_hash, embedding_type) DO UPDATE SET
                updated_at = CURRENT_TIMESTAMP
        """, (
            result.embedding_id,
            result.embedding_type.value,
            result.metadata.get('source_type', 'unknown'),
            result.source_hash,
            Json(result.metadata),
            len(result.vector),
            self._get_collection_name(result.embedding_type)
        ))
        self.pg_conn.commit()

        # Store vector in Qdrant
        collection_name = self._get_collection_name(result.embedding_type)

        point = PointStruct(
            id=result.embedding_id,
            vector=result.vector.tolist(),
            payload={
                "embedding_type": result.embedding_type.value,
                "source_hash": result.source_hash,
                "created_at": result.created_at.isoformat(),
                **result.metadata
            }
        )

        self.qdrant_client.upsert(
            collection_name=collection_name,
            points=[point]
        )

    def _get_collection_name(self, embedding_type: EmbeddingType) -> str:
        """Get Qdrant collection name for embedding type"""
        collection_map = {
            EmbeddingType.CHARACTER: "character_embeddings",
            EmbeddingType.POSE: "pose_embeddings",
            EmbeddingType.STYLE: "style_embeddings",
            EmbeddingType.SCENE: "scene_embeddings",
            EmbeddingType.EMOTION: "unified_embeddings",
            EmbeddingType.OBJECT: "unified_embeddings",
            EmbeddingType.COMPOSITION: "unified_embeddings"
        }
        return collection_map.get(embedding_type, "unified_embeddings")

    def search_similar(self,
                       query: Union[str, Image.Image, np.ndarray],
                       embedding_type: EmbeddingType,
                       limit: int = 10,
                       score_threshold: float = 0.0) -> List[Dict[str, Any]]:
        """
        Search for similar embeddings

        Args:
            query: Query image or text
            embedding_type: Type of embedding to search
            limit: Maximum number of results
            score_threshold: Minimum similarity score

        Returns:
            List of similar items with scores and metadata
        """
        # Generate query embedding
        if isinstance(query, str) and not query.endswith(('.jpg', '.png', '.jpeg')):
            query_vector = self._generate_text_embedding(query)
        else:
            if isinstance(query, str):
                image = Image.open(query).convert('RGB')
            elif isinstance(query, np.ndarray):
                image = Image.fromarray(query)
            else:
                image = query

            query_vector = self._generate_image_embedding(image)

        # Search in Qdrant
        collection_name = self._get_collection_name(embedding_type)

        from qdrant_client.models import SearchRequest

        response = self.qdrant_client.http.points_api.search_points(
            collection_name=collection_name,
            consistency=None,
            search_request=SearchRequest(
                vector=query_vector.tolist(),
                limit=limit,
                score_threshold=score_threshold if score_threshold > 0 else None,
                with_payload=True
            )
        )

        results = []
        if hasattr(response, 'result') and response.result:
            for point in response.result:
                # Get additional metadata from PostgreSQL
                self.pg_cursor.execute("""
                    SELECT metadata FROM unified_embeddings
                    WHERE embedding_id = %s
                """, (point.id,))

                row = self.pg_cursor.fetchone()
                metadata = row['metadata'] if row else {}

                results.append({
                    "embedding_id": point.id,
                    "score": point.score,
                    "embedding_type": embedding_type.value,
                    "metadata": metadata,
                    "payload": point.payload
                })

        return results

    def create_composite_embedding(self,
                                  embeddings: List[Tuple[EmbeddingResult, float]]) -> np.ndarray:
        """
        Create a weighted composite embedding from multiple sources

        Args:
            embeddings: List of (EmbeddingResult, weight) tuples

        Returns:
            Composite embedding vector
        """
        if not embeddings:
            raise ValueError("At least one embedding required")

        # Normalize weights
        total_weight = sum(weight for _, weight in embeddings)
        normalized_weights = [weight / total_weight for _, weight in embeddings]

        # Weighted average of embeddings
        composite = np.zeros_like(embeddings[0][0].vector)

        for (embedding, _), weight in zip(embeddings, normalized_weights):
            composite += embedding.vector * weight

        # Normalize the composite
        composite = composite / np.linalg.norm(composite)

        return composite

    def batch_generate_embeddings(self,
                                 sources: List[Any],
                                 embedding_type: EmbeddingType,
                                 batch_size: int = 32) -> List[EmbeddingResult]:
        """
        Generate embeddings for multiple sources in batches

        Args:
            sources: List of sources to embed
            embedding_type: Type of embedding
            batch_size: Batch size for processing

        Returns:
            List of EmbeddingResults
        """
        results = []

        for i in range(0, len(sources), batch_size):
            batch = sources[i:i + batch_size]

            for source in batch:
                try:
                    result = self.generate_embedding(source, embedding_type)
                    results.append(result)
                except Exception as e:
                    logger.error(f"Error generating embedding for source: {e}")
                    continue

        return results

    def cleanup_cache(self):
        """Clear the embedding cache"""
        self.cache.clear()
        logger.info("Embedding cache cleared")

    def close(self):
        """Close database connections"""
        if hasattr(self, 'pg_conn'):
            self.pg_conn.close()
        logger.info("Database connections closed")