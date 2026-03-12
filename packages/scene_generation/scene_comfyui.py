"""ComfyUI infrastructure helpers — copy files to input dir and poll for completion."""

import asyncio
import json
import logging
import shutil
from pathlib import Path

from packages.core.config import BASE_PATH, COMFYUI_URL, COMFYUI_OUTPUT_DIR, COMFYUI_INPUT_DIR

logger = logging.getLogger(__name__)


async def copy_to_comfyui_input(image_path: str) -> str:
    """Copy source image to ComfyUI input dir, return the filename."""
    src = Path(image_path)
    if not src.is_absolute():
        src = BASE_PATH / image_path
    dest = COMFYUI_INPUT_DIR / src.name
    if not dest.exists():
        shutil.copy2(str(src), str(dest))
    return src.name


def is_source_already_queued(source_name: str) -> str | None:
    """Check if a source image/video is already running or pending in ComfyUI.

    Inspects both queue_running and queue_pending for LoadImage or
    VHS_LoadVideoPath nodes referencing the same file.  Returns the
    prompt_id of the existing job if found, otherwise None.
    """
    import urllib.request

    try:
        req = urllib.request.Request(f"{COMFYUI_URL}/queue")
        resp = urllib.request.urlopen(req, timeout=5)
        queue = json.loads(resp.read())
    except Exception:
        return None  # Can't reach ComfyUI — let caller decide

    for bucket in ("queue_running", "queue_pending"):
        for item in queue.get(bucket, []):
            pid = item[1] if len(item) > 1 else None
            nodes = item[2] if len(item) > 2 and isinstance(item[2], dict) else {}
            for node in nodes.values():
                ct = node.get("class_type", "")
                if ct in ("LoadImage", "VHS_LoadVideoPath"):
                    img = node.get("inputs", {}).get("image", "") or node.get("inputs", {}).get("video", "")
                    if img and Path(img).name == Path(source_name).name:
                        return pid
    return None


async def poll_comfyui_completion(prompt_id: str, timeout_seconds: int = 1800) -> dict:
    """Poll ComfyUI /history until the prompt completes or times out."""
    import urllib.request
    import time as _time
    start = _time.time()
    _not_found_count = 0
    while (_time.time() - start) < timeout_seconds:
        try:
            req = urllib.request.Request(f"{COMFYUI_URL}/history/{prompt_id}")
            resp = urllib.request.urlopen(req, timeout=10)
            history = json.loads(resp.read())
            if prompt_id not in history:
                _not_found_count += 1
                # If prompt not found after 2 minutes (24 polls × 5s), it's gone
                # (ComfyUI was restarted or prompt was never accepted)
                if _not_found_count >= 24:
                    # Also check queue — if it's not running or pending, it's truly lost
                    try:
                        _q_req = urllib.request.Request(f"{COMFYUI_URL}/queue")
                        _q_resp = urllib.request.urlopen(_q_req, timeout=5)
                        _q_data = json.loads(_q_resp.read())
                        _running_ids = [r[1] for r in _q_data.get("queue_running", []) if len(r) > 1]
                        _pending_ids = [r[1] for r in _q_data.get("queue_pending", []) if len(r) > 1]
                        if prompt_id not in _running_ids and prompt_id not in _pending_ids:
                            logger.error(f"poll_comfyui: prompt {prompt_id} not in history/queue after {_not_found_count} checks — lost")
                            return {"status": "error", "output_files": [], "error": "Prompt lost (not in ComfyUI history or queue)"}
                    except Exception:
                        pass
                await asyncio.sleep(5)
                continue
            _not_found_count = 0  # Reset on found
            if prompt_id in history:
                entry = history[prompt_id]
                # Check execution status
                status_info = entry.get("status", {})
                status_str = status_info.get("status_str", "unknown")
                if status_str == "error":
                    # Extract error details from messages
                    msgs = status_info.get("messages", [])
                    err_detail = ""
                    for msg in msgs:
                        if isinstance(msg, list) and len(msg) >= 2 and "error" in str(msg[0]).lower():
                            err_detail = str(msg[1])[:200]
                    return {"status": "error", "output_files": [], "error": err_detail or "ComfyUI execution error"}
                outputs = entry.get("outputs", {})
                videos = []
                for node_output in outputs.values():
                    for key in ("videos", "gifs", "images"):
                        for item in node_output.get(key, []):
                            fn = item.get("filename")
                            if fn:
                                videos.append(fn)
                    # Also check 'video' (singular) used by some Wan nodes
                    if "video" in node_output:
                        v = node_output["video"]
                        if isinstance(v, dict) and v.get("filename"):
                            videos.append(v["filename"])
                        elif isinstance(v, list):
                            for item in v:
                                fn = item.get("filename") if isinstance(item, dict) else None
                                if fn:
                                    videos.append(fn)
                if not videos and status_str == "success":
                    # Scan output dir for files matching prefix (fallback)
                    try:
                        import glob as _glob
                        prompt_files = _glob.glob(str(COMFYUI_OUTPUT_DIR / f"*{prompt_id[:8]}*"))
                        videos = [Path(f).name for f in prompt_files if f.endswith((".mp4", ".webm"))]
                    except Exception:
                        pass
                return {"status": "completed", "output_files": videos}
        except Exception:
            pass
        await asyncio.sleep(5)
    return {"status": "timeout", "output_files": []}
