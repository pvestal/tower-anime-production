#!/usr/bin/env python3
"""
Job Tracking System for ComfyUI Generation Pipeline
Provides centralized tracking for all generation jobs across projects
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor
import json
import uuid
import requests
from datetime import datetime
import threading
import time

app = Flask(__name__)
CORS(app)

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'database': 'anime_production',
    'user': 'patrick',
    'password': 'tower_echo_brain_secret_key_2025'
}

COMFYUI_API = "http://localhost:8188"

def get_db():
    """Get database connection"""
    return psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)

def queue_comfyui_generation(job_id, workflow_type, params):
    """Queue a ComfyUI workflow and update job with prompt_id"""
    try:
        # Load SSOT workflow based on type
        workflow_map = {
            'base_image': '/opt/tower-anime-production/workflows/ssot/workflow_tokyo_debt_base.json',
            'svd_video': '/opt/tower-anime-production/workflows/ssot/workflow_svd_video.json',
            'openpose_skeleton': '/opt/tower-anime-production/workflows/openpose_workflow.json',
            'pose_controlled': '/opt/tower-anime-production/workflows/pose_controlled_workflow.json'
        }

        workflow_path = workflow_map.get(workflow_type)
        if not workflow_path:
            raise ValueError(f"Unknown workflow type: {workflow_type}")

        # Load and inject parameters
        from pathlib import Path
        if Path(workflow_path).exists():
            with open(workflow_path, 'r') as f:
                workflow_template = json.load(f)
                workflow = workflow_template.get('workflow', workflow_template)
        else:
            # Create basic workflow if template doesn't exist
            workflow = create_basic_workflow(workflow_type, params)

        # Inject parameters
        workflow_str = json.dumps(workflow)
        for key, value in params.items():
            workflow_str = workflow_str.replace(f"{{{{{key}}}}}", str(value))
        workflow = json.loads(workflow_str)

        # Submit to ComfyUI
        response = requests.post(
            f"{COMFYUI_API}/prompt",
            json={"prompt": workflow}
        )

        if response.status_code == 200:
            prompt_id = response.json().get('prompt_id')

            # Update job with ComfyUI prompt ID
            with get_db() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE generation_jobs
                        SET comfyui_prompt_id = %s,
                            status = 'queued',
                            updated_at = NOW()
                        WHERE id = %s
                    """, (prompt_id, job_id))
                    conn.commit()

            return prompt_id
        else:
            raise Exception(f"ComfyUI error: {response.status_code}")

    except Exception as e:
        # Mark job as failed
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE generation_jobs
                    SET status = 'failed',
                        error_message = %s,
                        updated_at = NOW()
                    WHERE id = %s
                """, (str(e), job_id))
                conn.commit()
        return None

def create_basic_workflow(workflow_type, params):
    """Create a basic workflow if template doesn't exist"""
    if workflow_type == 'openpose_skeleton':
        return {
            "1": {
                "class_type": "LoadImage",
                "inputs": {"image": params.get('image', 'input.png')}
            },
            "2": {
                "class_type": "OpenposePreprocessor",
                "inputs": {
                    "detect_hand": "enable",
                    "detect_body": "enable",
                    "detect_face": "enable",
                    "resolution": 512,
                    "image": ["1", 0]
                }
            },
            "3": {
                "class_type": "SaveImage",
                "inputs": {
                    "images": ["2", 0],
                    "filename_prefix": f"JOB_{params.get('job_id', 'unknown')}_skeleton"
                }
            }
        }
    return {}

