#!/usr/bin/env python3
"""
SSOT Content Rating and Reusable Components Management API
Provides comprehensive content rating, templates, and component management
"""

from fastapi import APIRouter, HTTPException, Query
import os
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
import asyncpg
import json

router = APIRouter()

# Database connection
DATABASE_URL = "postgresql://patrick:{os.getenv(\'DATABASE_PASSWORD\')}@localhost/anime_production"

class ContentRating(BaseModel):
    project_id: int
    overall_rating: str  # G, PG, PG-13, R, NC-17, TV-MA, etc.
    violence_level: int = Field(0, ge=0, le=10)
    violence_details: Optional[Dict[str, Any]] = None
    sexual_content_level: int = Field(0, ge=0, le=10)
    sexual_content_details: Optional[Dict[str, Any]] = None
    language_level: int = Field(0, ge=0, le=10)
    language_details: Optional[Dict[str, Any]] = None
    gore_level: int = Field(0, ge=0, le=10)
    gore_details: Optional[Dict[str, Any]] = None
    substance_use_level: int = Field(0, ge=0, le=10)
    substance_details: Optional[Dict[str, Any]] = None
    frightening_content_level: int = Field(0, ge=0, le=10)
    frightening_details: Optional[Dict[str, Any]] = None
    themes: Optional[List[str]] = None
    genre_tags: Optional[List[str]] = None
    target_audience: Optional[str] = None
    content_warnings: Optional[List[str]] = None
    distribution_restrictions: Optional[Dict[str, Any]] = None
    platform_compliance: Optional[Dict[str, Any]] = None

class StyleTemplate(BaseModel):
    template_name: str
    template_type: str  # character, scene, environment, effect
    category: Optional[str] = None
    base_parameters: Dict[str, Any]
    visual_style: Optional[Dict[str, Any]] = None
    content_rating: Optional[Dict[str, Any]] = None

class ReusableComponent(BaseModel):
    component_type: str  # workflow, prompt_template, character_base, scene_template
    component_name: str
    component_data: Dict[str, Any]
    tags: Optional[List[str]] = None
    category: Optional[str] = None
    content_rating_requirements: Optional[Dict[str, Any]] = None
    dependencies: Optional[Dict[str, Any]] = None
    is_public: bool = False

async def get_db_connection():
    """Create database connection"""
    return await asyncpg.connect(DATABASE_URL)

