#!/usr/bin/env python3
"""
ECHO BRAIN CONTEXT EXTRACTOR
Extracts complete project context from anime production database
"""

import json
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
import sys

class AnimeContextExtractor:
    def __init__(self):
        self.db_config = {
            'host': 'localhost',
            'database': 'anime_production',
            'user': 'patrick',
            'password': '***REMOVED***'
        }

    def extract_full_context(self, project_id: int) -> dict:
        """Extract complete project context for Echo Brain"""

        conn = psycopg2.connect(**self.db_config)
        cur = conn.cursor(cursor_factory=RealDictCursor)

        context = {
            "extraction_timestamp": datetime.now().isoformat(),
            "project_id": project_id
        }

        try:
            # 1. Get project info
            cur.execute("""
                SELECT * FROM projects WHERE id = %s
            """, (project_id,))
            context['project'] = cur.fetchone()

            # 2. Get all characters for this project
            cur.execute("""
                SELECT c.*,
                       am.model_name as lora_name,
                       am.model_path as lora_path
                FROM characters c
                LEFT JOIN ai_models am ON am.character_name = c.name AND am.model_type = 'lora'
                WHERE c.project_id = %s
                ORDER BY c.id
            """, (project_id,))
            context['characters'] = cur.fetchall()

            # 3. Get all episodes
            cur.execute("""
                SELECT e.*,
                       COUNT(DISTINCT s.id) as scene_count
                FROM episodes e
                LEFT JOIN scenes s ON s.episode_id = e.id
                WHERE e.project_id = %s
                GROUP BY e.id, e.project_id, e.episode_number, e.title,
                         e.description, e.prompt, e.enhanced_prompt, e.status,
                         e.created_at, e.production_status
                ORDER BY e.episode_number
            """, (project_id,))
            context['episodes'] = cur.fetchall()

            # 4. Get all scenes
            cur.execute("""
                SELECT s.*,
                       e.episode_number,
                       e.title as episode_title
                FROM scenes s
                JOIN episodes e ON s.episode_id = e.id
                WHERE e.project_id = %s
                ORDER BY e.episode_number, s.scene_number
            """, (project_id,))
            context['scenes'] = cur.fetchall()

            # 5. Get generation profiles
            cur.execute("""
                SELECT gp.*,
                       checkpoint.model_name as checkpoint_name,
                       lora.model_name as lora_name
                FROM generation_profiles gp
                LEFT JOIN ai_models checkpoint ON gp.checkpoint_id = checkpoint.id
                LEFT JOIN ai_models lora ON gp.lora_id = lora.id
                WHERE gp.is_default = true OR gp.name LIKE '%%' || (
                    SELECT name FROM projects WHERE id = %s
                ) || '%%'
            """, (project_id,))
            context['generation_profiles'] = cur.fetchall()

            # 6. Get recent generation history
            cur.execute("""
                SELECT gh.*
                FROM generation_history gh
                WHERE gh.id IN (
                    SELECT id FROM generation_history
                    ORDER BY created_at DESC
                    LIMIT 10
                )
            """)
            context['recent_generations'] = cur.fetchall()

            # 7. Get workflow templates
            cur.execute("""
                SELECT name, description, frame_count, fps, width, height
                FROM video_workflow_templates
                WHERE is_active = true
            """)
            context['workflow_templates'] = cur.fetchall()

            # 8. Get project statistics
            cur.execute("""
                SELECT
                    (SELECT COUNT(*) FROM characters WHERE project_id = %s) as total_characters,
                    (SELECT COUNT(*) FROM episodes WHERE project_id = %s) as total_episodes,
                    (SELECT COUNT(*) FROM scenes s
                     JOIN episodes e ON s.episode_id = e.id
                     WHERE e.project_id = %s) as total_scenes,
                    (SELECT COUNT(*) FROM production_jobs WHERE project_id = %s) as total_generations
            """, (project_id, project_id, project_id, project_id))
            context['statistics'] = cur.fetchone()

            return context

        finally:
            conn.close()

    def format_for_echo_brain(self, context: dict) -> str:
        """Format context as a prompt for Echo Brain"""

        project = context.get('project', {})
        characters = context.get('characters', [])
        episodes = context.get('episodes', [])

        prompt = f"""
PROJECT CONTEXT FOR ANIME PRODUCTION:

Project: {project.get('name', 'Unknown')}
Description: {project.get('description', 'No description')}

CHARACTERS ({len(characters)} total):
"""

        for char in characters[:5]:  # First 5 characters
            prompt += f"""
- {char['name']}: {char.get('description', 'No description')}
  LoRA Model: {char.get('lora_name', 'None')}
"""

        prompt += f"""

EPISODES ({len(episodes)} total):
"""

        for ep in episodes[:3]:  # First 3 episodes
            prompt += f"""
- Episode {ep['episode_number']}: {ep['title']}
  Scenes: {ep['scene_count']}
  Status: {ep['production_status']}
"""

        stats = context.get('statistics', {})
        prompt += f"""

PROJECT STATISTICS:
- Total Characters: {stats.get('total_characters', 0)}
- Total Episodes: {stats.get('total_episodes', 0)}
- Total Scenes: {stats.get('total_scenes', 0)}
- Total Generations: {stats.get('total_generations', 0)}

Based on this context, please help with anime production tasks.
"""

        return prompt

    def save_context(self, project_id: int, output_file: str):
        """Extract and save context to JSON file"""

        print(f"Extracting context for project {project_id}...")
        context = self.extract_full_context(project_id)

        # Convert datetime objects to strings
        def json_serial(obj):
            if hasattr(obj, 'isoformat'):
                return obj.isoformat()
            return str(obj)

        with open(output_file, 'w') as f:
            json.dump(context, f, indent=2, default=json_serial)

        print(f"✅ Context saved to {output_file}")
        print(f"📊 Summary:")
        print(f"   - Project: {context['project']['name']}")
        print(f"   - Characters: {len(context['characters'])}")
        print(f"   - Episodes: {len(context['episodes'])}")
        print(f"   - Scenes: {len(context['scenes'])}")

        # Also create a prompt version
        prompt = self.format_for_echo_brain(context)
        prompt_file = output_file.replace('.json', '_prompt.txt')

        with open(prompt_file, 'w') as f:
            f.write(prompt)

        print(f"📝 Prompt saved to {prompt_file}")

        return context

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Extract anime project context for Echo Brain')
    parser.add_argument('--project', type=int, default=24, help='Project ID (default: 24 - Tokyo Debt Desire)')
    parser.add_argument('--output', type=str, default='/tmp/project_context.json', help='Output JSON file')

    args = parser.parse_args()

    extractor = AnimeContextExtractor()

    try:
        context = extractor.save_context(args.project, args.output)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)