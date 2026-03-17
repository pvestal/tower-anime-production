"""Character name/slug/path/LoRA audit — catches mismatches before generation.

Validates the entire character resolution chain:
  name → slug → dataset dir → images → approval_status → LoRA files
  → shots.characters_present → source_image_path → content_lora_high/low

Usage:
  # As endpoint:  POST /api/scenes/character-audit
  # Standalone:   python -m packages.scene_generation.character_audit
"""

import json
import logging
import re
from pathlib import Path

import asyncpg

from packages.core.config import BASE_PATH
from packages.core.db import connect_direct

logger = logging.getLogger(__name__)

LORA_DIR = Path("/opt/ComfyUI/models/loras")
COMFYUI_INPUT = Path("/opt/ComfyUI/input")


def _name_to_slug(name: str) -> str:
    """Canonical slug derivation — must match scene_crud._name_to_slug."""
    return re.sub(r'[^a-z0-9_-]', '', name.lower().replace(' ', '_'))


# ── Individual checks ────────────────────────────────────────────────


def _check_slug_derivation(char: dict) -> list[dict]:
    """Verify derived slug maps to a dataset directory."""
    issues = []
    name = char["name"]
    slug = _name_to_slug(name)
    if not slug:
        issues.append({
            "check": "slug_derivation",
            "severity": "error",
            "detail": f"Character '{name}' (id={char['id']}) derives to empty slug",
        })
    return issues


# Roles that don't require their own dataset, LoRA, or training images.
# Background = crowd/group/extras, victim = one-off scene characters.
ROLES_NO_TRAINING = {"background", "victim"}


def _check_dataset_dir(slug: str, *, role: str | None = None) -> list[dict]:
    """Verify datasets/{slug}/ exists with images/ and approval_status.json.

    Characters with roles in ROLES_NO_TRAINING skip this check entirely.
    """
    if role and role.lower() in ROLES_NO_TRAINING:
        return []

    issues = []
    ds_dir = BASE_PATH / slug
    if not ds_dir.is_dir():
        issues.append({
            "check": "dataset_dir",
            "severity": "error",
            "detail": f"Dataset directory missing: {ds_dir}",
        })
        return issues  # No point checking children

    img_dir = ds_dir / "images"
    if not img_dir.is_dir():
        issues.append({
            "check": "dataset_images",
            "severity": "warning",
            "detail": f"images/ subdirectory missing: {img_dir}",
        })
    elif not any(img_dir.iterdir()):
        issues.append({
            "check": "dataset_images",
            "severity": "warning",
            "detail": f"images/ directory is empty: {img_dir}",
        })

    approval = ds_dir / "approval_status.json"
    if not approval.exists():
        issues.append({
            "check": "approval_status",
            "severity": "info",
            "detail": f"approval_status.json missing: {approval}",
        })
    else:
        try:
            with open(approval) as f:
                data = json.load(f)
            approved = sum(1 for v in data.values()
                          if v == "approved" or (isinstance(v, dict) and v.get("status") == "approved"))
            if approved == 0:
                issues.append({
                    "check": "approval_status",
                    "severity": "warning",
                    "detail": f"0 approved images in {approval} ({len(data)} total)",
                })
        except Exception as e:
            issues.append({
                "check": "approval_status",
                "severity": "error",
                "detail": f"Cannot parse {approval}: {e}",
            })

    return issues


def _check_lora_file(char: dict, slug: str) -> list[dict]:
    """Verify character LoRA exists on disk.

    Characters with roles in ROLES_NO_TRAINING only get checked if they have
    an explicit lora_path set (shouldn't happen, but catch misconfiguration).
    """
    role = (char.get("role") or "").lower()
    issues = []
    lora_path = char.get("lora_path") or ""

    # Background/victim chars without explicit lora_path → nothing to check
    if not lora_path and role in ROLES_NO_TRAINING:
        return issues

    if lora_path:
        # Check the explicit path
        full = LORA_DIR / lora_path
        if not full.exists():
            issues.append({
                "check": "lora_file",
                "severity": "error",
                "detail": f"characters.lora_path '{lora_path}' not found at {full}",
            })
    else:
        # No explicit path — check conventional names
        conventions = [
            f"{slug}_ill_lora.safetensors",
            f"{slug}_lora.safetensors",
            f"{slug}_wan22_lora.safetensors",
        ]
        found = [c for c in conventions if (LORA_DIR / c).exists()]
        if not found:
            issues.append({
                "check": "lora_file",
                "severity": "info",
                "detail": f"No LoRA file found for '{slug}' (checked: {', '.join(conventions)})",
            })

    return issues


