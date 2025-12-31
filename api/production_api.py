#!/usr/bin/env python3
"""
Production API for Anime Dashboard Control
"""
from flask import Flask, jsonify, request, render_template
import subprocess
import json
import uuid
from pathlib import Path
from datetime import datetime
import os

app = Flask(__name__,
            template_folder='../frontend/templates',
            static_folder='../frontend/static')

PROJECTS = {
    "tokyo_debt_desire": {
        "canonical": "/mnt/1TB-storage/ComfyUI/input/Mei_Tokyo_Debt_SVD_smooth_00001.png",
        "poses": ["standing", "frontal", "professional", "professional_alt"],
        "description": "Tokyo urban professional theme"
    },
    "cyberpunk_mei": {
        "canonical": None,  # To be created
        "poses": ["action", "hacker", "neon", "street"],
        "description": "Cyberpunk neon theme (coming soon)"
    }
}

@app.route('/')
def dashboard():
    """Serve the main dashboard HTML"""
    return render_template('production_dashboard.html')

@app.route('/api/production/status')
def status():
    """Get current production status"""
    output_dir = Path("/mnt/1TB-storage/ComfyUI/output")
    tokyo_outputs = list(output_dir.glob("MEI_Tokyo_*"))
    all_outputs = list(output_dir.glob("MEI_*"))

    return jsonify({
        "projects": PROJECTS,
        "statistics": {
            "total_outputs": len(all_outputs),
            "tokyo_outputs": len(tokyo_outputs),
            "last_updated": datetime.now().isoformat()
        },
        "comfyui_status": check_comfyui_status()
    })

@app.route('/api/production/generate', methods=['POST'])
def generate():
    """Generate a new pose variation"""
    data = request.json
    project = data.get('project', 'tokyo_debt_desire')
    pose = data.get('pose', 'frontal')

    if project not in PROJECTS:
        return jsonify({"error": "Invalid project"}), 400

    # Generate job ID
    job_id = f"P-{uuid.uuid4().hex[:6].upper()}"

    # Prepare the script path
    script_path = '/opt/tower-anime-production/workflows/production_pipeline_v2.py'

    # Run production script in background
    cmd = ['python3', script_path, '--pose', pose, '--job-id', job_id]

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd='/opt/tower-anime-production'
        )

        return jsonify({
            "job_id": job_id,
            "project": project,
            "pose": pose,
            "status": "started",
            "message": f"Generating {pose} pose variation for {project}...",
            "pid": process.pid
        })
    except Exception as e:
        return jsonify({
            "error": str(e),
            "job_id": job_id,
            "status": "failed"
        }), 500

@app.route('/api/production/outputs')
def get_outputs():
    """Get list of recent outputs"""
    output_dir = Path("/mnt/1TB-storage/ComfyUI/output")
    outputs = []

    # Get all MEI files
    for f in sorted(output_dir.glob("MEI_*"), key=lambda x: x.stat().st_mtime, reverse=True):
        if f.suffix in ['.png', '.mp4']:
            stat = f.stat()
            outputs.append({
                "filename": f.name,
                "path": str(f),
                "size": f"{stat.st_size/1024:.0f}KB" if stat.st_size < 1024*1024 else f"{stat.st_size/(1024*1024):.1f}MB",
                "time": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                "type": "video" if f.suffix == '.mp4' else "image",
                "project": "tokyo" if "Tokyo" in f.name else "general"
            })

    return jsonify(outputs[:20])  # Return last 20 files

def check_comfyui_status():
    """Check if ComfyUI is running"""
    try:
        result = subprocess.run(
            ['curl', '-s', 'http://localhost:8188/system_stats'],
            capture_output=True,
            timeout=2
        )
        if result.returncode == 0:
            return "running"
    except:
        pass
    return "offline"

if __name__ == '__main__':
    # Ensure directories exist
    Path("/opt/tower-anime-production/frontend/templates").mkdir(parents=True, exist_ok=True)
    Path("/opt/tower-anime-production/frontend/static").mkdir(parents=True, exist_ok=True)

    app.run(host='0.0.0.0', port=5000, debug=True)