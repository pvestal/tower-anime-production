#!/usr/bin/env python3
"""
Tower FramePack Diagnostic — Run this on Tower and paste the output back.
This gathers the exact node signatures, installed custom nodes,
model paths, and example workflow structure so we can build
a generation script that actually works.
"""

import json
import os
import sys
import glob
import subprocess

COMFYUI_URL = "http://localhost:8188"
COMFYUI_BASE = "/mnt/1TB-storage/ComfyUI"

try:
    import requests
except ImportError:
    print("ERROR: pip install requests")
    sys.exit(1)

output = {}

# ─── 1. ComfyUI Status ──────────────────────────────────────
print("=" * 60)
print("1. COMFYUI STATUS")
print("=" * 60)
try:
    stats = requests.get(f"{COMFYUI_URL}/system_stats", timeout=5).json()
    dev = stats.get("devices", [{}])[0]
    print(f"  GPU: {dev.get('name', '?')}")
    print(f"  VRAM Total: {dev.get('vram_total', 0) / 1024**3:.1f} GB")
    print(f"  VRAM Free:  {dev.get('vram_free', 0) / 1024**3:.1f} GB")
    output["comfyui_status"] = "running"
    output["gpu"] = dev.get("name", "unknown")
except Exception as e:
    print(f"  ❌ ComfyUI not responding: {e}")
    output["comfyui_status"] = f"down: {e}"
    print("\nStart ComfyUI first, then re-run this script.")
    sys.exit(1)

# ─── 2. FramePack Node Signatures ───────────────────────────
print("\n" + "=" * 60)
print("2. FRAMEPACK NODE SIGNATURES (exact inputs/outputs)")
print("=" * 60)
try:
    all_nodes = requests.get(f"{COMFYUI_URL}/object_info", timeout=15).json()

    # Find all FramePack-related nodes
    fp_nodes = {}
    for name, info in all_nodes.items():
        if "framepack" in name.lower() or "FramePack" in name:
            fp_nodes[name] = info

    # Also grab key infrastructure nodes we need
    infra_nodes = [
        "DualCLIPLoader", "CLIPTextEncode", "VAELoader", "VAEDecode",
        "VAEDecodeTiled", "LoadImage", "SaveImage", "EmptyHunyuanLatentVideo",
        "VHS_VideoCombine", "SaveVideo", "CLIPVisionLoader", "CLIPVisionEncode",
    ]
    for iname in infra_nodes:
        if iname in all_nodes:
            fp_nodes[iname] = all_nodes[iname]

    output["nodes"] = {}
    for name, info in sorted(fp_nodes.items()):
        req = info.get("input", {}).get("required", {})
        opt = info.get("input", {}).get("optional", {})
        outs = info.get("output", [])
        out_names = info.get("output_name", [])

        print(f"\n  [{name}]")
        output["nodes"][name] = {"required": {}, "optional": {}, "outputs": []}

        if req:
            print(f"    Required inputs:")
            for param, spec in req.items():
                # spec is like [["model1.safetensors", "model2.safetensors"], {...}]
                # or ["INT", {"default": 25, "min": 1}]
                # or ["MODEL"]
                if isinstance(spec, list) and len(spec) >= 1:
                    ptype = spec[0]
                    constraints = spec[1] if len(spec) > 1 else {}
                    if isinstance(ptype, list):
                        # Enum/dropdown — show first few options
                        opts_str = ptype[:5]
                        if len(ptype) > 5:
                            opts_str.append(f"... +{len(ptype)-5} more")
                        print(f"      {param}: ENUM {opts_str}")
                        output["nodes"][name]["required"][param] = {"type": "enum", "options": ptype}
                    else:
                        default = constraints.get("default", "") if isinstance(constraints, dict) else ""
                        print(f"      {param}: {ptype} (default={default})")
                        output["nodes"][name]["required"][param] = {"type": ptype, "default": default}
                else:
                    print(f"      {param}: {spec}")
                    output["nodes"][name]["required"][param] = {"type": str(spec)}

        if opt:
            print(f"    Optional inputs:")
            for param, spec in opt.items():
                if isinstance(spec, list) and len(spec) >= 1:
                    ptype = spec[0]
                    constraints = spec[1] if len(spec) > 1 else {}
                    if isinstance(ptype, list):
                        opts_str = ptype[:3]
                        print(f"      {param}: ENUM {opts_str}")
                        output["nodes"][name]["optional"][param] = {"type": "enum", "options": ptype}
                    else:
                        default = constraints.get("default", "") if isinstance(constraints, dict) else ""
                        print(f"      {param}: {ptype} (default={default})")
                        output["nodes"][name]["optional"][param] = {"type": ptype, "default": default}

        if outs:
            pairs = list(zip(out_names, outs)) if out_names else [(f"out_{i}", o) for i, o in enumerate(outs)]
            print(f"    Outputs: {pairs}")
            output["nodes"][name]["outputs"] = pairs

except Exception as e:
    print(f"  ❌ Failed to get node info: {e}")

# ─── 3. Model Files ─────────────────────────────────────────
print("\n" + "=" * 60)
print("3. MODEL FILES")
print("=" * 60)

model_dirs = {
    "diffusion_models": f"{COMFYUI_BASE}/models/diffusion_models",
    "text_encoders": f"{COMFYUI_BASE}/models/text_encoders",
    "clip_vision": f"{COMFYUI_BASE}/models/clip_vision",
    "vae": f"{COMFYUI_BASE}/models/vae",
}