@router.post("/content-rating/set")
async def set_content_rating(rating: ContentRating):
    """Set or update content rating for a project"""
    conn = await get_db_connection()

    try:
        # Check if rating exists
        existing = await conn.fetchrow(
            "SELECT id FROM project_content_ratings WHERE project_id = $1",
            rating.project_id
        )

        if existing:
            # Update existing rating
            await conn.execute("""
                UPDATE project_content_ratings SET
                    overall_rating = $2,
                    violence_level = $3,
                    violence_details = $4,
                    sexual_content_level = $5,
                    sexual_content_details = $6,
                    language_level = $7,
                    language_details = $8,
                    gore_level = $9,
                    gore_details = $10,
                    substance_use_level = $11,
                    substance_details = $12,
                    frightening_content_level = $13,
                    frightening_details = $14,
                    themes = $15,
                    genre_tags = $16,
                    target_audience = $17,
                    content_warnings = $18,
                    distribution_restrictions = $19,
                    platform_compliance = $20,
                    updated_at = CURRENT_TIMESTAMP
                WHERE project_id = $1
            """,
                rating.project_id,
                rating.overall_rating,
                rating.violence_level,
                json.dumps(rating.violence_details) if rating.violence_details else None,
                rating.sexual_content_level,
                json.dumps(rating.sexual_content_details) if rating.sexual_content_details else None,
                rating.language_level,
                json.dumps(rating.language_details) if rating.language_details else None,
                rating.gore_level,
                json.dumps(rating.gore_details) if rating.gore_details else None,
                rating.substance_use_level,
                json.dumps(rating.substance_details) if rating.substance_details else None,
                rating.frightening_content_level,
                json.dumps(rating.frightening_details) if rating.frightening_details else None,
                json.dumps(rating.themes) if rating.themes else None,
                rating.genre_tags,
                rating.target_audience,
                rating.content_warnings,
                json.dumps(rating.distribution_restrictions) if rating.distribution_restrictions else None,
                json.dumps(rating.platform_compliance) if rating.platform_compliance else None
            )
            message = "Content rating updated"
        else:
            # Insert new rating
            await conn.execute("""
                INSERT INTO project_content_ratings (
                    project_id, overall_rating,
                    violence_level, violence_details,
                    sexual_content_level, sexual_content_details,
                    language_level, language_details,
                    gore_level, gore_details,
                    substance_use_level, substance_details,
                    frightening_content_level, frightening_details,
                    themes, genre_tags, target_audience,
                    content_warnings, distribution_restrictions, platform_compliance
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20)
            """,
                rating.project_id,
                rating.overall_rating,
                rating.violence_level,
                json.dumps(rating.violence_details) if rating.violence_details else None,
                rating.sexual_content_level,
                json.dumps(rating.sexual_content_details) if rating.sexual_content_details else None,
                rating.language_level,
                json.dumps(rating.language_details) if rating.language_details else None,
                rating.gore_level,
                json.dumps(rating.gore_details) if rating.gore_details else None,
                rating.substance_use_level,
                json.dumps(rating.substance_details) if rating.substance_details else None,
                rating.frightening_content_level,
                json.dumps(rating.frightening_details) if rating.frightening_details else None,
                json.dumps(rating.themes) if rating.themes else None,
                rating.genre_tags,
                rating.target_audience,
                rating.content_warnings,
                json.dumps(rating.distribution_restrictions) if rating.distribution_restrictions else None,
                json.dumps(rating.platform_compliance) if rating.platform_compliance else None
            )
            message = "Content rating created"

        # Calculate age recommendation based on levels
        max_level = max(
            rating.violence_level,
            rating.sexual_content_level,
            rating.language_level,
            rating.gore_level,
            rating.substance_use_level,
            rating.frightening_content_level
        )

        age_recommendation = 0
        if max_level >= 9:
            age_recommendation = 18
        elif max_level >= 7:
            age_recommendation = 17
        elif max_level >= 5:
            age_recommendation = 13
        elif max_level >= 2:
            age_recommendation = 7

        return {
            "success": True,
            "message": message,
            "project_id": rating.project_id,
            "overall_rating": rating.overall_rating,
            "age_recommendation": age_recommendation,
            "max_content_level": max_level
        }

    finally:
        await conn.close()

@router.get("/content-rating/{project_id}")
async def get_content_rating(project_id: int):
    """Get content rating for a project"""
    conn = await get_db_connection()

    try:
        rating = await conn.fetchrow(
            """SELECT * FROM project_content_ratings WHERE project_id = $1""",
            project_id
        )

        if not rating:
            raise HTTPException(status_code=404, detail="Content rating not found for project")

        # Parse JSON fields
        result = dict(rating)
        json_fields = [
            'violence_details', 'sexual_content_details', 'language_details',
            'gore_details', 'substance_details', 'frightening_details',
            'themes', 'distribution_restrictions', 'platform_compliance'
        ]

        for field in json_fields:
            if result.get(field):
                result[field] = json.loads(result[field])

        return result

    finally:
        await conn.close()

@router.get("/content-rating/categories/list")
async def list_content_categories():
    """List all content rating categories with descriptions"""
    conn = await get_db_connection()

    try:
        categories = await conn.fetch(
            """SELECT * FROM content_rating_categories ORDER BY severity_level"""
        )

        # Group by category type
        grouped = {
            'violence': [],
            'sexual': [],
            'gore': [],
            'language': [],
            'substance': [],
            'fear': []
        }

        for cat in categories:
            cat_dict = dict(cat)
            prefix = cat['category_code'].split('_')[0]
            if prefix in grouped:
                grouped[prefix].append(cat_dict)

        return {
            "categories": grouped,
            "total_categories": len(categories)
        }

    finally:
        await conn.close()

