"""Graph Router — FastAPI endpoints for Apache AGE graph queries."""

import logging

from fastapi import APIRouter, HTTPException

from . import graph_sync
from . import graph_queries

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Sync & Admin ────────────────────────────────────────────────────────


@router.post("/sync")
async def trigger_sync():
    """Trigger full graph sync from relational tables. Idempotent."""
    try:
        results = await graph_sync.full_sync()
        return {"status": "ok", "synced": results}
    except Exception as e:
        logger.error(f"Graph sync failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_graph_stats():
    """Vertex and edge counts for the anime graph."""
    try:
        stats = await graph_sync.graph_stats()
        return stats
    except Exception as e:
        logger.error(f"Graph stats failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Character Queries ───────────────────────────────────────────────────


@router.get("/character/{slug}/lineage")
async def get_character_lineage(slug: str):
    """Full generation→rejection→regeneration chain for a character."""
    results = await graph_queries.generation_lineage(slug)
    return {"character_slug": slug, "lineage": results, "count": len(results)}


@router.get("/character/{slug}/co-occurrence")
async def get_character_co_occurrence(slug: str):
    """Characters that share shots with this character."""
    # Get the character's project first
    conn = await graph_sync._get_conn()
    try:
        project_result = await graph_sync._cypher(
            conn,
            f"MATCH (c:Character {{slug: '{slug}'}})-[:BELONGS_TO]->(p:Project) RETURN p.name",
        )
        project_name = str(project_result[0]).strip('"') if project_result else None
    finally:
        await conn.close()

    results = await graph_queries.character_co_occurrence(project_name)
    return {"character_slug": slug, "project": project_name, "co_occurrences": results}


@router.get("/character/{slug}/drift")
async def get_continuity_drift(slug: str):
    """Detect appearance quality drift for a character."""
    return await graph_queries.continuity_drift(slug)


@router.get("/character/{slug}/feedback")
async def get_character_feedback(slug: str):
    """Feedback category patterns for a character."""
    results = await graph_queries.feedback_patterns(slug)
    return {"character_slug": slug, "patterns": results}


@router.get("/character/{slug}/cross-project")
async def get_cross_project_params(slug: str):
    """Find similar characters in other projects and their optimal params."""
    results = await graph_queries.cross_project_params(slug)
    return {"character_slug": slug, "similar_characters": results}


# ── Checkpoint Queries ──────────────────────────────────────────────────


@router.get("/checkpoint/ranking")
async def get_checkpoint_ranking(species: str | None = None):
    """Rank checkpoints by quality score. Optionally filter by species."""
    results = await graph_queries.checkpoint_ranking(species)
    return {"species_filter": species, "rankings": results}


# ── Project Queries ─────────────────────────────────────────────────────


@router.get("/project/{name}/health")
async def get_project_health(name: str):
    """Project health dashboard — approval rates, quality, character coverage."""
    return await graph_queries.project_health(name)


# ── Global Queries ──────────────────────────────────────────────────────


@router.get("/feedback/patterns")
async def get_global_feedback():
    """Global feedback category patterns across all characters."""
    results = await graph_queries.feedback_patterns()
    return {"patterns": results}
