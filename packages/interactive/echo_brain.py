"""Echo Brain integration for interactive sessions — preferences, memory, summaries."""

import json
import logging
import urllib.request as _ur

logger = logging.getLogger(__name__)

ECHO_BRAIN_URL = "http://localhost:8309"
_TIMEOUT = 10


def _mcp_call(tool_name: str, arguments: dict) -> dict | None:
    """Call an Echo Brain MCP tool. Returns parsed result or None on failure."""
    try:
        payload = json.dumps({
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }).encode()
        req = _ur.Request(
            f"{ECHO_BRAIN_URL}/mcp",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        resp = _ur.urlopen(req, timeout=_TIMEOUT)
        return json.loads(resp.read())
    except Exception as e:
        logger.warning("Echo Brain %s failed: %s", tool_name, e)
        return None


def _extract_text(result: dict | None) -> str:
    """Extract text content from MCP result."""
    if not result or "result" not in result:
        return ""
    content = result.get("result", {}).get("content", [])
    parts = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            parts.append(item["text"])
    return "\n".join(parts)


def search_user_preferences(project_name: str) -> str:
    """Search Echo Brain for user's play preferences for a project."""
    result = _mcp_call("search_memory", {
        "query": f"interactive play preferences for {project_name} story choices tone",
        "limit": 5,
    })
    return _extract_text(result)


def recall_session_context(project_name: str, character_names: list[str]) -> str:
    """Recall past interactive sessions and preferences."""
    chars = ", ".join(character_names) if character_names else "characters"
    result = _mcp_call("search_memory", {
        "query": f"interactive session {project_name} {chars} story decisions endings",
        "limit": 3,
    })
    return _extract_text(result)


def store_preference(preference: str, project_name: str) -> bool:
    """Store a user preference as a fact in Echo Brain."""
    result = _mcp_call("store_fact", {
        "topic": f"interactive_preferences_{project_name}",
        "fact": preference,
    })
    return result is not None and "error" not in (result.get("result", {}) or {})


def store_session_summary(
    project_name: str,
    scene_count: int,
    ending_type: str | None,
    relationships: dict[str, int],
    key_decisions: list[str],
) -> bool:
    """Store a session summary in Echo Brain."""
    rel_str = ", ".join(f"{k}: {v:+d}" for k, v in relationships.items())
    decisions_str = "; ".join(key_decisions[:5]) if key_decisions else "none"
    summary = (
        f"Interactive session for {project_name}: "
        f"{scene_count} scenes, ending={ending_type or 'incomplete'}. "
        f"Relationships: {rel_str}. "
        f"Key decisions: {decisions_str}"
    )
    result = _mcp_call("store_memory", {"content": summary})
    return result is not None


def store_decision(project_name: str, scene_number: int, decision: str) -> bool:
    """Store a notable in-game decision."""
    result = _mcp_call("store_memory", {
        "content": f"[{project_name} interactive] Scene {scene_number}: {decision}",
    })
    return result is not None