def _check_lora_path_convention(char: dict, slug: str) -> list[dict]:
    """Flag mismatches between lora_path and expected naming conventions."""
    issues = []
    lora_path = char.get("lora_path") or ""
    if not lora_path:
        return issues

    # Check slug is part of the filename
    lora_name = Path(lora_path).stem.lower()
    if slug not in lora_name:
        issues.append({
            "check": "lora_convention",
            "severity": "warning",
            "detail": f"LoRA filename '{lora_path}' doesn't contain slug '{slug}'",
        })

    return issues


async def _check_shots_characters_present(conn, slug: str, char_id: int) -> list[dict]:
    """Check shots referencing this character via characters_present."""
    issues = []

    # Find shots where the slug appears in characters_present
    rows = await conn.fetch(
        """SELECT s.id, s.characters_present, s.source_image_path,
                  s.image_lora, s.content_lora_high, s.content_lora_low,
                  s.lora_name, sc.project_id
           FROM shots s
           JOIN scenes sc ON sc.id = s.scene_id
           WHERE $1 = ANY(s.characters_present)""",
        slug,
    )

    for row in rows:
        shot_id = row["id"]

        # Check source_image_path exists
        src = row["source_image_path"]
        if src:
            src_path = Path(src)
            if not src_path.is_absolute():
                src_path = BASE_PATH / src
            if not src_path.exists():
                # Also check ComfyUI input
                comfy_path = COMFYUI_INPUT / Path(src).name
                if not comfy_path.exists():
                    issues.append({
                        "check": "source_image",
                        "severity": "error",
                        "detail": f"Shot {shot_id}: source_image_path '{src}' not found on disk",
                    })

        # Check image_lora matches character lora_path
        image_lora = row["image_lora"]
        if image_lora:
            lora_full = LORA_DIR / image_lora
            if not lora_full.exists():
                issues.append({
                    "check": "shot_image_lora",
                    "severity": "error",
                    "detail": f"Shot {shot_id}: image_lora '{image_lora}' not found at {lora_full}",
                })

        # Check content_lora_high/low exist on disk
        for field in ("content_lora_high", "content_lora_low"):
            val = row[field]
            if val:
                lora_full = LORA_DIR / val
                if not lora_full.exists():
                    issues.append({
                        "check": f"shot_{field}",
                        "severity": "error",
                        "detail": f"Shot {shot_id}: {field} '{val}' not found at {lora_full}",
                    })

    return issues


async def _check_slug_case_mismatches(conn) -> list[dict]:
    """Find characters_present entries that don't match any known slug."""
    issues = []

    # Get all known slugs (derived from name — no slug column in DB)
    char_rows = await conn.fetch("SELECT name FROM characters")
    known_slugs = {_name_to_slug(r["name"]) for r in char_rows}

    # Get all distinct values from characters_present across all shots
    rows = await conn.fetch(
        """SELECT DISTINCT unnest(characters_present) AS slug_used
           FROM shots
           WHERE characters_present IS NOT NULL"""
    )

    for row in rows:
        used = row["slug_used"]
        if used not in known_slugs:
            # Check if it's a case mismatch
            lower_match = [s for s in known_slugs if s.lower() == used.lower()]
            if lower_match:
                issues.append({
                    "check": "slug_case_mismatch",
                    "severity": "error",
                    "detail": f"characters_present uses '{used}' but DB slug is '{lower_match[0]}' — case mismatch will break LoRA loading",
                })
            else:
                issues.append({
                    "check": "slug_unknown",
                    "severity": "warning",
                    "detail": f"characters_present references '{used}' which is not a known character slug",
                })

    return issues


async def _check_phantom_loras(conn) -> list[dict]:
    """Find shots with lora_name values that are bare keywords (not file paths)."""
    issues = []

    rows = await conn.fetch(
        """SELECT id, lora_name FROM shots
           WHERE lora_name IS NOT NULL
             AND lora_name != ''
             AND lora_name NOT LIKE '%/%'
             AND lora_name NOT LIKE '%.safetensors'"""
    )

    for row in rows:
        lora_name = row["lora_name"]
        # Check if it's a valid catalog key
        try:
            from .catalog_loader import load_catalog
            catalog = load_catalog()
            pairs = catalog.get("video_lora_pairs", {}) if catalog else {}
            presets = catalog.get("action_presets", {}) if catalog else {}
            motion = catalog.get("video_motion_loras", {}) if catalog else {}
            if lora_name not in pairs and lora_name not in presets and lora_name not in motion:
                issues.append({
                    "check": "phantom_lora",
                    "severity": "warning",
                    "detail": f"Shot {row['id']}: lora_name '{lora_name}' is neither a file path nor a catalog key",
                })
        except Exception:
            # Can't load catalog — just flag bare keywords
            issues.append({
                "check": "phantom_lora",
                "severity": "warning",
                "detail": f"Shot {row['id']}: lora_name '{lora_name}' looks like a bare keyword (not a file path)",
            })

    return issues


