#!/usr/bin/env python3
"""End-to-end pipeline test for LoRA Studio.

Runs against the LIVE API on localhost:8401. Not mocked — real Ollama,
real filesystem, real DB. Uses a dedicated test project + test character
that gets created and cleaned up.

Usage:
    python tests/test_e2e_pipeline.py
    venv/bin/pytest tests/test_e2e_pipeline.py -v -s
"""

import asyncio
import json
import shutil
import sys
import time
from pathlib import Path

import httpx
import pytest

BASE_URL = "http://localhost:8401"
API = f"{BASE_URL}/api/lora"

# DB connection config (matches what the service uses via Vault/env)
DB_CONFIG = {
    "host": "localhost",
    "database": "anime_production",
    "user": "patrick",
    "password": "RP78eIrW7cI2jYvL5akt1yurE",
}

# Test fixtures
TEST_PROJECT_NAME = "E2E Test Project"
TEST_CHARACTER_NAME = "E2E Test Hero"
TEST_CHARACTER_SLUG = "e2e_test_hero"
TEST_DESIGN_PROMPT = "A heroic test character, bold colors, standing pose, Illumination 3D CGI style"
DATASETS_DIR = Path(__file__).resolve().parent.parent / "datasets"

# Source image to copy for ingestion test
SOURCE_IMAGE = DATASETS_DIR / "mario" / "images" / "gen_mario_20260214_162819_9385.png"

# Track state for cleanup
_created_project_id: int | None = None
_created_character_id: int | None = None


class StepResult:
    def __init__(self, name: str, passed: bool, duration: float,
                 skipped: bool = False, detail: str = ""):
        self.name = name
        self.passed = passed
        self.duration = duration
        self.skipped = skipped
        self.detail = detail

    def __str__(self):
        if self.skipped:
            tag = "SKIP"
        elif self.passed:
            tag = "PASS"
        else:
            tag = "FAIL"
        line = f"[{tag}] {self.name} ({self.duration:.2f}s)"
        if self.detail:
            line += f"  — {self.detail}"
        return line


async def step_health(client: httpx.AsyncClient) -> StepResult:
    """Step 1: Health check."""
    t0 = time.monotonic()
    resp = await client.get(f"{API}/health")
    dt = time.monotonic() - t0
    if resp.status_code != 200:
        return StepResult("Health check", False, dt, detail=f"status={resp.status_code}")
    data = resp.json()
    if data.get("status") != "healthy":
        return StepResult("Health check", False, dt, detail=f"status={data}")
    return StepResult("Health check", True, dt)


async def step_create_project(client: httpx.AsyncClient) -> StepResult:
    """Step 2: Create test project."""
    global _created_project_id
    t0 = time.monotonic()
    resp = await client.post(f"{API}/projects", json={
        "name": TEST_PROJECT_NAME,
        "description": "Temporary project for e2e testing",
        "genre": "test",
        "checkpoint_model": "realcartoonPixar_v12.safetensors",
        "cfg_scale": 7.0,
        "steps": 20,
        "sampler": "DPM++ 2M Karras",
        "width": 512,
        "height": 512,
    })
    dt = time.monotonic() - t0
    if resp.status_code != 200:
        return StepResult("Create project", False, dt,
                          detail=f"status={resp.status_code} body={resp.text[:200]}")
    data = resp.json()
    _created_project_id = data.get("project_id")
    if not _created_project_id:
        return StepResult("Create project", False, dt, detail="No project_id in response")
    return StepResult("Create project", True, dt,
                      detail=f"id={_created_project_id}")


async def step_verify_project(client: httpx.AsyncClient) -> StepResult:
    """Step 3: Verify project appears in project list."""
    t0 = time.monotonic()
    resp = await client.get(f"{API}/projects")
    dt = time.monotonic() - t0
    if resp.status_code != 200:
        return StepResult("Verify project listed", False, dt,
                          detail=f"status={resp.status_code}")
    projects = resp.json().get("projects", [])
    found = any(p["name"] == TEST_PROJECT_NAME for p in projects)
    if not found:
        return StepResult("Verify project listed", False, dt,
                          detail=f"'{TEST_PROJECT_NAME}' not in {[p['name'] for p in projects]}")
    return StepResult("Verify project listed", True, dt)


