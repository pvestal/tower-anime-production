"""
Database Manager
Professional database management for scene description service
"""

import asyncio
import asyncpg
import logging
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
import json
import os

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Professional database manager for scene descriptions"""

    def __init__(self):
        self.pool = None
        self.connection_config = self._get_connection_config()

    def _get_connection_config(self) -> Dict[str, Any]:
        """Get database connection configuration"""
        return {
            "host": os.getenv("DB_HOST", "192.168.50.135"),
            "port": int(os.getenv("DB_PORT", "5432")),
            "user": os.getenv("DB_USER", "patrick"),
            "password": os.getenv("DB_PASSWORD", "tower_echo_brain_secret_key_2025"),
            "database": os.getenv("DB_NAME", "scene_description"),
            "min_size": 5,
            "max_size": 20,
            "command_timeout": 60
        }

    async def initialize(self):
        """Initialize database connection pool"""
        try:
            self.pool = await asyncpg.create_pool(**self.connection_config)
            logger.info("Database connection pool initialized successfully")

            # Test connection
            async with self.pool.acquire() as conn:
                await conn.execute("SELECT 1")
                logger.info("Database connectivity verified")

        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            raise

    async def close(self):
        """Close database connection pool"""
        if self.pool:
            await self.pool.close()
            logger.info("Database connection pool closed")

    async def execute(self, query: str, *args) -> str:
        """Execute a query and return result status"""
        async with self.pool.acquire() as conn:
            result = await conn.execute(query, *args)
            return result

    async def fetchrow(self, query: str, *args) -> Optional[asyncpg.Record]:
        """Fetch a single row"""
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def fetch(self, query: str, *args) -> List[asyncpg.Record]:
        """Fetch multiple rows"""
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchval(self, query: str, *args) -> Any:
        """Fetch a single value"""
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, *args)

    # Scene-specific database operations
    async def create_scene(self, scene_data: Dict[str, Any]) -> int:
        """Create a new scene in the database"""
        try:
            scene_id = await self.fetchval("""
                INSERT INTO scenes (
                    script_id, scene_number, title, location, time_of_day,
                    characters, action_summary, mood, visual_description,
                    cinematography_notes, atmosphere_description, timing_notes,
                    technical_specifications, revenue_potential, created_by
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
                RETURNING id
            """,
                scene_data["script_id"],
                scene_data["scene_number"],
                scene_data["title"],
                scene_data["location"],
                scene_data["time_of_day"],
                json.dumps(scene_data["characters"]),
                scene_data["action_summary"],
                scene_data["mood"],
                scene_data["visual_description"],
                scene_data["cinematography_notes"],
                scene_data["atmosphere_description"],
                scene_data["timing_notes"],
                json.dumps(scene_data["technical_specifications"]),
                scene_data.get("revenue_potential", 0.00),
                scene_data.get("created_by", "autonomous")
            )

            logger.info(f"Scene created with ID: {scene_id}")
            return scene_id

        except Exception as e:
            logger.error(f"Scene creation failed: {e}")
            raise

    async def get_scene(self, scene_id: int) -> Optional[Dict[str, Any]]:
        """Get scene by ID"""
        try:
            scene_record = await self.fetchrow("""
                SELECT * FROM scenes WHERE id = $1
            """, scene_id)

            if scene_record:
                scene_dict = dict(scene_record)
                # Parse JSON fields
                if scene_dict.get("characters"):
                    scene_dict["characters"] = json.loads(scene_dict["characters"])
                if scene_dict.get("technical_specifications"):
                    scene_dict["technical_specifications"] = json.loads(scene_dict["technical_specifications"])
                return scene_dict
            return None

        except Exception as e:
            logger.error(f"Scene retrieval failed: {e}")
            raise

    async def update_scene(self, scene_id: int, updates: Dict[str, Any]) -> bool:
        """Update scene with provided fields"""
        try:
            # Build dynamic update query
            set_clauses = []
            values = []
            param_counter = 1

            for field, value in updates.items():
                if field in ["characters", "technical_specifications"] and isinstance(value, (dict, list)):
                    value = json.dumps(value)

                set_clauses.append(f"{field} = ${param_counter}")
                values.append(value)
                param_counter += 1

            # Add updated_at
            set_clauses.append(f"updated_at = ${param_counter}")
            values.append(datetime.utcnow())
            param_counter += 1

            # Add scene_id for WHERE clause
            values.append(scene_id)

            query = f"""
                UPDATE scenes
                SET {', '.join(set_clauses)}
                WHERE id = ${param_counter}
            """

            result = await self.execute(query, *values)
            success = "UPDATE 1" in result

            if success:
                logger.info(f"Scene {scene_id} updated successfully")
            return success

        except Exception as e:
            logger.error(f"Scene update failed: {e}")
            raise

    async def delete_scene(self, scene_id: int) -> bool:
        """Delete scene and related data"""
        try:
            result = await self.execute("""
                DELETE FROM scenes WHERE id = $1
            """, scene_id)

            success = "DELETE 1" in result
            if success:
                logger.info(f"Scene {scene_id} deleted successfully")
            return success

        except Exception as e:
            logger.error(f"Scene deletion failed: {e}")
            raise

    async def get_script_scenes(
        self,
        script_id: int,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get all scenes for a script"""
        try:
            scene_records = await self.fetch("""
                SELECT * FROM scenes
                WHERE script_id = $1
                ORDER BY scene_number ASC
                LIMIT $2 OFFSET $3
            """, script_id, limit, offset)

            scenes = []
            for record in scene_records:
                scene_dict = dict(record)
                # Parse JSON fields
                if scene_dict.get("characters"):
                    scene_dict["characters"] = json.loads(scene_dict["characters"])
                if scene_dict.get("technical_specifications"):
                    scene_dict["technical_specifications"] = json.loads(scene_dict["technical_specifications"])
                scenes.append(scene_dict)

            return scenes

        except Exception as e:
            logger.error(f"Script scenes retrieval failed: {e}")
            raise

    # Character management
    async def add_scene_character(
        self,
        scene_id: int,
        character_data: Dict[str, Any]
    ) -> int:
        """Add character to scene"""
        try:
            character_id = await self.fetchval("""
                INSERT INTO scene_characters (
                    scene_id, character_name, character_role, emotional_state,
                    physical_description, costume_notes, positioning, interaction_level
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING id
            """,
                scene_id,
                character_data["character_name"],
                character_data["character_role"],
                character_data.get("emotional_state"),
                character_data.get("physical_description"),
                character_data.get("costume_notes"),
                character_data.get("positioning"),
                character_data.get("interaction_level", "secondary")
            )

            logger.info(f"Scene character added with ID: {character_id}")
            return character_id

        except Exception as e:
            logger.error(f"Scene character addition failed: {e}")
            raise

    async def get_scene_characters(self, scene_id: int) -> List[Dict[str, Any]]:
        """Get all characters for a scene"""
        try:
            character_records = await self.fetch("""
                SELECT * FROM scene_characters WHERE scene_id = $1
                ORDER BY interaction_level DESC, character_name ASC
            """, scene_id)

            return [dict(record) for record in character_records]

        except Exception as e:
            logger.error(f"Scene characters retrieval failed: {e}")
            raise

    # Quality and analytics
    async def save_quality_metrics(
        self,
        scene_id: int,
        metrics: Dict[str, float]
    ) -> int:
        """Save quality metrics for scene"""
        try:
            metrics_id = await self.fetchval("""
                INSERT INTO quality_metrics (
                    scene_id, visual_clarity, narrative_coherence,
                    character_consistency, production_feasibility,
                    market_appeal, overall_score, assessed_by
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING id
            """,
                scene_id,
                metrics["visual_clarity"],
                metrics["narrative_coherence"],
                metrics["character_consistency"],
                metrics["production_feasibility"],
                metrics["market_appeal"],
                metrics["overall_score"],
                metrics.get("assessed_by", "autonomous")
            )

            logger.info(f"Quality metrics saved with ID: {metrics_id}")
            return metrics_id

        except Exception as e:
            logger.error(f"Quality metrics save failed: {e}")
            raise

    async def save_revenue_metrics(
        self,
        scene_id: int,
        metrics: Dict[str, Any]
    ) -> int:
        """Save revenue metrics for scene"""
        try:
            metrics_id = await self.fetchval("""
                INSERT INTO revenue_metrics (
                    scene_id, estimated_view_count, monetization_potential,
                    merchandise_opportunity, licensing_value,
                    audience_retention_score, viral_potential
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING id
            """,
                scene_id,
                metrics.get("estimated_view_count", 0),
                metrics.get("monetization_potential", 0.00),
                metrics.get("merchandise_opportunity", 0.00),
                metrics.get("licensing_value", 0.00),
                metrics.get("audience_retention_score", 0.00),
                metrics.get("viral_potential", 0.00)
            )

            logger.info(f"Revenue metrics saved with ID: {metrics_id}")
            return metrics_id

        except Exception as e:
            logger.error(f"Revenue metrics save failed: {e}")
            raise

    # Analytics queries
    async def get_scene_analytics(
        self,
        days_back: int = 30
    ) -> Dict[str, Any]:
        """Get scene generation analytics"""
        try:
            analytics = await self.fetchrow("""
                SELECT
                    COUNT(*) as total_scenes,
                    AVG(revenue_potential) as avg_revenue_potential,
                    COUNT(DISTINCT script_id) as unique_scripts,
                    COUNT(CASE WHEN status = 'approved' THEN 1 END) as approved_scenes,
                    MIN(created_at) as earliest_scene,
                    MAX(created_at) as latest_scene
                FROM scenes
                WHERE created_at >= NOW() - INTERVAL '%s days'
            """ % days_back)

            # Get quality metrics
            quality_analytics = await self.fetchrow("""
                SELECT
                    AVG(overall_score) as avg_quality_score,
                    AVG(visual_clarity) as avg_visual_clarity,
                    AVG(production_feasibility) as avg_production_feasibility
                FROM quality_metrics qm
                JOIN scenes s ON qm.scene_id = s.id
                WHERE s.created_at >= NOW() - INTERVAL '%s days'
            """ % days_back)

            return {
                "period_days": days_back,
                "scene_metrics": dict(analytics) if analytics else {},
                "quality_metrics": dict(quality_analytics) if quality_analytics else {},
                "generated_at": datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"Analytics retrieval failed: {e}")
            raise

    # Integration tracking
    async def log_echo_collaboration(
        self,
        scene_id: int,
        collaboration_data: Dict[str, Any]
    ) -> int:
        """Log Echo Brain collaboration"""
        try:
            collaboration_id = await self.fetchval("""
                INSERT INTO echo_collaborations (
                    scene_id, collaboration_type, prompt, context,
                    response, creative_parameters, success, response_time_ms
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING id
            """,
                scene_id,
                collaboration_data["collaboration_type"],
                collaboration_data["prompt"],
                json.dumps(collaboration_data.get("context", {})),
                collaboration_data.get("response", ""),
                json.dumps(collaboration_data.get("creative_parameters", {})),
                collaboration_data.get("success", True),
                collaboration_data.get("response_time_ms", 0)
            )

            logger.info(f"Echo collaboration logged with ID: {collaboration_id}")
            return collaboration_id

        except Exception as e:
            logger.error(f"Echo collaboration logging failed: {e}")
            raise

    async def log_autonomous_operation(
        self,
        operation_type: str,
        target_id: Optional[int] = None,
        operation_details: Optional[Dict[str, Any]] = None,
        success: bool = True,
        execution_time_ms: int = 0,
        error_message: Optional[str] = None
    ) -> int:
        """Log autonomous operation"""
        try:
            operation_id = await self.fetchval("""
                INSERT INTO autonomous_operations (
                    operation_type, target_id, operation_details,
                    success, execution_time_ms, error_message
                ) VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id
            """,
                operation_type,
                target_id,
                json.dumps(operation_details or {}),
                success,
                execution_time_ms,
                error_message
            )

            logger.info(f"Autonomous operation logged with ID: {operation_id}")
            return operation_id

        except Exception as e:
            logger.error(f"Autonomous operation logging failed: {e}")
            raise

    # Database maintenance
    async def cleanup_old_data(self, days_to_keep: int = 90) -> Dict[str, int]:
        """Clean up old data beyond retention period"""
        try:
            # Clean up old autonomous operations
            operations_deleted = await self.fetchval("""
                DELETE FROM autonomous_operations
                WHERE created_at < NOW() - INTERVAL '%s days'
                RETURNING COUNT(*)
            """ % days_to_keep)

            # Clean up old echo collaborations
            collaborations_deleted = await self.fetchval("""
                DELETE FROM echo_collaborations
                WHERE created_at < NOW() - INTERVAL '%s days'
                RETURNING COUNT(*)
            """ % days_to_keep)

            cleanup_results = {
                "operations_deleted": operations_deleted or 0,
                "collaborations_deleted": collaborations_deleted or 0
            }

            logger.info(f"Data cleanup completed: {cleanup_results}")
            return cleanup_results

        except Exception as e:
            logger.error(f"Data cleanup failed: {e}")
            raise

    async def get_database_stats(self) -> Dict[str, Any]:
        """Get database statistics"""
        try:
            stats = {}

            # Table sizes
            for table in ["scenes", "scene_characters", "quality_metrics", "revenue_metrics", "echo_collaborations"]:
                count = await self.fetchval(f"SELECT COUNT(*) FROM {table}")
                stats[f"{table}_count"] = count

            # Recent activity
            recent_scenes = await self.fetchval("""
                SELECT COUNT(*) FROM scenes WHERE created_at >= NOW() - INTERVAL '24 hours'
            """)
            stats["scenes_last_24h"] = recent_scenes

            return stats

        except Exception as e:
            logger.error(f"Database stats retrieval failed: {e}")
            raise