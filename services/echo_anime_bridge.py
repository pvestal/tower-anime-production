#!/usr/bin/env python3
"""
Echo Brain + Anime Production Integration Bridge
Handles creative intelligence for storyline generation and management
"""

import asyncio
import json
import re
import httpx
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor

class EchoAnimeBridge:
    """
    Bridge between Echo Brain's creative intelligence and anime production database
    """

    def __init__(self):
        self.echo_url = "http://localhost:8309"
        self.db_config = {
            'host': 'localhost',
            'database': 'anime_production',
            'user': 'patrick',
            'password': '***REMOVED***'
        }
        self.current_timeline = "main"
        self.character_memory = {}

    async def generate_episode_from_concept(self, concept: str, project_id: int) -> dict:
        """
        Generate complete episode structure from high-level concept

        Args:
            concept: High-level story concept from user
            project_id: Anime project ID

        Returns:
            Episode structure ready for database insertion
        """
        # Get project context
        project_context = self._get_project_context(project_id)

        # Query Echo Brain for episode generation
        echo_response = await self._query_echo(
            f"""Create a detailed episode for an anime series with the following:

            Concept: {concept}

            Project: {project_context['name']}
            Characters: {', '.join([c['name'] for c in project_context['characters']])}
            Previous Episodes: {len(project_context['episodes'])} episodes exist
            Current Timeline: {self.current_timeline}

            Provide:
            1. Episode title
            2. Synopsis (2-3 sentences)
            3. 5-8 scenes with:
               - Location (INT/EXT)
               - Time (DAY/NIGHT)
               - Characters present
               - Action description
               - Camera direction (wide shot, close-up, etc.)
               - Mood/atmosphere
            4. Key dialogue snippets
            5. Decision points that could create timeline branches
            """,
            conversation_id=f"anime_project_{project_id}"
        )

        # Parse Echo's response into structured data
        episode_data = self._parse_episode_structure(echo_response)

        # Store in database
        episode_id = self._store_episode(project_id, episode_data)

        # Generate scene prompts
        scene_prompts = await self._generate_scene_prompts(episode_data['scenes'])

        # Store scenes with prompts
        self._store_scenes(episode_id, episode_data['scenes'], scene_prompts)

        return {
            "episode_id": episode_id,
            "title": episode_data['title'],
            "synopsis": episode_data['synopsis'],
            "scenes": len(episode_data['scenes']),
            "timeline": self.current_timeline,
            "decision_points": episode_data.get('decision_points', [])
        }

    async def create_timeline_branch(self, decision_point: str, choice: str, episode_id: str) -> dict:
        """
        Create alternate timeline based on a decision

        Args:
            decision_point: Description of the decision moment
            choice: The choice made
            episode_id: Current episode ID

        Returns:
            New timeline branch information
        """
        # Get current world state
        world_state = self._get_world_state(episode_id)

        # Ask Echo to generate consequences
        echo_response = await self._query_echo(
            f"""In our anime storyline, a critical decision was made:

            Decision Point: {decision_point}
            Choice Made: {choice}
            Current World State: {json.dumps(world_state)}

            Generate:
            1. Immediate consequences (this episode)
            2. Ripple effects (next 3 episodes)
            3. Long-term impact on characters
            4. New world state after this choice
            5. Potential future decision points
            """,
            conversation_id=f"timeline_branch_{episode_id}"
        )

        # Parse timeline changes
        timeline_data = self._parse_timeline_branch(echo_response)

        # Create new timeline branch in database
        branch_id = self._create_timeline_branch(
            parent_timeline=self.current_timeline,
            divergence_point=decision_point,
            choice=choice,
            new_world_state=timeline_data['new_world_state']
        )

        return {
            "branch_id": branch_id,
            "parent_timeline": self.current_timeline,
            "consequences": timeline_data['consequences'],
            "ripple_effects": timeline_data['ripple_effects'],
            "character_impacts": timeline_data['character_impacts']
        }

    async def maintain_character_consistency(self, character_id: int, episode_id: str) -> dict:
        """
        Ensure character remains consistent across episodes

        Args:
            character_id: Character database ID
            episode_id: Current episode

        Returns:
            Character consistency report
        """
        # Get character history
        character = self._get_character_data(character_id)
        appearances = self._get_character_appearances(character_id)

        # Ask Echo to analyze character development
        echo_response = await self._query_echo(
            f"""Analyze character consistency for {character['name']}:

            Base Traits: {character['description']}
            Physical: {character['physical_traits']}
            Appearances: {len(appearances)} episodes

            Recent Actions: {self._get_recent_actions(character_id)}

            Provide:
            1. Character growth trajectory
            2. Consistency check (are actions matching personality?)
            3. Suggested development for next episode
            4. Visual consistency notes (for generation)
            5. Key character moments to reference
            """,
            conversation_id=f"character_{character_id}"
        )

        # Parse and store character development
        consistency_data = self._parse_character_consistency(echo_response)

        # Update character memory
        self.character_memory[character_id] = consistency_data

        # Store in database
        self._update_character_consistency(character_id, consistency_data)

        return consistency_data

    async def generate_scene_prompt_from_description(self, scene_description: str, style: str = "anime") -> str:
        """
        Convert scene description to ComfyUI-ready prompt

        Args:
            scene_description: Natural language scene description
            style: Visual style (anime, realistic, etc.)

        Returns:
            ComfyUI-optimized prompt
        """
        echo_response = await self._query_echo(
            f"""Convert this scene to a visual generation prompt:

            Scene: {scene_description}
            Style: {style}

            Create a prompt with:
            1. Character descriptions (appearance, clothing, pose)
            2. Location details (setting, time of day, lighting)
            3. Camera angle (wide, close-up, aerial, etc.)
            4. Mood/atmosphere tags
            5. Technical quality tags (masterpiece, best quality, etc.)

            Format as comma-separated tags optimized for image generation.
            """,
            conversation_id="prompt_generation"
        )

        # Extract and clean prompt
        prompt = self._extract_prompt(echo_response)

        # Add style-specific tags
        if style == "anime":
            prompt += ", anime style, cel shading, vibrant colors"
        elif style == "realistic":
            prompt += ", photorealistic, high detail, cinematic lighting"

        return prompt

    def _parse_episode_structure(self, echo_response: str) -> dict:
        """Parse Echo's response into structured episode data"""
        episode = {
            "title": "",
            "synopsis": "",
            "scenes": [],
            "decision_points": []
        }

        # Extract title
        title_match = re.search(r'(?:Title|Episode \d+):\s*"?([^"\n]+)"?', echo_response, re.IGNORECASE)
        if title_match:
            episode["title"] = title_match.group(1).strip()

        # Extract synopsis
        synopsis_match = re.search(r'Synopsis:\s*([^\n]+(?:\n[^\n]+)?)', echo_response, re.IGNORECASE)
        if synopsis_match:
            episode["synopsis"] = synopsis_match.group(1).strip()

        # Extract scenes
        scene_pattern = r'(?:Scene \d+|INT\.|EXT\.)[^\n]*\n([^Scene]+?)(?=Scene \d+|INT\.|EXT\.|Decision Point|$)'
        scene_matches = re.finditer(scene_pattern, echo_response, re.MULTILINE | re.DOTALL)

        for i, match in enumerate(scene_matches, 1):
            scene_text = match.group(0)
            scene = self._parse_single_scene(scene_text, i)
            episode["scenes"].append(scene)

        # Extract decision points
        decision_pattern = r'Decision Point[^\n]*:\s*([^\n]+)'
        for match in re.finditer(decision_pattern, echo_response, re.IGNORECASE):
            episode["decision_points"].append(match.group(1).strip())

        return episode

    def _parse_single_scene(self, scene_text: str, scene_number: int) -> dict:
        """Parse individual scene from text"""
        scene = {
            "scene_number": scene_number,
            "location": "",
            "time": "DAY",
            "characters": [],
            "action": "",
            "camera": "medium shot",
            "mood": "neutral"
        }

        # Extract location (INT/EXT)
        location_match = re.search(r'(INT\.|EXT\.)([^-\n]+)', scene_text)
        if location_match:
            scene["location"] = location_match.group(2).strip()

        # Extract time
        if re.search(r'\b(NIGHT|EVENING|DUSK|DAWN)\b', scene_text, re.IGNORECASE):
            scene["time"] = "NIGHT"

        # Extract characters (look for character names in caps)
        char_pattern = r'\b([A-Z][A-Z]+(?:\s+[A-Z]+)*)\b'
        characters = re.findall(char_pattern, scene_text)
        scene["characters"] = list(set(c for c in characters if len(c) > 2))

        # Extract camera direction
        camera_match = re.search(r'(close-up|wide shot|aerial|POV|tracking shot)', scene_text, re.IGNORECASE)
        if camera_match:
            scene["camera"] = camera_match.group(1).lower()

        # Extract mood
        mood_match = re.search(r'(tense|dramatic|peaceful|action|romantic|mysterious)', scene_text, re.IGNORECASE)
        if mood_match:
            scene["mood"] = mood_match.group(1).lower()

        # Rest is action
        scene["action"] = re.sub(r'(INT\.|EXT\.)[^\n]+\n', '', scene_text).strip()[:500]

        return scene

    async def _generate_scene_prompts(self, scenes: List[dict]) -> List[str]:
        """Generate ComfyUI prompts for each scene"""
        prompts = []

        for scene in scenes:
            prompt = await self.generate_scene_prompt_from_description(
                f"{scene['action']} Location: {scene['location']}, Time: {scene['time']}, "
                f"Characters: {', '.join(scene['characters'])}, Camera: {scene['camera']}, "
                f"Mood: {scene['mood']}"
            )
            prompts.append(prompt)

        return prompts

    def _get_project_context(self, project_id: int) -> dict:
        """Get project information from database"""
        conn = psycopg2.connect(**self.db_config)
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Get project
        cur.execute("SELECT * FROM projects WHERE id = %s", (project_id,))
        project = cur.fetchone()

        # Get characters
        cur.execute("SELECT * FROM characters WHERE project_id = %s", (project_id,))
        characters = cur.fetchall()

        # Get episodes
        cur.execute("SELECT * FROM episodes WHERE project_id = %s", (project_id,))
        episodes = cur.fetchall()

        conn.close()

        return {
            "name": project['name'],
            "characters": characters,
            "episodes": episodes
        }

    def _store_episode(self, project_id: int, episode_data: dict) -> str:
        """Store episode in database"""
        conn = psycopg2.connect(**self.db_config)
        cur = conn.cursor()

        import uuid
        episode_id = str(uuid.uuid4())

        cur.execute("""
            INSERT INTO episodes (id, project_id, episode_number, title, description, status)
            VALUES (%s, %s, %s, %s, %s, 'pre-production')
            RETURNING id
        """, (episode_id, project_id,
              self._get_next_episode_number(project_id),
              episode_data['title'],
              episode_data['synopsis']))

        result = cur.fetchone()
        conn.commit()
        conn.close()

        return result[0]

    def _store_scenes(self, episode_id: str, scenes: List[dict], prompts: List[str]):
        """Store scenes in database"""
        conn = psycopg2.connect(**self.db_config)
        cur = conn.cursor()

        for scene, prompt in zip(scenes, prompts):
            import uuid
            cur.execute("""
                INSERT INTO scenes (id, episode_id, scene_number, description, prompt, status)
                VALUES (%s, %s, %s, %s, %s, 'ready')
            """, (str(uuid.uuid4()), episode_id, scene['scene_number'],
                  scene['action'][:500], prompt))

        conn.commit()
        conn.close()

    async def _query_echo(self, query: str, conversation_id: str = None) -> str:
        """Query Echo Brain API"""
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.echo_url}/api/echo/query",
                json={
                    "query": query,
                    "conversation_id": conversation_id or "anime_bridge",
                    "temperature": 0.8
                }
            )

            if response.status_code == 200:
                data = response.json()
                return data.get("response", "")
            else:
                return f"Echo Brain error: {response.status_code}"

    def _get_next_episode_number(self, project_id: int) -> int:
        """Get next episode number for project"""
        conn = psycopg2.connect(**self.db_config)
        cur = conn.cursor()
        cur.execute(
            "SELECT MAX(episode_number) FROM episodes WHERE project_id = %s",
            (project_id,)
        )
        result = cur.fetchone()
        conn.close()
        return (result[0] or 0) + 1

# API Integration Functions
async def generate_episode_with_echo(project_id: int, concept: str):
    """Generate episode using Echo Brain"""
    bridge = EchoAnimeBridge()
    return await bridge.generate_episode_from_concept(concept, project_id)

async def create_timeline_branch_with_echo(decision: str, choice: str, episode_id: str):
    """Create timeline branch using Echo Brain"""
    bridge = EchoAnimeBridge()
    return await bridge.create_timeline_branch(decision, choice, episode_id)

async def check_character_consistency(character_id: int, episode_id: str):
    """Check character consistency using Echo Brain"""
    bridge = EchoAnimeBridge()
    return await bridge.maintain_character_consistency(character_id, episode_id)

async def generate_scene_prompt(description: str, style: str = "anime"):
    """Generate ComfyUI prompt from description"""
    bridge = EchoAnimeBridge()
    return await bridge.generate_scene_prompt_from_description(description, style)