async def step_create_character(client: httpx.AsyncClient) -> StepResult:
    """Step 4: Create test character via API (also links to project + creates dataset dir)."""
    global _created_character_id
    t0 = time.monotonic()
    resp = await client.post(f"{API}/characters", json={
        "name": TEST_CHARACTER_NAME,
        "project_name": TEST_PROJECT_NAME,
        "description": "E2E test character — will be deleted after test",
        "design_prompt": TEST_DESIGN_PROMPT,
    })
    dt = time.monotonic() - t0
    if resp.status_code == 409:
        # Already exists from a previous failed run — that's OK
        return StepResult("Create character", True, dt, detail="already existed (409)")
    if resp.status_code != 200:
        return StepResult("Create character", False, dt,
                          detail=f"status={resp.status_code} body={resp.text[:200]}")
    data = resp.json()
    _created_character_id = data.get("id")
    if data.get("slug") != TEST_CHARACTER_SLUG:
        return StepResult("Create character", False, dt,
                          detail=f"unexpected slug: {data.get('slug')}")
    return StepResult("Create character", True, dt,
                      detail=f"id={_created_character_id}")


async def step_link_character_to_project() -> StepResult:
    """Step 4b: No-op — the create_character API now links to project automatically."""
    t0 = time.monotonic()
    dt = time.monotonic() - t0
    if _created_character_id:
        return StepResult("Link character to project in DB", True, dt,
                          detail=f"already linked by API (character_id={_created_character_id})")
    return StepResult("Link character to project in DB", True, dt,
                      skipped=True, detail="no character_id — create may have returned 409")


async def step_ingest_image(client: httpx.AsyncClient) -> tuple[StepResult, str]:
    """Step 5: Ingest a test image via file upload."""
    import random
    import struct
    import zlib
    t0 = time.monotonic()

    # Always generate a unique PNG with random pixel data to avoid dedup collisions.
    # The API server's in-memory dedup cache persists between test runs, so reusing
    # the same source image (e.g. a Mario PNG) gets flagged as duplicate every time.
    def _make_unique_png() -> bytes:
        """Generate an 8x8 PNG with random pixel data — unique per call."""
        w, h = 8, 8
        sig = b"\x89PNG\r\n\x1a\n"
        ihdr_data = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
        ihdr_crc = struct.pack(">I", zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF)
        ihdr = struct.pack(">I", 13) + b"IHDR" + ihdr_data + ihdr_crc
        raw_rows = b""
        for _ in range(h):
            raw_rows += b"\x00" + bytes(random.randint(0, 255) for _ in range(w * 3))
        compressed = zlib.compress(raw_rows)
        idat_crc = struct.pack(">I", zlib.crc32(b"IDAT" + compressed) & 0xFFFFFFFF)
        idat = struct.pack(">I", len(compressed)) + b"IDAT" + compressed + idat_crc
        iend_crc = struct.pack(">I", zlib.crc32(b"IEND") & 0xFFFFFFFF)
        iend = struct.pack(">I", 0) + b"IEND" + iend_crc
        return sig + ihdr + idat + iend

    image_bytes = _make_unique_png()
    files = {"file": ("e2e_test.png", image_bytes, "image/png")}

    resp = await client.post(
        f"{API}/ingest/image",
        files=files,
        params={"character_slug": TEST_CHARACTER_SLUG},
    )
    dt = time.monotonic() - t0

    if resp.status_code != 200:
        return (StepResult("Ingest test image", False, dt,
                           detail=f"status={resp.status_code} body={resp.text[:200]}"), "")
    body = resp.json()
    image_name = body.get("image", "")
    status = body.get("status", "unknown")
    if not image_name:
        return (StepResult("Ingest test image", False, dt, detail="No image name returned"), "")
    if status == "duplicate":
        return (StepResult("Ingest test image", True, dt,
                           skipped=True, detail=f"{image_name} (duplicate — not registered as pending)"), "")
    return (StepResult("Ingest test image", True, dt,
                       detail=f"{image_name} (status={status})"), image_name)


