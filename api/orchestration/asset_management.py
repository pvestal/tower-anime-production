"""
Asset Management System for Animation Production
Manages all generated assets, references, and project resources with vector search
"""

import json
import uuid
import shutil
import logging
from typing import Dict, Any, List, Optional, Tuple, Union
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field
import hashlib
from enum import Enum

import numpy as np
from PIL import Image
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, Filter, FieldCondition, MatchValue

from .unified_embedding_pipeline import UnifiedEmbeddingPipeline, EmbeddingType

logger = logging.getLogger(__name__)


class AssetType(Enum):
    """Types of assets managed by the system"""
    CHARACTER_REFERENCE = "character_reference"
    POSE_REFERENCE = "pose_reference"
    STYLE_REFERENCE = "style_reference"
    BACKGROUND = "background"
    PROP = "prop"
    GENERATED_IMAGE = "generated_image"
    GENERATED_VIDEO = "generated_video"
    AUDIO_TRACK = "audio_track"
    WORKFLOW_TEMPLATE = "workflow_template"
    SCENE_PRESET = "scene_preset"


@dataclass
class Asset:
    """Individual asset with metadata and embedding"""
    asset_id: str
    asset_type: AssetType
    name: str
    file_path: str
    thumbnail_path: Optional[str] = None
    embedding_id: Optional[str] = None
    project_id: Optional[str] = None
    character_id: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    file_size: int = 0
    file_hash: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    usage_count: int = 0


@dataclass
class AssetCollection:
    """Collection of related assets"""
    collection_id: str
    name: str
    description: str
    asset_ids: List[str]
    project_id: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


