"""Graph Queries — Cypher query helpers for anime production graph analytics.

All functions return Python dicts/lists ready for JSON serialization.
Uses the same AGE connection pattern as graph_sync.
"""

import json
import logging

import asyncpg

from .config import DB_CONFIG

logger = logging.getLogger(__name__)

GRAPH_NAME = "anime_graph"


async def _get_conn() -> asyncpg.Connection:
    conn = await asyncpg.connect(
        host=DB_CONFIG["host"],
        database=DB_CONFIG["database"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
        statement_cache_size=0,
    )
    await conn.execute('SET search_path = ag_catalog, "$user", public')
    return conn


def _parse_agtype(val) -> any:
    """Parse an agtype value to a Python native type."""
    if val is None:
        return None
    s = str(val)
    # Strip ::vertex, ::edge suffixes
    for suffix in ("::vertex", "::edge", "::path"):
        if s.endswith(suffix):
            s = s[: -len(suffix)]
    # Try JSON parse for objects/arrays
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        # Try numeric
        try:
            if "." in s:
                return float(s)
            return int(s)
        except (ValueError, TypeError):
            return s


async def _cypher_multi(conn: asyncpg.Connection, query: str, columns: list[str]) -> list[dict]:
    """Execute Cypher returning multiple columns."""
    col_def = ", ".join(f"{c} agtype" for c in columns)
    sql = f"SELECT * FROM cypher('{GRAPH_NAME}', $cypher${query}$cypher$) AS ({col_def})"
    rows = await conn.fetch(sql)
    results = []
    for row in rows:
        results.append({c: _parse_agtype(row[c]) for c in columns})
    return results


async def _cypher_single(conn: asyncpg.Connection, query: str) -> list:
    """Execute Cypher returning a single column."""
    sql = f"SELECT * FROM cypher('{GRAPH_NAME}', $cypher${query}$cypher$) AS (result agtype)"
    rows = await conn.fetch(sql)
    return [_parse_agtype(row["result"]) for row in rows]


# ── Core Query Functions ────────────────────────────────────────────────


async def checkpoint_ranking(species: str | None = None) -> list[dict]:
    """Best checkpoints ranked by average quality score of approved images.

    Optionally filter by character species (e.g., 'goblin', 'human').
    """
    conn = await _get_conn()
    try:
        if species:
            species_lower = species.lower()
            query = f"""
                MATCH (c:Character)-[:DEPICTS]-(i:Image)-[:GENERATED_WITH]->(ck:Checkpoint)
                WHERE i.status = 'approved' AND c.species CONTAINS '{species_lower}'
                RETURN ck.checkpoint_model, avg(i.quality_score), count(i)
            """
        else:
            query = """
                MATCH (i:Image)-[:GENERATED_WITH]->(ck:Checkpoint)
                WHERE i.status = 'approved'
                RETURN ck.checkpoint_model, avg(i.quality_score), count(i)
            """

        results = await _cypher_multi(conn, query, ["checkpoint", "avg_quality", "count"])
        # Sort by avg_quality descending
        results.sort(key=lambda x: float(x.get("avg_quality") or 0), reverse=True)
        return results
    except Exception as e:
        logger.error(f"checkpoint_ranking failed: {e}")
        return []
    finally:
        await conn.close()


async def character_co_occurrence(project_name: str | None = None) -> list[dict]:
    """Characters that appear together in shared shots."""
    conn = await _get_conn()
    try:
        if project_name:
            query = f"""
                MATCH (c1:Character)-[:APPEARS_IN]->(sh:Shot)<-[:APPEARS_IN]-(c2:Character)
                WHERE c1.slug < c2.slug
                MATCH (c1)-[:BELONGS_TO]->(p:Project {{name: '{project_name.replace("'", "''")}'}} )
                RETURN c1.name, c2.name, count(sh)
            """
        else:
            query = """
                MATCH (c1:Character)-[:APPEARS_IN]->(sh:Shot)<-[:APPEARS_IN]-(c2:Character)
                WHERE c1.slug < c2.slug
                RETURN c1.name, c2.name, count(sh)
            """

        results = await _cypher_multi(conn, query, ["char1", "char2", "shared_shots"])
        results.sort(key=lambda x: int(x.get("shared_shots") or 0), reverse=True)
        return results
    except Exception as e:
        logger.error(f"character_co_occurrence failed: {e}")
        return []
    finally:
        await conn.close()


async def generation_lineage(character_slug: str) -> list[dict]:
    """Full generation→rejection→regeneration chain for a character."""
    conn = await _get_conn()
    try:
        # Get all images for this character with their regeneration links
        query = f"""
            MATCH (c:Character {{slug: '{character_slug}'}})<-[:DEPICTS]-(i:Image)
            OPTIONAL MATCH (i)-[:REGENERATED_FROM]->(parent:Image)
            RETURN i.img_id, i.status, i.quality_score, i.generated_at, parent.img_id
        """
        results = await _cypher_multi(
            conn, query, ["img_id", "status", "quality_score", "generated_at", "parent_id"]
        )
        return results
    except Exception as e:
        logger.error(f"generation_lineage failed: {e}")
        return []
    finally:
        await conn.close()


async def cross_project_params(character_slug: str) -> list[dict]:
    """Find characters with similar species in other projects and their best checkpoint params."""
    conn = await _get_conn()
    try:
        # First get the character's species
        species_result = await _cypher_single(
            conn, f"MATCH (c:Character {{slug: '{character_slug}'}}) RETURN c.species"
        )
        if not species_result or not species_result[0]:
            return []

        species = str(species_result[0]).strip("'\"")
        if not species:
            return []

        # Find similar characters in other projects with high-quality approved images
        query = f"""
            MATCH (c:Character {{slug: '{character_slug}'}})-[:BELONGS_TO]->(p:Project)
            WITH p.name as my_project
            MATCH (c2:Character)-[:BELONGS_TO]->(p2:Project)
            WHERE c2.species CONTAINS '{species.split()[0].lower()}'
              AND p2.name <> my_project
            MATCH (c2)<-[:DEPICTS]-(i:Image {{status: 'approved'}})-[:GENERATED_WITH]->(ck:Checkpoint)
            RETURN c2.name, p2.name, ck.checkpoint_model, avg(i.quality_score), count(i)
        """
        results = await _cypher_multi(
            conn, query, ["character", "project", "checkpoint", "avg_quality", "count"]
        )
        results.sort(key=lambda x: float(x.get("avg_quality") or 0), reverse=True)
        return results
    except Exception as e:
        logger.error(f"cross_project_params failed: {e}")
        return []
    finally:
        await conn.close()


async def continuity_drift(character_slug: str) -> dict:
    """Detect appearance drift — compare earliest vs most recent approved image quality."""
    conn = await _get_conn()
    try:
        query = f"""
            MATCH (c:Character {{slug: '{character_slug}'}})<-[:DEPICTS]-(i:Image {{status: 'approved'}})
            RETURN i.quality_score, i.generated_at
        """
        results = await _cypher_multi(conn, query, ["quality_score", "generated_at"])

        if len(results) < 2:
            return {
                "character_slug": character_slug,
                "drift_detected": False,
                "reason": "insufficient_data",
                "total_approved": len(results),
            }

        # Sort by generated_at
        results.sort(key=lambda x: str(x.get("generated_at") or ""))

        # Compare first 5 vs last 5
        earliest = [float(r["quality_score"]) for r in results[:5] if r["quality_score"] is not None]
        recent = [float(r["quality_score"]) for r in results[-5:] if r["quality_score"] is not None]

        if not earliest or not recent:
            return {
                "character_slug": character_slug,
                "drift_detected": False,
                "reason": "no_quality_scores",
            }

        avg_earliest = sum(earliest) / len(earliest)
        avg_recent = sum(recent) / len(recent)
        drift = avg_recent - avg_earliest

        return {
            "character_slug": character_slug,
            "drift_detected": abs(drift) > 0.1,
            "direction": "improving" if drift > 0.05 else "declining" if drift < -0.05 else "stable",
            "avg_earliest": round(avg_earliest, 3),
            "avg_recent": round(avg_recent, 3),
            "drift_amount": round(drift, 3),
            "total_approved": len(results),
        }
    except Exception as e:
        logger.error(f"continuity_drift failed: {e}")
        return {"character_slug": character_slug, "error": str(e)}
    finally:
        await conn.close()


async def project_health(project_name: str) -> dict:
    """Overall project health — approval rates, quality trends, character coverage."""
    conn = await _get_conn()
    try:
        # Character stats
        char_query = f"""
            MATCH (c:Character)-[:BELONGS_TO]->(p:Project {{name: '{project_name.replace("'", "''")}'}} )
            OPTIONAL MATCH (c)<-[:DEPICTS]-(i:Image)
            RETURN c.name, c.slug,
                   count(i),
                   sum(CASE WHEN i.status = 'approved' THEN 1 ELSE 0 END),
                   sum(CASE WHEN i.status = 'rejected' THEN 1 ELSE 0 END)
        """
        chars = await _cypher_multi(
            conn, char_query, ["name", "slug", "total", "approved", "rejected"]
        )

        # Scene stats
        scene_query = f"""
            MATCH (c:Character)-[:BELONGS_TO]->(p:Project {{name: '{project_name.replace("'", "''")}'}} )
            WITH p
            MATCH (s:Scene)-[:SCENE_IN]->(ep:Episode)
            RETURN count(DISTINCT s), count(DISTINCT ep)
        """
        try:
            scene_stats = await _cypher_multi(conn, scene_query, ["scenes", "episodes"])
        except Exception:
            scene_stats = [{"scenes": 0, "episodes": 0}]

        # Checkpoint usage
        ck_query = f"""
            MATCH (p:Project {{name: '{project_name.replace("'", "''")}'}} )-[:USES_CHECKPOINT]->(ck:Checkpoint)
            RETURN ck.checkpoint_model, ck.cfg, ck.steps
        """
        try:
            checkpoints = await _cypher_multi(conn, ck_query, ["model", "cfg", "steps"])
        except Exception:
            checkpoints = []

        total_images = sum(int(c.get("total") or 0) for c in chars)
        total_approved = sum(int(c.get("approved") or 0) for c in chars)
        approval_rate = round(total_approved / total_images, 3) if total_images > 0 else 0

        empty_chars = [c for c in chars if int(c.get("total") or 0) == 0]

        return {
            "project_name": project_name,
            "characters": chars,
            "total_characters": len(chars),
            "total_images": total_images,
            "total_approved": total_approved,
            "approval_rate": approval_rate,
            "empty_characters": [c["name"] for c in empty_chars],
            "scenes": scene_stats[0] if scene_stats else {},
            "checkpoints": checkpoints,
        }
    except Exception as e:
        logger.error(f"project_health failed: {e}")
        return {"project_name": project_name, "error": str(e)}
    finally:
        await conn.close()


async def feedback_patterns(character_slug: str | None = None) -> list[dict]:
    """Most common feedback categories, optionally filtered by character."""
    conn = await _get_conn()
    try:
        if character_slug:
            query = f"""
                MATCH (fc:FeedbackCategory)-[:FEEDBACK_FOR]->(i:Image)-[:DEPICTS]->(c:Character {{slug: '{character_slug}'}})
                RETURN fc.category, count(i)
            """
        else:
            query = """
                MATCH (fc:FeedbackCategory)-[:FEEDBACK_FOR]->(i:Image)
                RETURN fc.category, count(i)
            """

        results = await _cypher_multi(conn, query, ["category", "count"])
        results.sort(key=lambda x: int(x.get("count") or 0), reverse=True)
        return results
    except Exception as e:
        logger.error(f"feedback_patterns failed: {e}")
        return []
    finally:
        await conn.close()