# ── Main audit ────────────────────────────────────────────────────────


async def run_audit(
    character_ids: list[int] | None = None,
    project_id: int | None = None,
    fix: bool = False,
) -> dict:
    """Run the full character name/slug/path/LoRA audit.

    Args:
        character_ids: Limit to specific characters. None = all.
        project_id: Limit to characters in a specific project.
        fix: If True, auto-fix safe issues (slug case in characters_present).

    Returns dict with:
        characters: per-character audit results
        global_issues: cross-cutting issues
        summary: counts by severity
        fixes_applied: list of fixes if fix=True
    """
    conn = await connect_direct()
    await conn.execute("SET search_path TO public")
    try:
        # Build character query — no slug column in DB, derive at runtime
        if character_ids:
            chars = await conn.fetch(
                "SELECT id, name, lora_path, project_id, role FROM characters WHERE id = ANY($1::int[])",
                character_ids,
            )
        elif project_id:
            chars = await conn.fetch(
                "SELECT id, name, lora_path, project_id, role FROM characters WHERE project_id = $1",
                project_id,
            )
        else:
            chars = await conn.fetch(
                "SELECT id, name, lora_path, project_id, role FROM characters"
            )

        results = {}
        all_issues = []
        fixes_applied = []

        for char in chars:
            char_dict = dict(char)
            slug = _name_to_slug(char_dict["name"])
            char_issues = []

            # 1. Slug derivation
            char_issues.extend(_check_slug_derivation(char_dict))

            # 2. Dataset directory (skip for background/victim roles)
            char_issues.extend(_check_dataset_dir(slug, role=char_dict.get("role")))

            # 3. LoRA file on disk
            char_issues.extend(_check_lora_file(char_dict, slug))

            # 4. LoRA naming convention
            char_issues.extend(_check_lora_path_convention(char_dict, slug))

            # 5. Shots referencing this character
            char_issues.extend(await _check_shots_characters_present(conn, slug, char_dict["id"]))

            results[f"{slug} (id={char_dict['id']})"] = char_issues
            all_issues.extend(char_issues)

        # Global checks (not per-character)
        global_issues = []

        # 6. Slug case mismatches across all shots
        global_issues.extend(await _check_slug_case_mismatches(conn))

        # 7. Phantom LoRAs
        global_issues.extend(await _check_phantom_loras(conn))

        all_issues.extend(global_issues)

        # Auto-fix: case mismatches in characters_present
        if fix:
            for issue in global_issues:
                if issue["check"] == "slug_case_mismatch":
                    # Extract the wrong and correct slugs
                    detail = issue["detail"]
                    wrong = detail.split("'")[1]
                    correct = detail.split("'")[3]
                    updated = await conn.execute(
                        """UPDATE shots
                           SET characters_present = array_replace(characters_present, $1, $2)
                           WHERE $1 = ANY(characters_present)""",
                        wrong, correct,
                    )
                    fixes_applied.append(f"Fixed characters_present: '{wrong}' → '{correct}' ({updated})")

        # Summary
        severity_counts = {"error": 0, "warning": 0, "info": 0}
        for issue in all_issues:
            severity_counts[issue["severity"]] = severity_counts.get(issue["severity"], 0) + 1

        return {
            "characters": results,
            "global_issues": global_issues,
            "summary": {
                "characters_audited": len(results),
                "total_issues": len(all_issues),
                **severity_counts,
            },
            "fixes_applied": fixes_applied,
        }

    finally:
        await conn.close()


# ── CLI entrypoint ────────────────────────────────────────────────────

if __name__ == "__main__":
    import asyncio
    import sys

    async def main():
        result = await run_audit()
        print(f"\n{'='*60}")
        print(f"CHARACTER AUDIT — {result['summary']['characters_audited']} characters")
        print(f"{'='*60}")

        for char_key, issues in result["characters"].items():
            if not issues:
                continue
            print(f"\n  {char_key}:")
            for issue in issues:
                icon = {"error": "!!!", "warning": " ! ", "info": " i "}[issue["severity"]]
                print(f"    [{icon}] {issue['check']}: {issue['detail']}")

        if result["global_issues"]:
            print(f"\n  GLOBAL ISSUES:")
            for issue in result["global_issues"]:
                icon = {"error": "!!!", "warning": " ! ", "info": " i "}[issue["severity"]]
                print(f"    [{icon}] {issue['check']}: {issue['detail']}")

        s = result["summary"]
        print(f"\n  Summary: {s['total_issues']} issues "
              f"({s['error']} errors, {s['warning']} warnings, {s['info']} info)")

        if s["error"] > 0:
            sys.exit(1)

    asyncio.run(main())