output["models"] = {}
for category, path in model_dirs.items():
    print(f"\n  [{category}] {path}")
    files = []
    if os.path.isdir(path):
        for f in sorted(os.listdir(path)):
            fpath = os.path.join(path, f)
            if os.path.islink(fpath):
                target = os.readlink(fpath)
                real = os.path.realpath(fpath)
                exists = os.path.exists(real)
                size = os.path.getsize(real) / (1024**3) if exists else 0
                print(f"    {f} -> {target} ({'✅' if exists else '❌ BROKEN'} {size:.2f}GB)")
                files.append({"name": f, "symlink": target, "exists": exists, "size_gb": round(size, 2)})
            elif os.path.isdir(fpath):
                subfiles = os.listdir(fpath)
                print(f"    {f}/ ({len(subfiles)} files)")
                for sf in subfiles[:5]:
                    sfpath = os.path.join(fpath, sf)
                    sz = os.path.getsize(sfpath) / (1024**3) if os.path.isfile(sfpath) else 0
                    print(f"      {sf} ({sz:.2f}GB)")
                    files.append({"name": f"{f}/{sf}", "size_gb": round(sz, 2)})
            else:
                size = os.path.getsize(fpath) / (1024**3)
                print(f"    {f} ({size:.2f}GB)")
                files.append({"name": f, "size_gb": round(size, 2)})
    else:
        print(f"    ❌ Directory not found")
    output["models"][category] = files

# ─── 4. Custom Nodes Installed ───────────────────────────────
print("\n" + "=" * 60)
print("4. CUSTOM NODES")
print("=" * 60)

custom_dir = f"{COMFYUI_BASE}/custom_nodes"
output["custom_nodes"] = []
if os.path.isdir(custom_dir):
    for d in sorted(os.listdir(custom_dir)):
        dpath = os.path.join(custom_dir, d)
        if os.path.isdir(dpath) and not d.startswith("."):
            # Check for FramePack or Video related
            relevant = any(k in d.lower() for k in ["frame", "video", "vhs", "animate", "hunyuan"])
            marker = " ⭐" if relevant else ""
            print(f"  {d}{marker}")
            if relevant:
                output["custom_nodes"].append(d)

# ─── 5. Example Workflow ────────────────────────────────────
print("\n" + "=" * 60)
print("5. EXAMPLE WORKFLOW (API FORMAT)")
print("=" * 60)

example_paths = glob.glob(f"{COMFYUI_BASE}/custom_nodes/ComfyUI-FramePackWrapper*/example_workflows/*.json")
output["example_workflows"] = []

for wf_path in example_paths:
    fname = os.path.basename(wf_path)
    print(f"\n  [{fname}]")
    try:
        with open(wf_path) as f:
            wf = json.load(f)

        # ComfyUI saves in "UI format" with nodes array
        # We need to understand the structure
        if "nodes" in wf:
            nodes = wf["nodes"]
            print(f"    Format: ComfyUI UI (has 'nodes' array)")
            print(f"    Node count: {len(nodes)}")
            print(f"    Node types:")
            for node in sorted(nodes, key=lambda n: n.get("id", 0)):
                ntype = node.get("type", "?")
                nid = node.get("id", "?")
                widgets = node.get("widgets_values", [])
                # Show widget values for key nodes
                if any(k in ntype.lower() for k in ["framepack", "clip", "vae", "sampler", "load", "save", "vhs"]):
                    print(f"      id={nid}: {ntype}")
                    if widgets:
                        print(f"        widgets: {widgets}")

            # CRITICAL: dump the full workflow JSON for API conversion
            output["example_workflows"].append({
                "filename": fname,
                "full_json": wf,
            })
        elif "prompt" in wf:
            print(f"    Format: API format (has 'prompt' key)")
            output["example_workflows"].append({
                "filename": fname,
                "full_json": wf,
            })
        else:
            print(f"    Format: Unknown (keys: {list(wf.keys())[:5]})")

    except Exception as e:
        print(f"    ❌ Error reading: {e}")

# ─── 6. Recent ComfyUI History ──────────────────────────────
print("\n" + "=" * 60)
print("6. RECENT COMFYUI HISTORY (last 5 jobs)")
print("=" * 60)

try:
    history = requests.get(f"{COMFYUI_URL}/history", timeout=5).json()
    for pid, job in list(history.items())[-5:]:
        status = job.get("status", {}).get("status_str", "unknown")
        completed = job.get("status", {}).get("completed", False)
        outputs = job.get("outputs", {})
        output_files = []
        for nid, out in outputs.items():
            for key in ["images", "gifs", "videos"]:
                for item in out.get(key, []):
                    output_files.append(item.get("filename", "?"))

        icon = "✅" if completed and output_files else "❌"
        print(f"  {icon} {pid[:16]}... completed={completed} files={output_files}")
except Exception as e:
    print(f"  ❌ {e}")

# ─── 7. Dump Full JSON ──────────────────────────────────────
dump_path = "/tmp/framepack_diagnostic.json"
with open(dump_path, "w") as f:
    json.dump(output, f, indent=2, default=str)
print(f"\n{'=' * 60}")
print(f"FULL DIAGNOSTIC JSON: {dump_path}")
print(f"{'=' * 60}")
print(f"\nPaste the contents of {dump_path} back to Claude,")
print(f"or copy-paste the terminal output above.")
print(f"\nTo copy JSON: cat {dump_path} | xclip -selection clipboard")