class AssetManager:
    """
    Comprehensive asset management system with vector search capabilities
    """

    def __init__(self,
                 storage_root: str = "/opt/tower-anime-production/assets",
                 embedding_pipeline: Optional[UnifiedEmbeddingPipeline] = None,
                 qdrant_client: Optional[QdrantClient] = None):

        self.storage_root = Path(storage_root)
        self.embedding_pipeline = embedding_pipeline
        self.qdrant_client = qdrant_client

        # Create directory structure
        self._initialize_storage()

        # Asset registry (in production, use database)
        self.assets: Dict[str, Asset] = {}
        self.collections: Dict[str, AssetCollection] = {}

        # Load existing assets
        self._load_asset_registry()

    def _initialize_storage(self):
        """Initialize storage directory structure"""
        directories = [
            "characters",
            "poses",
            "styles",
            "backgrounds",
            "props",
            "generated/images",
            "generated/videos",
            "audio",
            "workflows",
            "thumbnails",
            "temp"
        ]

        for dir_name in directories:
            dir_path = self.storage_root / dir_name
            dir_path.mkdir(parents=True, exist_ok=True)

    def _load_asset_registry(self):
        """Load existing asset registry from disk"""
        registry_file = self.storage_root / "asset_registry.json"

        if registry_file.exists():
            try:
                with open(registry_file, 'r') as f:
                    data = json.load(f)

                # Load assets
                for asset_data in data.get("assets", []):
                    asset = Asset(**asset_data)
                    self.assets[asset.asset_id] = asset

                # Load collections
                for collection_data in data.get("collections", []):
                    collection = AssetCollection(**collection_data)
                    self.collections[collection.collection_id] = collection

                logger.info(f"Loaded {len(self.assets)} assets and {len(self.collections)} collections")
            except Exception as e:
                logger.error(f"Failed to load asset registry: {e}")

    def _save_asset_registry(self):
        """Save asset registry to disk"""
        registry_file = self.storage_root / "asset_registry.json"

        # Convert to serializable format
        data = {
            "assets": [],
            "collections": []
        }

        for asset in self.assets.values():
            asset_data = {
                "asset_id": asset.asset_id,
                "asset_type": asset.asset_type.value,
                "name": asset.name,
                "file_path": asset.file_path,
                "thumbnail_path": asset.thumbnail_path,
                "embedding_id": asset.embedding_id,
                "project_id": asset.project_id,
                "character_id": asset.character_id,
                "tags": asset.tags,
                "metadata": asset.metadata,
                "file_size": asset.file_size,
                "file_hash": asset.file_hash,
                "created_at": asset.created_at.isoformat(),
                "updated_at": asset.updated_at.isoformat(),
                "usage_count": asset.usage_count
            }
            data["assets"].append(asset_data)

        for collection in self.collections.values():
            collection_data = {
                "collection_id": collection.collection_id,
                "name": collection.name,
                "description": collection.description,
                "asset_ids": collection.asset_ids,
                "project_id": collection.project_id,
                "tags": collection.tags,
                "created_at": collection.created_at.isoformat(),
                "updated_at": collection.updated_at.isoformat()
            }
            data["collections"].append(collection_data)

        with open(registry_file, 'w') as f:
            json.dump(data, f, indent=2)

    def import_asset(self,
                    file_path: str,
                    asset_type: AssetType,
                    name: str,
                    project_id: Optional[str] = None,
                    character_id: Optional[str] = None,
                    tags: List[str] = None,
                    metadata: Dict[str, Any] = None,
                    generate_embedding: bool = True) -> Asset:
        """
        Import an asset into the management system

        Args:
            file_path: Path to the asset file
            asset_type: Type of asset
            name: Asset name
            project_id: Associated project ID
            character_id: Associated character ID
            tags: Asset tags
            metadata: Additional metadata
            generate_embedding: Whether to generate vector embedding

        Returns:
            Created Asset object
        """
        source_path = Path(file_path)
        if not source_path.exists():
            raise FileNotFoundError(f"Asset file not found: {file_path}")

        asset_id = str(uuid.uuid4())

        # Determine storage location
        storage_dir = self._get_storage_directory(asset_type)
        file_extension = source_path.suffix
        dest_filename = f"{asset_id}{file_extension}"
        dest_path = storage_dir / dest_filename

        # Copy file to storage
        shutil.copy2(source_path, dest_path)

        # Generate file hash
        file_hash = self._calculate_file_hash(dest_path)

        # Get file size
        file_size = dest_path.stat().st_size

        # Generate thumbnail if image/video
        thumbnail_path = None
        if asset_type in [AssetType.CHARACTER_REFERENCE, AssetType.POSE_REFERENCE,
                          AssetType.STYLE_REFERENCE, AssetType.BACKGROUND,
                          AssetType.GENERATED_IMAGE]:
            thumbnail_path = self._generate_thumbnail(dest_path, asset_id)

        # Generate embedding if requested
        embedding_id = None
        if generate_embedding and self.embedding_pipeline and asset_type in [
            AssetType.CHARACTER_REFERENCE,
            AssetType.POSE_REFERENCE,
            AssetType.STYLE_REFERENCE,
            AssetType.GENERATED_IMAGE
        ]:
            embedding_type_map = {
                AssetType.CHARACTER_REFERENCE: EmbeddingType.CHARACTER,
                AssetType.POSE_REFERENCE: EmbeddingType.POSE,
                AssetType.STYLE_REFERENCE: EmbeddingType.STYLE,
                AssetType.GENERATED_IMAGE: EmbeddingType.SCENE
            }

            embedding_result = self.embedding_pipeline.generate_embedding(
                source=str(dest_path),
                embedding_type=embedding_type_map[asset_type],
                metadata={
                    "asset_id": asset_id,
                    "asset_name": name,
                    "project_id": project_id,
                    "character_id": character_id
                }
            )
            embedding_id = embedding_result.embedding_id

        # Create asset object
        asset = Asset(
            asset_id=asset_id,
            asset_type=asset_type,
            name=name,
            file_path=str(dest_path),
            thumbnail_path=thumbnail_path,
            embedding_id=embedding_id,
            project_id=project_id,
            character_id=character_id,
            tags=tags or [],
            metadata=metadata or {},
            file_size=file_size,
            file_hash=file_hash
        )

        # Register asset
        self.assets[asset_id] = asset
        self._save_asset_registry()

        logger.info(f"Imported asset: {name} ({asset_id})")
        return asset

    def _get_storage_directory(self, asset_type: AssetType) -> Path:
        """Get storage directory for asset type"""
        directory_map = {
            AssetType.CHARACTER_REFERENCE: "characters",
            AssetType.POSE_REFERENCE: "poses",
            AssetType.STYLE_REFERENCE: "styles",
            AssetType.BACKGROUND: "backgrounds",
            AssetType.PROP: "props",
            AssetType.GENERATED_IMAGE: "generated/images",
            AssetType.GENERATED_VIDEO: "generated/videos",
            AssetType.AUDIO_TRACK: "audio",
            AssetType.WORKFLOW_TEMPLATE: "workflows",
            AssetType.SCENE_PRESET: "workflows"
        }

        return self.storage_root / directory_map.get(asset_type, "temp")

    def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA256 hash of file"""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def _generate_thumbnail(self, image_path: Path, asset_id: str) -> str:
        """Generate thumbnail for image asset"""
        try:
            img = Image.open(image_path)

            # Create thumbnail
            thumbnail_size = (256, 256)
            img.thumbnail(thumbnail_size, Image.Resampling.LANCZOS)

            # Save thumbnail
            thumbnail_path = self.storage_root / "thumbnails" / f"{asset_id}_thumb.jpg"
            img.save(thumbnail_path, "JPEG", quality=85)

            return str(thumbnail_path)
        except Exception as e:
            logger.error(f"Failed to generate thumbnail: {e}")
            return None

    def get_asset(self, asset_id: str) -> Optional[Asset]:
        """Get asset by ID"""
        return self.assets.get(asset_id)

    def search_assets(self,
                     query: Optional[str] = None,
                     asset_type: Optional[AssetType] = None,
                     project_id: Optional[str] = None,
                     character_id: Optional[str] = None,
                     tags: List[str] = None,
                     limit: int = 50) -> List[Asset]:
        """
        Search assets with filters

        Args:
            query: Text query for semantic search
            asset_type: Filter by asset type
            project_id: Filter by project
            character_id: Filter by character
            tags: Filter by tags
            limit: Maximum results

        Returns:
            List of matching assets
        """
        results = []

        # If query provided and embeddings available, do semantic search
        if query and self.embedding_pipeline and self.qdrant_client:
            # Generate query embedding
            query_embedding = self.embedding_pipeline._generate_text_embedding(query)

            # Search in vector database
            from qdrant_client.models import SearchRequest

            # Build filter conditions
            filter_conditions = []
            if project_id:
                filter_conditions.append(
                    FieldCondition(key="project_id", match=MatchValue(value=project_id))
                )
            if character_id:
                filter_conditions.append(
                    FieldCondition(key="character_id", match=MatchValue(value=character_id))
                )

            search_filter = Filter(must=filter_conditions) if filter_conditions else None

            response = self.qdrant_client.http.points_api.search_points(
                collection_name="unified_embeddings",
                consistency=None,
                search_request=SearchRequest(
                    vector=query_embedding.tolist(),
                    limit=limit,
                    filter=search_filter,
                    with_payload=True
                )
            )

            if hasattr(response, 'result') and response.result:
                for point in response.result:
                    asset_id = point.payload.get("asset_id")
                    if asset_id and asset_id in self.assets:
                        results.append(self.assets[asset_id])

        else:
            # Filter-based search
            for asset in self.assets.values():
                # Apply filters
                if asset_type and asset.asset_type != asset_type:
                    continue
                if project_id and asset.project_id != project_id:
                    continue
                if character_id and asset.character_id != character_id:
                    continue
                if tags and not any(tag in asset.tags for tag in tags):
                    continue

                results.append(asset)

            # Limit results
            results = results[:limit]

        return results

    def create_collection(self,
                         name: str,
                         description: str,
                         asset_ids: List[str],
                         project_id: Optional[str] = None,
                         tags: List[str] = None) -> AssetCollection:
        """
        Create a collection of related assets

        Args:
            name: Collection name
            description: Collection description
            asset_ids: List of asset IDs to include
            project_id: Associated project ID
            tags: Collection tags

        Returns:
            Created AssetCollection
        """
        collection_id = str(uuid.uuid4())

        collection = AssetCollection(
            collection_id=collection_id,
            name=name,
            description=description,
            asset_ids=asset_ids,
            project_id=project_id,
            tags=tags or []
        )

        self.collections[collection_id] = collection
        self._save_asset_registry()

        logger.info(f"Created collection: {name} with {len(asset_ids)} assets")
        return collection

    def get_collection(self, collection_id: str) -> Optional[AssetCollection]:
        """Get collection by ID"""
        return self.collections.get(collection_id)

    def get_collection_assets(self, collection_id: str) -> List[Asset]:
        """Get all assets in a collection"""
        collection = self.collections.get(collection_id)
        if not collection:
            return []

        assets = []
        for asset_id in collection.asset_ids:
            if asset_id in self.assets:
                assets.append(self.assets[asset_id])

        return assets

    def update_asset_usage(self, asset_id: str):
        """Increment asset usage count"""
        if asset_id in self.assets:
            self.assets[asset_id].usage_count += 1
            self.assets[asset_id].updated_at = datetime.now()
            self._save_asset_registry()

    def get_project_assets(self, project_id: str) -> List[Asset]:
        """Get all assets for a project"""
        return [
            asset for asset in self.assets.values()
            if asset.project_id == project_id
        ]

    def get_character_assets(self, character_id: str) -> List[Asset]:
        """Get all assets for a character"""
        return [
            asset for asset in self.assets.values()
            if asset.character_id == character_id
        ]

    def delete_asset(self, asset_id: str, delete_file: bool = False) -> bool:
        """
        Delete an asset

        Args:
            asset_id: Asset ID to delete
            delete_file: Whether to delete the actual file

        Returns:
            Success status
        """
        if asset_id not in self.assets:
            return False

        asset = self.assets[asset_id]

        # Delete file if requested
        if delete_file:
            file_path = Path(asset.file_path)
            if file_path.exists():
                file_path.unlink()

            # Delete thumbnail
            if asset.thumbnail_path:
                thumb_path = Path(asset.thumbnail_path)
                if thumb_path.exists():
                    thumb_path.unlink()

        # Remove from registry
        del self.assets[asset_id]

        # Remove from collections
        for collection in self.collections.values():
            if asset_id in collection.asset_ids:
                collection.asset_ids.remove(asset_id)

        self._save_asset_registry()

        logger.info(f"Deleted asset: {asset_id}")
        return True

    def get_statistics(self) -> Dict[str, Any]:
        """Get asset management statistics"""
        stats = {
            "total_assets": len(self.assets),
            "total_collections": len(self.collections),
            "assets_by_type": {},
            "total_size": 0,
            "most_used_assets": []
        }

        # Count by type
        for asset in self.assets.values():
            asset_type = asset.asset_type.value
            if asset_type not in stats["assets_by_type"]:
                stats["assets_by_type"][asset_type] = 0
            stats["assets_by_type"][asset_type] += 1
            stats["total_size"] += asset.file_size

        # Most used assets
        sorted_assets = sorted(
            self.assets.values(),
            key=lambda a: a.usage_count,
            reverse=True
        )
        stats["most_used_assets"] = [
            {
                "name": a.name,
                "type": a.asset_type.value,
                "usage_count": a.usage_count
            }
            for a in sorted_assets[:10]
        ]

        return stats