"""Visual Pipeline router — generation, gallery endpoints.

Vision quality review endpoints are in visual_review.py (included as sub-router).
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from packages.core.config import BASE_PATH, COMFYUI_OUTPUT_DIR, normalize_sampler
from packages.core.db import get_char_project_map
from packages.core.auth import get_user_projects
from packages.core.models import GenerateRequest
from packages.core.audit import log_generation
from packages.core.events import event_bus, GENERATION_SUBMITTED
from packages.core.model_selector import recommend_params

from .comfyui import build_comfyui_workflow, submit_comfyui_workflow, get_comfyui_progress
from .visual_review import router as review_router

logger = logging.getLogger(__name__)
router = APIRouter()
router.include_router(review_router)


@router.post("/generate/{character_slug}")
async def generate_for_character(character_slug: str, body: GenerateRequest, allowed_projects: list[int] = Depends(get_user_projects)):
    """Generate an image or video for a character using SSOT profile."""
    char_map = await get_char_project_map()
    db_info = char_map.get(character_slug)
    if not db_info:
        raise HTTPException(status_code=404, detail=f"Character '{character_slug}' not found")

    # Check project access
    project_id = db_info.get("project_id")
    if project_id and project_id not in allowed_projects:
        raise HTTPException(status_code=403, detail="Access denied to this character's project")

    # Use style_override if provided, otherwise use project default
    style_info = db_info
    if body.style_override:
        from packages.core.db import get_pool
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT checkpoint_model, positive_prompt_template, negative_prompt_template, "
                "cfg_scale, sampler, steps, width, height, scheduler "
                "FROM generation_styles WHERE style_name = $1", body.style_override
            )
            if not row:
                raise HTTPException(status_code=400, detail=f"Style '{body.style_override}' not found")
            style_info = {**db_info, **dict(row)}
            logger.info(f"Using style override '{body.style_override}' for {character_slug}")

    checkpoint = style_info.get("checkpoint_model")
    if not checkpoint:
        raise HTTPException(status_code=400, detail="No checkpoint model configured for this character's project")

    prompt = body.prompt_override or db_info.get("design_prompt", "")
    if not prompt:
        raise HTTPException(status_code=400, detail="No design_prompt and no prompt_override provided")

    # Prepend positive_prompt_template from style (quality tags)
    style_preamble = style_info.get("positive_prompt_template") or db_info.get("style_preamble")
    if style_preamble and body.prompt_override:
        # For overrides, prepend the style's quality tags
        prompt = f"{style_preamble}, {prompt}"
    elif style_preamble and not body.prompt_override:
        prompt = f"{style_preamble}, {prompt}"

    norm_sampler, norm_scheduler = normalize_sampler(
        style_info.get("sampler"), style_info.get("scheduler")
    )

    # Use style's negative template if no explicit negative given
    style_negative = style_info.get("negative_prompt_template", "")
    base_negative = body.negative_prompt or style_negative or "worst quality, low quality, blurry, deformed"

    # Auto-enhance negative prompt with learned rejection patterns from DB
    try:
        rec = await recommend_params(
            character_slug, project_name=db_info.get("project_name"),
            checkpoint_model=checkpoint,
        )
        learned_neg = rec.get("learned_negatives", "")
        if learned_neg:
            base_negative = f"{base_negative}, {learned_neg}"
            logger.info(f"Enhanced negative prompt for {character_slug} with learned terms")
    except Exception:
        pass  # Never block generation on recommendation failure

    # Build extra_loras list from test LoRA if provided
    extra_loras = None
    if body.extra_lora:
        strength = body.extra_lora_strength if body.extra_lora_strength is not None else 0.7
        extra_loras = [(body.extra_lora, strength)]

    workflow = build_comfyui_workflow(
        design_prompt=prompt,
        checkpoint_model=checkpoint,
        cfg_scale=style_info.get("cfg_scale") or 7.0,
        steps=style_info.get("steps") or 25,
        sampler=norm_sampler,
        scheduler=norm_scheduler,
        width=style_info.get("width") or 512,
        height=style_info.get("height") or 768,
        negative_prompt=base_negative,
        generation_type=body.generation_type,
        seed=body.seed,
        character_slug=character_slug,
        db_lora_path=db_info.get("lora_path"),
        lora_trigger=db_info.get("lora_trigger"),
        extra_loras=extra_loras,
    )

    try:
        prompt_id = submit_comfyui_workflow(workflow)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"ComfyUI submission failed: {e}")

    actual_seed = workflow["3"]["inputs"]["seed"]

    # Log to generation_history
    gen_id = await log_generation(
        character_slug=character_slug,
        project_name=db_info.get("project_name"),
        comfyui_prompt_id=prompt_id,
        generation_type=body.generation_type,
        checkpoint_model=checkpoint,
        prompt=prompt,
        negative_prompt=body.negative_prompt or "worst quality, low quality, blurry, deformed",
        seed=actual_seed,
        cfg_scale=db_info.get("cfg_scale"),
        steps=db_info.get("steps"),
        sampler=norm_sampler,
        scheduler=norm_scheduler,
        width=db_info.get("width"),
        height=db_info.get("height"),
    )

    await event_bus.emit(GENERATION_SUBMITTED, {
        "character_slug": character_slug,
        "prompt_id": prompt_id,
        "generation_history_id": gen_id,
        "project_name": db_info.get("project_name"),
    })

    return {
        "prompt_id": prompt_id,
        "generation_history_id": gen_id,
        "character": character_slug,
        "generation_type": body.generation_type,
        "prompt_used": prompt,
        "checkpoint": checkpoint,
        "seed": actual_seed,
    }


@router.get("/generate/{prompt_id}/status")
async def get_generation_status(prompt_id: str):
    """Check ComfyUI generation progress."""
    return get_comfyui_progress(prompt_id)


@router.get("/character-thumbnails")
async def get_character_thumbnails(
    allowed_projects: list[int] = Depends(get_user_projects),
):
    """Return one thumbnail image filename per character (most recent image in dataset)."""
    char_map = await get_char_project_map()
    char_map = {k: v for k, v in char_map.items() if v.get("project_id") in allowed_projects}
    thumbnails = {}
    for slug, d in char_map.items():
        img_dir = BASE_PATH / slug / "images"
        if not img_dir.exists():
            continue
        pngs = sorted(img_dir.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
        if pngs:
            thumbnails[slug] = f"dataset/{slug}/{pngs[0].name}"
    return {"thumbnails": thumbnails}


@router.get("/dataset/{slug}/{filename}")
async def get_dataset_image(slug: str, filename: str):
    """Serve a character dataset image."""
    import re as _re
    if not _re.match(r'^[a-z0-9_-]+$', slug) or '..' in filename:
        raise HTTPException(status_code=400, detail="Invalid path")
    image_path = BASE_PATH / slug / "images" / filename
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(image_path)


@router.get("/gallery")
async def get_gallery(
    limit: int = 60,
    offset: int = 0,
    search: str = "",
    character: str = "",
    project: str = "",
    checkpoint: str = "",
    pose: str = "",
):
    """Get images from ComfyUI output enriched with DB metadata. Supports infinite scroll."""
    from packages.core.db import get_pool

    if not COMFYUI_OUTPUT_DIR.exists():
        return {"images": [], "total": 0, "has_more": False}

    # Build DB lookup: map character_slug → latest generation metadata
    pool = await get_pool()
    rows = await pool.fetch("""
        SELECT DISTINCT ON (character_slug)
            character_slug, project_name, checkpoint_model
        FROM generation_history
        WHERE character_slug IS NOT NULL
        ORDER BY character_slug, created_at DESC
    """)
    # slug → {project_name, checkpoint_model}
    char_meta: dict[str, dict] = {}
    for r in rows:
        char_meta[r["character_slug"]] = {
            "project_name": r["project_name"] or "",
            "checkpoint_model": r["checkpoint_model"] or "",
        }

    # Also build reverse map: project_name → set of slugs (for project filter)
    project_slugs: dict[str, set[str]] = {}
    for slug, meta in char_meta.items():
        pn = meta["project_name"]
        if pn:
            project_slugs.setdefault(pn, set()).add(slug)

    # Scan files
    image_files = []
    for ext in ("*.png", "*.jpg"):
        image_files.extend(COMFYUI_OUTPUT_DIR.glob(ext))
    image_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    def _normalize(text: str) -> str:
        return text.lower().strip().replace(" ", "_").replace("-", "_")

    def _extract_char_slug(filename_stem: str) -> str | None:
        """Try to match a known character slug from the filename."""
        fl = filename_stem.lower()
        # Check all known slugs (longest first to match multi-word names)
        for slug in sorted(char_meta.keys(), key=len, reverse=True):
            if slug in fl:
                return slug
        return None

    def matches(img_path) -> tuple[bool, str | None]:
        """Return (matches, character_slug)."""
        fl = img_path.stem.lower()
        slug = _extract_char_slug(fl)
        meta = char_meta.get(slug) if slug else None

        # Search: check filename, project_name, checkpoint, character slug
        if search:
            q = _normalize(search)
            searchable = fl
            if meta:
                searchable += f" {meta['project_name'].lower()} {meta['checkpoint_model'].lower()}"
            if q not in searchable.replace(" ", "_") and q not in searchable:
                return False, slug

        # Character filter
        if character:
            cn = _normalize(character)
            if not slug or cn not in slug:
                # Also check by display name from filename
                if cn not in fl:
                    return False, slug

        # Project filter — match by DB project name
        if project:
            pn = _normalize(project)
            if meta and pn in _normalize(meta["project_name"]):
                pass  # match
            elif pn in fl:
                pass  # fallback filename match
            else:
                return False, slug

        # Checkpoint filter
        if checkpoint:
            cn = _normalize(checkpoint)
            if not meta or cn not in _normalize(meta["checkpoint_model"]):
                return False, slug

        # Pose filter — match in filename
        if pose:
            if _normalize(pose) not in fl:
                return False, slug

        return True, slug

    # Filter and enrich
    filtered_items = []
    for img in image_files:
        ok, slug = matches(img)
        if ok:
            filtered_items.append((img, slug))

    total = len(filtered_items)
    page = filtered_items[offset:offset + limit]

    results = []
    for img, slug in page:
        meta = char_meta.get(slug) if slug else None
        entry = {
            "filename": img.name,
            "created_at": datetime.fromtimestamp(img.stat().st_mtime).isoformat(),
            "size_kb": round(img.stat().st_size / 1024, 1),
        }
        if meta:
            entry["project_name"] = meta["project_name"]
            entry["checkpoint_model"] = meta["checkpoint_model"]
            entry["character_slug"] = slug
        results.append(entry)

    return {
        "images": results,
        "total": total,
        "has_more": (offset + limit) < total,
    }


@router.get("/gallery/filters")
async def get_gallery_filters():
    """Get available filter values from DB generation history."""
    from packages.core.db import get_pool

    pool = await get_pool()

    projects = await pool.fetch("""
        SELECT DISTINCT project_name FROM generation_history
        WHERE project_name IS NOT NULL ORDER BY project_name
    """)
    characters = await pool.fetch("""
        SELECT DISTINCT character_slug FROM generation_history
        WHERE character_slug IS NOT NULL ORDER BY character_slug
    """)
    checkpoints = await pool.fetch("""
        SELECT DISTINCT checkpoint_model FROM generation_history
        WHERE checkpoint_model IS NOT NULL ORDER BY checkpoint_model
    """)

    return {
        "projects": [r["project_name"] for r in projects],
        "characters": [r["character_slug"].replace("_", " ").title() for r in characters],
        "character_slugs": [r["character_slug"] for r in characters],
        "checkpoints": [r["checkpoint_model"] for r in checkpoints],
    }


@router.get("/gallery/image/{filename}")
async def get_gallery_image(filename: str):
    """Serve a gallery image from ComfyUI output."""
    image_path = COMFYUI_OUTPUT_DIR / filename
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(image_path)