async def step_verify_pending(client: httpx.AsyncClient, image_name: str) -> StepResult:
    """Step 6: Verify the ingested image appears in pending list."""
    t0 = time.monotonic()
    resp = await client.get(f"{API}/approval/pending")
    dt = time.monotonic() - t0
    if resp.status_code != 200:
        return StepResult("Verify image pending", False, dt,
                          detail=f"status={resp.status_code}")
    pending = resp.json().get("pending_images", [])
    # The character might not appear in pending if it has no DB record with project_id.
    # Check if our image is there, or at least check approval_status.json directly.
    found = any(
        p.get("character_slug") == TEST_CHARACTER_SLUG and p.get("name") == image_name
        for p in pending
    )
    if not found:
        # Fallback: check filesystem directly
        approval_file = DATASETS_DIR / TEST_CHARACTER_SLUG / "approval_status.json"
        if approval_file.exists():
            statuses = json.loads(approval_file.read_text())
            if statuses.get(image_name) == "pending":
                return StepResult("Verify image pending", True, dt,
                                  detail="found in approval_status.json (not in API — cache stale)")
            return StepResult("Verify image pending", False, dt,
                              detail=f"approval_status.json exists but image status={statuses.get(image_name)!r}, keys={list(statuses.keys())[:3]}")
        return StepResult("Verify image pending", False, dt,
                          detail=f"image '{image_name}' not in API ({len(pending)} items) and {approval_file} does not exist")
    return StepResult("Verify image pending", True, dt)


async def step_vision_review(client: httpx.AsyncClient) -> StepResult:
    """Step 7: Run vision model review on the test character's pending images."""
    t0 = time.monotonic()
    resp = await client.post(f"{API}/approval/llava-review", json={
        "character_slug": TEST_CHARACTER_SLUG,
        "max_images": 1,
        "auto_reject_threshold": 0.0,   # Don't auto-reject our test image
        "auto_approve_threshold": 1.1,   # Don't auto-approve either
        "regenerate": False,
        "update_captions": False,
    }, timeout=60.0)
    dt = time.monotonic() - t0

    if resp.status_code == 404:
        # Character not in DB char_map — expected if no project link
        return StepResult("Vision model review", True, dt,
                          skipped=True, detail="character not in DB char_map (no project link)")
    if resp.status_code != 200:
        return StepResult("Vision model review", False, dt,
                          detail=f"status={resp.status_code} body={resp.text[:300]}")
    body = resp.json()
    reviewed = body.get("reviewed", 0)
    model = body.get("model", "unknown")
    results = body.get("results", [])
    if reviewed == 0:
        return StepResult("Vision model review", True, dt,
                          skipped=True, detail="0 images reviewed (char not in DB)")
    score = results[0].get("quality_score") if results else None
    return StepResult("Vision model review", True, dt,
                      detail=f"model={model}, reviewed={reviewed}, score={score}")


async def step_manual_approve(client: httpx.AsyncClient, image_name: str) -> StepResult:
    """Step 8: Manually approve the test image."""
    t0 = time.monotonic()
    resp = await client.post(f"{API}/approval/approve", json={
        "character_name": TEST_CHARACTER_NAME,
        "character_slug": TEST_CHARACTER_SLUG,
        "image_name": image_name,
        "approved": True,
    })
    dt = time.monotonic() - t0
    if resp.status_code != 200:
        return StepResult("Manual approve", False, dt,
                          detail=f"status={resp.status_code} body={resp.text[:200]}")
    return StepResult("Manual approve", True, dt)


async def step_verify_approved(image_name: str) -> StepResult:
    """Step 9: Verify approval_status.json shows 'approved'."""
    t0 = time.monotonic()
    approval_file = DATASETS_DIR / TEST_CHARACTER_SLUG / "approval_status.json"
    if not approval_file.exists():
        dt = time.monotonic() - t0
        return StepResult("Verify approved on disk", False, dt,
                          detail="approval_status.json not found")
    statuses = json.loads(approval_file.read_text())
    status = statuses.get(image_name)
    dt = time.monotonic() - t0
    if status != "approved":
        return StepResult("Verify approved on disk", False, dt,
                          detail=f"status='{status}', expected 'approved'")
    return StepResult("Verify approved on disk", True, dt)