@router.post("/style-template/create")
async def create_style_template(template: StyleTemplate):
    """Create a new reusable style template"""
    conn = await get_db_connection()

    try:
        template_id = await conn.fetchval("""
            INSERT INTO style_templates (
                template_name, template_type, category,
                base_parameters, visual_style, content_rating
            ) VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id
        """,
            template.template_name,
            template.template_type,
            template.category,
            json.dumps(template.base_parameters),
            json.dumps(template.visual_style) if template.visual_style else None,
            json.dumps(template.content_rating) if template.content_rating else None
        )

        return {
            "success": True,
            "template_id": template_id,
            "template_name": template.template_name,
            "message": "Style template created successfully"
        }

    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409, detail="Template with this name already exists")
    finally:
        await conn.close()

@router.get("/style-templates/list")
async def list_style_templates(
    template_type: Optional[str] = None,
    category: Optional[str] = None
):
    """List available style templates with optional filtering"""
    conn = await get_db_connection()

    try:
        query = "SELECT * FROM style_templates WHERE 1=1"
        params = []

        if template_type:
            params.append(template_type)
            query += f" AND template_type = ${len(params)}"

        if category:
            params.append(category)
            query += f" AND category = ${len(params)}"

        query += " ORDER BY usage_count DESC, template_name"

        templates = await conn.fetch(query, *params)

        result = []
        for template in templates:
            template_dict = dict(template)
            # Parse JSON fields
            template_dict['base_parameters'] = json.loads(template_dict['base_parameters'])
            if template_dict.get('visual_style'):
                template_dict['visual_style'] = json.loads(template_dict['visual_style'])
            if template_dict.get('content_rating'):
                template_dict['content_rating'] = json.loads(template_dict['content_rating'])
            result.append(template_dict)

        return {
            "templates": result,
            "total": len(result)
        }

    finally:
        await conn.close()

@router.post("/component/create")
async def create_reusable_component(component: ReusableComponent):
    """Create a new reusable component"""
    conn = await get_db_connection()

    try:
        component_id = await conn.fetchval("""
            INSERT INTO reusable_components (
                component_type, component_name, component_data,
                tags, category, content_rating_requirements,
                dependencies, is_public, created_by
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING id
        """,
            component.component_type,
            component.component_name,
            json.dumps(component.component_data),
            component.tags,
            component.category,
            json.dumps(component.content_rating_requirements) if component.content_rating_requirements else None,
            json.dumps(component.dependencies) if component.dependencies else None,
            component.is_public,
            "system"  # TODO: Get from auth context
        )

        return {
            "success": True,
            "component_id": component_id,
            "component_name": component.component_name,
            "message": "Reusable component created successfully"
        }

    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409, detail="Component with this name and type already exists")
    finally:
        await conn.close()

@router.get("/components/list")
async def list_reusable_components(
    component_type: Optional[str] = None,
    category: Optional[str] = None,
    tags: Optional[List[str]] = Query(None)
):
    """List available reusable components with optional filtering"""
    conn = await get_db_connection()

    try:
        query = "SELECT * FROM reusable_components WHERE 1=1"
        params = []

        if component_type:
            params.append(component_type)
            query += f" AND component_type = ${len(params)}"

        if category:
            params.append(category)
            query += f" AND category = ${len(params)}"

        if tags:
            params.append(tags)
            query += f" AND tags && ${len(params)}"  # Array overlap operator

        query += " ORDER BY created_at DESC"

        components = await conn.fetch(query, *params)

        result = []
        for comp in components:
            comp_dict = dict(comp)
            # Parse JSON fields
            comp_dict['component_data'] = json.loads(comp_dict['component_data'])
            if comp_dict.get('content_rating_requirements'):
                comp_dict['content_rating_requirements'] = json.loads(comp_dict['content_rating_requirements'])
            if comp_dict.get('dependencies'):
                comp_dict['dependencies'] = json.loads(comp_dict['dependencies'])
            if comp_dict.get('performance_metrics'):
                comp_dict['performance_metrics'] = json.loads(comp_dict['performance_metrics'])
            if comp_dict.get('usage_statistics'):
                comp_dict['usage_statistics'] = json.loads(comp_dict['usage_statistics'])
            result.append(comp_dict)

        return {
            "components": result,
            "total": len(result)
        }

    finally:
        await conn.close()

