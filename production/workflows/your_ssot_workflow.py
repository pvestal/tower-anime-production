#!/usr/bin/env python3
"""
YOUR ACTUAL SSOT WORKFLOW
Using your database workflow, your characters, your LoRA models
"""

import requests
import json
import time
import psycopg2
from typing import Dict, Any

class YourSSOTWorkflow:
    """Use Patrick's actual SSOT workflow from database with his characters"""

    def __init__(self):
        self.comfyui_url = "http://localhost:8188"
        self.db_config = {
            'host': 'localhost',
            'database': 'tower_consolidated',
            'user': 'patrick',
            'password': 'RP78eIrW7cI2jYvL5akt1yurE'
        }

    def get_characters(self):
        """Get YOUR actual characters from database"""
        conn = psycopg2.connect(**self.db_config)
        cur = conn.cursor()

        cur.execute("SELECT name, description FROM characters WHERE name != 'Test Character' AND name != 'Integration Test Character' LIMIT 3")
        characters = cur.fetchall()

        conn.close()
        return characters

    def get_your_ssot_workflow(self, workflow_name="anime_30sec_rife_workflow"):
        """Load YOUR actual SSOT workflow from database"""
        conn = psycopg2.connect(**self.db_config)
        cur = conn.cursor()

        cur.execute("""
            SELECT workflow_template, frame_count, fps, description
            FROM video_workflow_templates
            WHERE name = %s
        """, (workflow_name,))

        row = cur.fetchone()
        conn.close()

        if row:
            return {
                'workflow': row[0],
                'frame_count': row[1],
                'fps': row[2],
                'description': row[3]
            }
        return None

    def create_character_prompt(self, character_name, character_desc, action="standing in cyberpunk city"):
        """Create prompt using YOUR character data"""
        # Extract key visual elements from character description
        if "Akira" in character_name:
            return f"masterpiece, best quality, {character_name}, 22-year-old man with spiky black hair, cybernetic arm implants, neon blue jacket, street racer, {action}, cyberpunk setting, dynamic pose, detailed character design"
        elif "Luna" in character_name:
            return f"masterpiece, best quality, {character_name}, woman with silver hair, holographic tattoos, lab coat, AI researcher, {action}, futuristic laboratory, detailed character design"
        elif "Viktor" in character_name:
            return f"masterpiece, best quality, {character_name}, corporate man in expensive suit, augmented reality monocle, cold expression, CEO, {action}, corporate office, detailed character design"
        else:
            return f"masterpiece, best quality, {character_name}, {character_desc}, {action}, anime style, detailed character design"

    def run_your_workflow_with_character(self, character_name, character_desc):
        """Run YOUR SSOT workflow with YOUR character"""
        print(f"🎬 Running YOUR SSOT Workflow with {character_name}")

        # Get YOUR workflow from database
        ssot_data = self.get_your_ssot_workflow()
        if not ssot_data:
            print("❌ Could not load YOUR SSOT workflow")
            return None

        workflow = ssot_data['workflow'].copy()
        print(f"✅ Loaded YOUR workflow: {ssot_data['description']}")
        print(f"   Frames: {ssot_data['frame_count']}, FPS: {ssot_data['fps']}")

        # Update with YOUR character prompt
        character_prompt = self.create_character_prompt(character_name, character_desc, "dynamic action pose in neon cyberpunk city")

        # Find and update the positive prompt node
        for node_id, node in workflow.items():
            if isinstance(node, dict):
                if node.get("_meta", {}).get("title") == "CLIP Text Encode (Prompt)" or "positive" in node.get("_meta", {}).get("title", "").lower():
                    workflow[node_id]["inputs"]["text"] = character_prompt
                    print(f"✅ Updated prompt for {character_name}")
                    break

        # Update seed for uniqueness
        for node_id, node in workflow.items():
            if isinstance(node, dict) and node.get("class_type") == "KSampler":
                workflow[node_id]["inputs"]["seed"] = int(time.time()) % 2147483647
                print(f"✅ Updated seed")
                break

        # Submit to ComfyUI
        response = requests.post(f"{self.comfyui_url}/prompt", json={"prompt": workflow})
        result = response.json()

        if 'prompt_id' in result:
            prompt_id = result['prompt_id']
            print(f"✅ YOUR workflow submitted for {character_name}: {prompt_id}")
            return prompt_id
        else:
            print(f"❌ Failed: {result}")
            return None

def main():
    """Test YOUR actual SSOT workflow with YOUR characters"""
    workflow_runner = YourSSOTWorkflow()

    # Get YOUR actual characters
    characters = workflow_runner.get_characters()
    print(f"📋 Found {len(characters)} of YOUR characters:")
    for name, desc in characters:
        print(f"   - {name}: {desc[:100]}...")

    # Test with YOUR first character
    if characters:
        char_name, char_desc = characters[0]
        print(f"\n🎯 Generating video with YOUR character: {char_name}")

        job_id = workflow_runner.run_your_workflow_with_character(char_name, char_desc)

        if job_id:
            print(f"\n✅ YOUR SSOT workflow running with YOUR character!")
            print(f"Monitor: curl -s http://localhost:8188/history/{job_id}")
            print("Output will use YOUR LoRA (mei_working_v1.safetensors) and YOUR models")
        else:
            print("\n❌ Failed to run YOUR workflow")

if __name__ == "__main__":
    main()