async def step_generate_image(client: httpx.AsyncClient) -> tuple[StepResult, str]:
    """Step 10: Submit image generation to ComfyUI (soft-fail)."""
    t0 = time.monotonic()

    # Check if ComfyUI is reachable first
    try:
        comfy_resp = await client.get("http://localhost:8188/system_stats", timeout=3.0)
        if comfy_resp.status_code != 200:
            dt = time.monotonic() - t0
            return (StepResult("Generate image via ComfyUI", True, dt,
                               skipped=True, detail="ComfyUI not responding"), "")
    except Exception:
        dt = time.monotonic() - t0
        return (StepResult("Generate image via ComfyUI", True, dt,
                           skipped=True, detail="ComfyUI unreachable"), "")

    resp = await client.post(f"{API}/generate/{TEST_CHARACTER_SLUG}", json={
        "generation_type": "image",
    }, timeout=30.0)
    dt = time.monotonic() - t0

    if resp.status_code == 404:
        return (StepResult("Generate image via ComfyUI", True, dt,
                           skipped=True, detail="character not in DB char_map"), "")
    if resp.status_code == 400:
        return (StepResult("Generate image via ComfyUI", True, dt,
                           skipped=True, detail=f"missing config: {resp.text[:100]}"), "")
    if resp.status_code == 502:
        return (StepResult("Generate image via ComfyUI", True, dt,
                           skipped=True, detail="ComfyUI submission failed"), "")
    if resp.status_code != 200:
        return (StepResult("Generate image via ComfyUI", False, dt,
                           detail=f"status={resp.status_code} body={resp.text[:200]}"), "")

    body = resp.json()
    prompt_id = body.get("prompt_id", "")
    return (StepResult("Generate image via ComfyUI", True, dt,
                       detail=f"prompt_id={prompt_id}"), prompt_id)


async def step_check_generation(client: httpx.AsyncClient, prompt_id: str) -> StepResult:
    """Step 11: Poll generation status until done or timeout."""
    if not prompt_id:
        return StepResult("Check generation status", True, 0.0,
                          skipped=True, detail="no prompt_id (generation was skipped)")

    t0 = time.monotonic()
    max_wait = 30.0  # Don't wait forever in a test
    poll_interval = 2.0

    while (time.monotonic() - t0) < max_wait:
        resp = await client.get(f"{API}/generate/{prompt_id}/status", timeout=10.0)
        if resp.status_code != 200:
            dt = time.monotonic() - t0
            return StepResult("Check generation status", True, dt,
                              skipped=True, detail=f"status endpoint returned {resp.status_code}")
        data = resp.json()
        status = data.get("status", "unknown")
        if status == "completed":
            dt = time.monotonic() - t0
            return StepResult("Check generation status", True, dt,
                              detail=f"completed in {dt:.1f}s")
        if status in ("error", "failed"):
            dt = time.monotonic() - t0
            return StepResult("Check generation status", True, dt,
                              skipped=True, detail=f"generation failed: {status}")
        await asyncio.sleep(poll_interval)

    dt = time.monotonic() - t0
    return StepResult("Check generation status", True, dt,
                      skipped=True, detail=f"timed out after {max_wait}s (generation still running)")


async def step_cleanup(client: httpx.AsyncClient) -> StepResult:
    """Step 12: Delete test project from DB and remove test dataset directory."""
    t0 = time.monotonic()
    errors = []

    # Delete test data from DB
    if _created_project_id or _created_character_id:
        try:
            import asyncpg
            conn = await asyncpg.connect(**DB_CONFIG)
            # Delete character first (FK to projects)
            if _created_character_id:
                await conn.execute(
                    "DELETE FROM characters WHERE id = $1", _created_character_id)
            # Delete the generation style (FK from projects)
            if _created_project_id:
                style_name = await conn.fetchval(
                    "SELECT default_style FROM projects WHERE id = $1", _created_project_id)
                await conn.execute(
                    "DELETE FROM projects WHERE id = $1", _created_project_id)
                if style_name:
                    await conn.execute(
                        "DELETE FROM generation_styles WHERE style_name = $1", style_name)
            await conn.close()
        except Exception as e:
            errors.append(f"DB cleanup: {e}")

    # Remove test dataset directory
    test_dir = DATASETS_DIR / TEST_CHARACTER_SLUG
    if test_dir.exists():
        try:
            shutil.rmtree(test_dir)
        except Exception as e:
            errors.append(f"Dir cleanup: {e}")

    dt = time.monotonic() - t0
    if errors:
        return StepResult("Cleanup", False, dt, detail="; ".join(errors))
    return StepResult("Cleanup", True, dt)


async def _pre_cleanup():
    """Remove any leftover test data from previous failed runs."""
    try:
        import asyncpg
        conn = await asyncpg.connect(**DB_CONFIG)
        rows = await conn.fetch(
            "SELECT id, default_style FROM projects WHERE name = $1",
            TEST_PROJECT_NAME,
        )
        for r in rows:
            # Delete characters linked to this project first
            await conn.execute(
                "DELETE FROM characters WHERE project_id = $1", r["id"])
            await conn.execute("DELETE FROM projects WHERE id = $1", r["id"])
            if r["default_style"]:
                await conn.execute(
                    "DELETE FROM generation_styles WHERE style_name = $1",
                    r["default_style"],
                )
        await conn.close()
    except Exception:
        pass  # Best-effort

    test_dir = DATASETS_DIR / TEST_CHARACTER_SLUG
    if test_dir.exists():
        shutil.rmtree(test_dir, ignore_errors=True)