@router.put("/component/{component_id}/update")
async def update_component(component_id: int, component: ReusableComponent):
    """Update an existing reusable component"""
    conn = await get_db_connection()

    try:
        result = await conn.execute("""
            UPDATE reusable_components SET
                component_data = $2,
                tags = $3,
                category = $4,
                content_rating_requirements = $5,
                dependencies = $6,
                is_public = $7,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = $1
        """,
            component_id,
            json.dumps(component.component_data),
            component.tags,
            component.category,
            json.dumps(component.content_rating_requirements) if component.content_rating_requirements else None,
            json.dumps(component.dependencies) if component.dependencies else None,
            component.is_public
        )

        if result == "UPDATE 0":
            raise HTTPException(status_code=404, detail="Component not found")

        return {
            "success": True,
            "component_id": component_id,
            "message": "Component updated successfully"
        }

    finally:
        await conn.close()

@router.get("/component/{component_id}/usage-stats")
async def get_component_usage_stats(component_id: int):
    """Get usage statistics for a reusable component"""
    conn = await get_db_connection()

    try:
        # Get component details
        component = await conn.fetchrow(
            "SELECT * FROM reusable_components WHERE id = $1",
            component_id
        )

        if not component:
            raise HTTPException(status_code=404, detail="Component not found")

        # Get usage statistics
        usage_stats = await conn.fetchrow("""
            SELECT
                COUNT(*) as total_uses,
                COUNT(DISTINCT project_id) as projects_used,
                AVG(quality_score) as avg_quality_score,
                AVG(generation_time_seconds) as avg_generation_time,
                SUM(CASE WHEN success THEN 1 ELSE 0 END)::float / COUNT(*) * 100 as success_rate
            FROM component_usage
            WHERE component_id = $1
        """, component_id)

        # Get recent usage
        recent_usage = await conn.fetch("""
            SELECT cu.*, p.name as project_name
            FROM component_usage cu
            LEFT JOIN projects p ON cu.project_id = p.id
            WHERE cu.component_id = $1
            ORDER BY cu.usage_timestamp DESC
            LIMIT 10
        """, component_id)

        return {
            "component": {
                "id": component['id'],
                "name": component['component_name'],
                "type": component['component_type']
            },
            "statistics": dict(usage_stats) if usage_stats else {},
            "recent_usage": [dict(r) for r in recent_usage]
        }

    finally:
        await conn.close()

