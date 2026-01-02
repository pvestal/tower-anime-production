#!/usr/bin/env python3
"""
Echo Brain JSON Bridge
Ensures Echo outputs structured JSON for anime production
"""

import json
import httpx
import asyncio
from typing import Dict, Any

class EchoJSONBridge:
    """Bridge that enforces JSON output from Echo Brain"""

    def __init__(self):
        self.echo_url = "http://localhost:8309"
        self.system_prompt = """You are an anime story generator.
ALWAYS respond with valid JSON matching this exact schema:
{
  "episode": {
    "title": string,
    "number": int,
    "synopsis": string
  },
  "scenes": [
    {
      "order": int,
      "location": string (INT/EXT),
      "time": string (DAY/NIGHT),
      "characters": [string],
      "action": string,
      "mood": string,
      "camera": string,
      "comfyui_prompt": string
    }
  ],
  "decision_points": [
    {
      "scene_order": int,
      "choice": string,
      "consequences": [string]
    }
  ]
}

NEVER include any text outside the JSON structure.
Generate exactly 5-8 scenes per episode.
Each comfyui_prompt should be detailed tags for image generation."""

    async def generate_episode_json(self, concept: str, project_context: dict = None) -> dict:
        """Generate episode with guaranteed JSON output"""

        # Build the full prompt with context
        prompt = f"""{self.system_prompt}

Project: {project_context.get('project_name', 'Anime Project')}
Characters Available: {', '.join([c['name'] for c in project_context.get('characters', [])])}

User Request: {concept}

Generate the episode structure as JSON:"""

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.echo_url}/api/echo/chat",
                json={
                    "query": prompt,
                    "conversation_id": f"anime_json_{project_context.get('project_id', 1)}",
                    "temperature": 0.7  # Lower temperature for more structured output
                }
            )

            if response.status_code == 200:
                data = response.json()
                echo_response = data.get("response", "")

                # Try to extract JSON from response
                try:
                    # Find JSON in response (in case Echo adds text around it)
                    start = echo_response.find('{')
                    end = echo_response.rfind('}') + 1
                    if start >= 0 and end > start:
                        json_str = echo_response[start:end]
                        return json.loads(json_str)
                    else:
                        # Fallback: create structure from prose
                        return self._parse_prose_to_json(echo_response)
                except json.JSONDecodeError:
                    return self._parse_prose_to_json(echo_response)
            else:
                raise Exception(f"Echo Brain error: {response.status_code}")

    def _parse_prose_to_json(self, prose: str) -> dict:
        """Fallback parser if Echo doesn't output clean JSON"""

        import re

        # Default structure
        result = {
            "episode": {
                "title": "Generated Episode",
                "number": 1,
                "synopsis": ""
            },
            "scenes": [],
            "decision_points": []
        }

        # Try to extract title
        title_match = re.search(r'(?:Title|Episode):\s*"?([^"\n]+)"?', prose, re.IGNORECASE)
        if title_match:
            result["episode"]["title"] = title_match.group(1).strip()

        # Extract synopsis
        synopsis_match = re.search(r'Synopsis:\s*([^\n]+)', prose, re.IGNORECASE)
        if synopsis_match:
            result["episode"]["synopsis"] = synopsis_match.group(1).strip()

        # Extract scenes
        scene_blocks = re.split(r'Scene \d+:', prose, flags=re.IGNORECASE)

        for i, block in enumerate(scene_blocks[1:], 1):  # Skip first empty block
            scene = {
                "order": i,
                "location": "INT" if "INT" in block.upper() else "EXT",
                "time": "NIGHT" if "NIGHT" in block.upper() else "DAY",
                "characters": [],
                "action": block[:200].strip(),
                "mood": "dramatic",
                "camera": "medium shot",
                "comfyui_prompt": ""
            }

            # Extract character names (words in all caps)
            characters = re.findall(r'\b([A-Z][A-Z]+(?:\s+[A-Z]+)*)\b', block)
            scene["characters"] = list(set(c for c in characters if len(c) > 2))[:3]

            # Generate ComfyUI prompt
            scene["comfyui_prompt"] = self._generate_prompt_from_scene(scene)

            result["scenes"].append(scene)

        return result

    def _generate_prompt_from_scene(self, scene: dict) -> str:
        """Generate ComfyUI prompt from scene data"""

        prompt_parts = []

        # Add characters
        if scene["characters"]:
            for char in scene["characters"]:
                prompt_parts.append(char.lower())

        # Add location and time
        prompt_parts.extend([
            f"{scene['location'].lower()} location",
            f"{scene['time'].lower()} time",
            scene["mood"] + " mood",
            scene["camera"]
        ])

        # Add quality tags
        prompt_parts.extend([
            "anime style",
            "high quality",
            "detailed",
            "cinematic lighting"
        ])

        return ", ".join(prompt_parts)

    async def test_json_generation(self):
        """Test JSON generation with a sample concept"""

        concept = "Kai infiltrates a corporate building to rescue victims"

        context = {
            "project_name": "Cyberpunk Goblin Slayer",
            "project_id": 29,
            "characters": [
                {"name": "Kai Nakamura"},
                {"name": "Goblin Boss"}
            ]
        }

        print("Testing JSON generation...")
        result = await self.generate_episode_json(concept, context)

        print("\n✅ Generated JSON Structure:")
        print(json.dumps(result, indent=2))

        return result

# Direct integration with database
def store_json_episode(episode_json: dict, project_id: int):
    """Store JSON episode structure in database"""

    import psycopg2
    import uuid

    db_config = {
        'host': 'localhost',
        'database': 'anime_production',
        'user': 'patrick',
        'password': '***REMOVED***'
    }

    conn = psycopg2.connect(**db_config)
    cur = conn.cursor()

    try:
        # Store episode
        episode_id = str(uuid.uuid4())
        cur.execute("""
            INSERT INTO episodes (id, project_id, episode_number, title, description, status)
            VALUES (%s, %s, %s, %s, %s, 'pre-production')
            RETURNING id
        """, (
            episode_id,
            project_id,
            episode_json["episode"]["number"],
            episode_json["episode"]["title"],
            episode_json["episode"]["synopsis"]
        ))

        # Store scenes
        for scene in episode_json["scenes"]:
            scene_id = str(uuid.uuid4())
            cur.execute("""
                INSERT INTO scenes (
                    id, episode_id, scene_number, prompt,
                    description, status, project_id
                )
                VALUES (%s, %s, %s, %s, %s, 'ready', %s)
            """, (
                scene_id,
                episode_id,
                scene["order"],
                scene["comfyui_prompt"],
                scene["action"],
                project_id
            ))

        # Store decision points if any
        for dp in episode_json.get("decision_points", []):
            cur.execute("""
                INSERT INTO decision_points (
                    episode_id, decision_description, choices, impact_level
                )
                VALUES (%s, %s, %s, 'major')
            """, (
                episode_id,
                dp["choice"],
                json.dumps(dp["consequences"])
            ))

        conn.commit()
        print(f"✅ Episode stored: {episode_id}")
        return episode_id

    except Exception as e:
        conn.rollback()
        print(f"❌ Error storing episode: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    # Test the JSON bridge
    bridge = EchoJSONBridge()
    asyncio.run(bridge.test_json_generation())