#!/usr/bin/env python3
"""
Tower Anime Production - Complete Frontend Dashboard
Director/Editor control system with real-time monitoring
"""

from flask import Flask, render_template, jsonify, request, send_file
from flask_cors import CORS
import os
import json
import psycopg2
from datetime import datetime
from pathlib import Path

app = Flask(__name__,
            template_folder='templates',
            static_folder='static')
CORS(app)

# Database connection
def get_db():
    return psycopg2.connect(
        host="localhost",
        database="anime_production",
        user="patrick",
        password="tower_echo_brain_secret_key_2025"
    )

@app.route('/')
def dashboard():
    """Main production dashboard"""
    return render_template('dashboard.html')

@app.route('/characters')
def characters_page():
    """Character management interface"""
    return render_template('characters.html')

@app.route('/storylines')
def storylines_page():
    """Storyline editor"""
    return render_template('storylines.html')

@app.route('/scenes')
def scenes_page():
    """Scene composer"""
    return render_template('scenes.html')

@app.route('/models')
def models_page():
    """Model library with CivitAI integration"""
    return render_template('models.html')

@app.route('/jobs')
def jobs_page():
    """Job queue and monitoring"""
    return render_template('jobs.html')

@app.route('/editor/<int:scene_id>')
def scene_editor(scene_id):
    """Interactive scene editor with live preview"""
    return render_template('editor.html', scene_id=scene_id)

# API endpoints for frontend
@app.route('/api/characters/list')
def get_characters():
    """Get all characters with details"""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT character_name, project, checkpoint, seed,
               COUNT(*) as image_count
        FROM character_generations
        WHERE character_name IS NOT NULL
        GROUP BY character_name, project, checkpoint, seed
        ORDER BY character_name
    """)

    characters = []
    for row in cursor.fetchall():
        characters.append({
            "name": row[0],
            "project": row[1],
            "checkpoint": row[2],
            "seed": row[3],
            "image_count": row[4],
            "lora_trained": False,  # Check if LoRA exists
            "status": "ready"
        })

    cursor.close()
    conn.close()

    return jsonify(characters)

@app.route('/api/storylines/list')
def get_storylines():
    """Get all storylines with scene count"""
    conn = get_db()
    cursor = conn.cursor()

    # Get storylines
    cursor.execute("""
        SELECT id, title, description, created_at
        FROM storylines
        ORDER BY created_at DESC
    """)

    storylines = []
    for row in cursor.fetchall():
        # Count scenes
        cursor.execute("SELECT COUNT(*) FROM scenes WHERE storyline_id = %s", (row[0],))
        scene_count = cursor.fetchone()[0]

        storylines.append({
            "id": row[0],
            "title": row[1],
            "description": row[2],
            "created_at": row[3].isoformat() if row[3] else None,
            "scene_count": scene_count,
            "status": "ready" if scene_count > 0 else "empty"
        })

    cursor.close()
    conn.close()

    return jsonify(storylines)

@app.route('/api/dashboard/stats')
def dashboard_stats():
    """Get dashboard statistics"""
    conn = get_db()
    cursor = conn.cursor()

    # Get stats
    stats = {}

    # Character count
    cursor.execute("SELECT COUNT(DISTINCT character_name) FROM character_generations WHERE character_name IS NOT NULL")
    stats['total_characters'] = cursor.fetchone()[0]

    # Total generations
    cursor.execute("SELECT COUNT(*) FROM character_generations")
    stats['total_generations'] = cursor.fetchone()[0]

    # Storylines
    cursor.execute("SELECT COUNT(*) FROM storylines")
    stats['total_storylines'] = cursor.fetchone()[0]

    # Scenes
    cursor.execute("SELECT COUNT(*) FROM scenes")
    stats['total_scenes'] = cursor.fetchone()[0]

    # Recent generations
    cursor.execute("""
        SELECT character_name, project, created_at
        FROM character_generations
        WHERE created_at IS NOT NULL
        ORDER BY created_at DESC
        LIMIT 5
    """)

    stats['recent_generations'] = []
    for row in cursor.fetchall():
        stats['recent_generations'].append({
            "character": row[0],
            "project": row[1],
            "created_at": row[2].isoformat() if row[2] else None
        })

    cursor.close()
    conn.close()

    return jsonify(stats)

@app.route('/api/scene/preview', methods=['POST'])
def generate_preview():
    """Generate a preview for a scene"""
    data = request.json

    # TODO: Call ComfyUI to generate preview
    # For now, return mock data
    return jsonify({
        "success": True,
        "preview_url": f"/static/previews/preview_{data.get('scene_id', 1)}.png",
        "seed": data.get('seed', 12004)
    })

@app.route('/api/scene/generate', methods=['POST'])
def generate_scene():
    """Generate a full scene"""
    data = request.json

    # TODO: Submit to ComfyUI queue
    # For now, return mock response
    return jsonify({
        "success": True,
        "job_id": f"job_{datetime.now().timestamp()}",
        "message": "Scene generation started"
    })

@app.route('/api/models/local')
def get_local_models():
    """Get list of local models"""
    models = []

    # Check checkpoints
    checkpoint_dir = Path("/mnt/1TB-storage/ComfyUI/models/checkpoints")
    if checkpoint_dir.exists():
        for f in checkpoint_dir.glob("*.safetensors"):
            models.append({
                "name": f.stem,
                "type": "checkpoint",
                "path": str(f),
                "size": f.stat().st_size
            })

    # Check LoRAs
    lora_dir = Path("/mnt/1TB-storage/ComfyUI/models/loras")
    if lora_dir.exists():
        for f in lora_dir.glob("*.safetensors"):
            models.append({
                "name": f.stem,
                "type": "lora",
                "path": str(f),
                "size": f.stat().st_size
            })

    return jsonify(models)

@app.route('/api/character/<character_name>/settings')
def get_character_settings(character_name):
    """Get character-specific settings"""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT character_name, project, checkpoint, seed, output_path
        FROM character_generations
        WHERE character_name = %s
        ORDER BY created_at DESC
        LIMIT 5
    """, (character_name,))

    images = []
    character_data = None

    for row in cursor.fetchall():
        if not character_data:
            character_data = {
                "name": row[0],
                "project": row[1],
                "checkpoint": row[2],
                "seed": row[3]
            }
        if row[4] and os.path.exists(row[4]):
            images.append(row[4])

    cursor.close()
    conn.close()

    if character_data:
        character_data["face_images"] = images
        character_data["lora_trained"] = False  # Check if LoRA exists
        character_data["token"] = character_name.lower().replace(" ", "")

    return jsonify(character_data or {})

@app.route('/api/generate/all', methods=['POST'])
def generate_all_pending():
    """Generate all pending scenes"""
    # TODO: Queue all pending generations
    return jsonify({
        "success": True,
        "message": "Batch generation started",
        "queued": 0
    })

if __name__ == '__main__':
    # Create template directory if it doesn't exist
    os.makedirs('frontend/templates', exist_ok=True)
    os.makedirs('frontend/static', exist_ok=True)

    app.run(host='0.0.0.0', port=8330, debug=True)