@router.post("/content-rating/auto-calculate/{project_id}")
async def auto_calculate_content_rating(project_id: int):
    """Automatically calculate content rating based on project content"""
    conn = await get_db_connection()

    try:
        # Get project details
        project = await conn.fetchrow(
            "SELECT * FROM projects WHERE id = $1",
            project_id
        )

        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        # Analyze project configs for content indicators
        configs = await conn.fetch(
            "SELECT config_data FROM project_configs WHERE project_id = $1",
            project_id
        )

        # Initialize content levels
        violence_level = 0
        sexual_level = 0
        language_level = 0
        gore_level = 0
        substance_level = 0
        fear_level = 0

        themes = []
        warnings = []

        # Analyze each config for content indicators
        for config in configs:
            config_data = json.loads(config['config_data'])

            # Check for violence keywords
            config_str = json.dumps(config_data).lower()

            if any(word in config_str for word in ['fight', 'battle', 'combat', 'war']):
                violence_level = max(violence_level, 5)
            if any(word in config_str for word in ['kill', 'murder', 'death', 'slaughter']):
                violence_level = max(violence_level, 7)
            if any(word in config_str for word in ['gore', 'brutal', 'visceral', 'dismember']):
                gore_level = max(gore_level, 8)

            if any(word in config_str for word in ['romance', 'kiss', 'love']):
                sexual_level = max(sexual_level, 1)
            if any(word in config_str for word in ['suggestive', 'sexy', 'seductive']):
                sexual_level = max(sexual_level, 3)
            if any(word in config_str for word in ['nudity', 'naked', 'explicit']):
                sexual_level = max(sexual_level, 6)

            if any(word in config_str for word in ['horror', 'scary', 'frightening', 'terror']):
                fear_level = max(fear_level, 6)

            # Extract themes
            if 'themes' in config_data:
                if isinstance(config_data['themes'], list):
                    themes.extend(config_data['themes'])

            # Extract content warnings
            if 'content_warnings' in config_data:
                if isinstance(config_data['content_warnings'], list):
                    warnings.extend(config_data['content_warnings'])

        # Determine overall rating based on levels
        overall_rating = "G"
        max_level = max(violence_level, sexual_level, language_level, gore_level, substance_level, fear_level)

        if max_level >= 9:
            overall_rating = "NC-17"
        elif max_level >= 7:
            overall_rating = "R"
        elif max_level >= 5:
            overall_rating = "PG-13"
        elif max_level >= 2:
            overall_rating = "PG"

        # Create or update rating
        rating = ContentRating(
            project_id=project_id,
            overall_rating=overall_rating,
            violence_level=violence_level,
            sexual_content_level=sexual_level,
            language_level=language_level,
            gore_level=gore_level,
            substance_use_level=substance_level,
            frightening_content_level=fear_level,
            themes=list(set(themes)) if themes else None,
            content_warnings=list(set(warnings)) if warnings else None,
            target_audience="Adult" if max_level >= 7 else "Teen" if max_level >= 5 else "General"
        )

        result = await set_content_rating(rating)

        return {
            "success": True,
            "message": "Content rating auto-calculated",
            "project_id": project_id,
            "overall_rating": overall_rating,
            "levels": {
                "violence": violence_level,
                "sexual": sexual_level,
                "language": language_level,
                "gore": gore_level,
                "substance": substance_level,
                "frightening": fear_level
            },
            "themes": themes,
            "warnings": warnings
        }

    finally:
        await conn.close()

@router.get("/templates/compatibility-check")
async def check_template_compatibility(
    project_id: int,
    template_id: int
):
    """Check if a template is compatible with project's content rating"""
    conn = await get_db_connection()

    try:
        # Get project rating
        project_rating = await conn.fetchrow(
            "SELECT * FROM project_content_ratings WHERE project_id = $1",
            project_id
        )

        if not project_rating:
            return {
                "compatible": True,
                "message": "No content rating set for project, all templates allowed"
            }

        # Get template
        template = await conn.fetchrow(
            "SELECT * FROM style_templates WHERE id = $1",
            template_id
        )

        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

        # Check compatibility
        if template['content_rating']:
            template_rating = json.loads(template['content_rating'])

            issues = []

            if 'max_violence' in template_rating:
                if project_rating['violence_level'] > template_rating['max_violence']:
                    issues.append(f"Project violence level ({project_rating['violence_level']}) exceeds template maximum ({template_rating['max_violence']})")

            if 'max_sexual' in template_rating:
                if project_rating['sexual_content_level'] > template_rating['max_sexual']:
                    issues.append(f"Project sexual content level ({project_rating['sexual_content_level']}) exceeds template maximum ({template_rating['max_sexual']})")

            if issues:
                return {
                    "compatible": False,
                    "issues": issues,
                    "message": "Template not compatible with project content rating"
                }

        return {
            "compatible": True,
            "message": "Template compatible with project content rating"
        }

    finally:
        await conn.close()