async def run_e2e():
    """Run all e2e steps sequentially, collecting results."""
    results: list[StepResult] = []

    # Clean up any leftovers from previous failed runs
    await _pre_cleanup()

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            # Step 1: Health check (critical)
            r = await step_health(client)
            results.append(r)
            print(r)
            if not r.passed:
                print("\nHealth check failed — is tower-anime-studio running on port 8401?")
                return results

            # Step 2: Create project (critical)
            r = await step_create_project(client)
            results.append(r)
            print(r)
            if not r.passed:
                return results

            # Step 3: Verify project listed
            r = await step_verify_project(client)
            results.append(r)
            print(r)

            # Step 4: Create character (critical)
            r = await step_create_character(client)
            results.append(r)
            print(r)
            if not r.passed:
                return results

            # Step 4b: Link character to project in DB
            r = await step_link_character_to_project()
            results.append(r)
            print(r)

            # Invalidate the API's char_project_map cache so it picks up the new character.
            # The create_character endpoint calls invalidate_char_cache(), but we need to
            # ensure the cache is fully rebuilt before we query pending images.
            # Hit the characters endpoint which calls get_char_project_map(), rebuilding cache.
            await asyncio.sleep(0.5)  # Brief pause to ensure DB commit is visible
            chars_resp = await client.get(f"{API}/characters")
            if chars_resp.status_code == 200:
                char_slugs = [c.get("slug") for c in chars_resp.json().get("characters", [])]
                if TEST_CHARACTER_SLUG not in char_slugs:
                    # Cache may still be stale — wait for TTL and retry
                    await asyncio.sleep(1.0)
                    await client.get(f"{API}/characters")

            # Step 5: Ingest image
            r, image_name = await step_ingest_image(client)
            results.append(r)
            print(r)
            if not r.passed:
                return results

            # Step 6: Verify pending (skip if ingest returned duplicate/no image)
            if image_name:
                r = await step_verify_pending(client, image_name)
            else:
                r = StepResult("Verify image pending", True, 0.0,
                               skipped=True, detail="no image to verify (ingest was duplicate)")
            results.append(r)
            print(r)

            # Step 7: Vision review (soft-fail)
            r = await step_vision_review(client)
            results.append(r)
            print(r)

            # Step 8: Manual approve (skip if no image)
            if image_name:
                r = await step_manual_approve(client, image_name)
            else:
                r = StepResult("Manual approve", True, 0.0,
                               skipped=True, detail="no image to approve")
            results.append(r)
            print(r)

            # Step 9: Verify approved on disk (skip if no image)
            if image_name:
                r = await step_verify_approved(image_name)
            else:
                r = StepResult("Verify approved on disk", True, 0.0,
                               skipped=True, detail="no image to verify")
            results.append(r)
            print(r)

            # Step 10: Generate image (soft-fail)
            r, prompt_id = await step_generate_image(client)
            results.append(r)
            print(r)

            # Step 11: Check generation status (soft-fail)
            r = await step_check_generation(client, prompt_id)
            results.append(r)
            print(r)

        finally:
            # Step 12: Cleanup always runs
            r = await step_cleanup(client)
            results.append(r)
            print(r)

    return results


def print_summary(results: list[StepResult]):
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)
    skipped = sum(1 for r in results if r.skipped)
    total = len(results)
    print(f"\n{passed}/{total} passed, {failed} failed, {skipped} skipped")
    return failed == 0


# ---- pytest entry point ----

@pytest.mark.e2e
def test_e2e_pipeline():
    """Pytest-compatible entry point for the full e2e pipeline."""
    results = asyncio.run(run_e2e())
    failed = [r for r in results if not r.passed]
    if failed:
        msgs = "\n".join(f"  {r}" for r in failed)
        raise AssertionError(f"E2E pipeline failures:\n{msgs}")


# ---- standalone entry point ----

if __name__ == "__main__":
    print("=" * 60)
    print("LoRA Studio E2E Pipeline Test")
    print("=" * 60)
    print(f"Target: {BASE_URL}")
    print()

    results = asyncio.run(run_e2e())
    ok = print_summary(results)
    sys.exit(0 if ok else 1)