@app.route('/api/jobs/create', methods=['POST'])
def create_job():
    """Create a new generation job"""
    data = request.json
    job_id = str(uuid.uuid4())

    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO generation_jobs
                    (id, project_name, job_type, status, input_data, created_by)
                    VALUES (%s, %s, %s, 'pending', %s, %s)
                    RETURNING id
                """, (
                    job_id,
                    data.get('project_name', 'tokyo_debt_desire'),
                    data.get('job_type', 'base_image'),
                    json.dumps(data.get('parameters', {})),
                    data.get('created_by', 'api')
                ))
                conn.commit()

        # Queue the job asynchronously
        thread = threading.Thread(
            target=queue_comfyui_generation,
            args=(job_id, data.get('job_type'), data.get('parameters', {}))
        )
        thread.start()

        return jsonify({
            'job_id': job_id,
            'status': 'created',
            'message': 'Job queued for processing'
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/jobs/<job_id>/status', methods=['GET'])
def get_job_status(job_id):
    """Get status of a specific job"""
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, project_name, job_type, status, progress,
                           current_node, output_data, error_message,
                           created_at, updated_at
                    FROM generation_jobs
                    WHERE id = %s
                """, (job_id,))
                job = cur.fetchone()

                if not job:
                    return jsonify({'error': 'Job not found'}), 404

                # Convert timestamps to ISO format
                job['created_at'] = job['created_at'].isoformat()
                job['updated_at'] = job['updated_at'].isoformat()

                return jsonify(job)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/jobs', methods=['GET'])
def list_jobs():
    """List all jobs with optional filtering"""
    project = request.args.get('project')
    status = request.args.get('status')
    limit = request.args.get('limit', 20)

    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                query = """
                    SELECT id, project_name, job_type, status, progress,
                           created_at, updated_at
                    FROM generation_jobs
                """
                conditions = []
                params = []

                if project:
                    conditions.append("project_name = %s")
                    params.append(project)
                if status:
                    conditions.append("status = %s")
                    params.append(status)

                if conditions:
                    query += " WHERE " + " AND ".join(conditions)

                query += " ORDER BY created_at DESC LIMIT %s"
                params.append(limit)

                cur.execute(query, params)
                jobs = cur.fetchall()

                # Convert timestamps
                for job in jobs:
                    job['created_at'] = job['created_at'].isoformat()
                    job['updated_at'] = job['updated_at'].isoformat()

                return jsonify(jobs)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/jobs/<job_id>/update', methods=['POST'])
def update_job_status(job_id):
    """Update job status (called by WebSocket bridge)"""
    data = request.json

    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                updates = []
                params = []

                if 'status' in data:
                    updates.append("status = %s")
                    params.append(data['status'])
                if 'progress' in data:
                    updates.append("progress = %s")
                    params.append(data['progress'])
                if 'current_node' in data:
                    updates.append("current_node = %s")
                    params.append(data['current_node'])
                if 'output_data' in data:
                    updates.append("output_data = %s")
                    params.append(json.dumps(data['output_data']))
                if 'error_message' in data:
                    updates.append("error_message = %s")
                    params.append(data['error_message'])

                updates.append("updated_at = NOW()")
                params.append(job_id)

                cur.execute(f"""
                    UPDATE generation_jobs
                    SET {', '.join(updates)}
                    WHERE id = %s
                """, params)
                conn.commit()

        return jsonify({'status': 'updated'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/jobs/stats', methods=['GET'])
def get_job_stats():
    """Get statistics about jobs"""
    project = request.args.get('project')

    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                base_query = "FROM generation_jobs"
                params = []

                if project:
                    base_query += " WHERE project_name = %s"
                    params.append(project)

                # Get counts by status
                cur.execute(f"""
                    SELECT
                        COUNT(*) FILTER (WHERE status = 'pending') as pending,
                        COUNT(*) FILTER (WHERE status = 'queued') as queued,
                        COUNT(*) FILTER (WHERE status = 'running') as running,
                        COUNT(*) FILTER (WHERE status = 'success') as success,
                        COUNT(*) FILTER (WHERE status = 'failed') as failed,
                        COUNT(*) as total
                    {base_query}
                """, params)

                stats = cur.fetchone()

                # Get recent success rate
                cur.execute(f"""
                    SELECT
                        COUNT(*) FILTER (WHERE status = 'success') * 100.0 /
                        NULLIF(COUNT(*), 0) as success_rate
                    {base_query}
                    {' AND' if project else 'WHERE'} created_at > NOW() - INTERVAL '24 hours'
                """, params)

                recent = cur.fetchone()
                stats['success_rate_24h'] = float(recent['success_rate'] or 0)

                return jsonify(stats)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("Starting Job Tracker API on port 5001...")
    app.run(host='0.0.0.0', port=5001, debug=True)
