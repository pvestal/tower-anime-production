#!/usr/bin/env python3
"""
Dynamic Context-Aware Prompt System
Learns from failures and adaptively improves generation quality
"""

import json
import sqlite3
import logging
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from datetime import datetime
import hashlib
import random

logger = logging.getLogger(__name__)

class DynamicPromptSystem:
    """Adaptive prompt system that learns from context and failures"""

    def __init__(self, db_path: str = "/opt/tower-anime-production/dynamic_prompts.db"):
        self.db_path = db_path
        self.init_database()

        # Base character templates from project files
        self.character_base_templates = {}
        self.load_character_templates()

        # Dynamic enhancement rules
        self.solo_enhancers = [
            "((solo))", "((1girl))", "((single person))", "((only one person))",
            "((individual))", "((isolated))", "portrait", "close up"
        ]

        self.solo_mega_negatives = [
            "((multiple people))", "((2girls))", "((3girls))", "((twins))",
            "((duplicates))", "((clones))", "((group))", "((crowd))",
            "((siblings))", "multiple heads", "multiple faces", "extra person",
            "second person", "background people", "other people", "additional person"
        ]

        # Context-aware parameter adjustments
        self.solo_params = {
            "cfg": 8.5,  # Higher CFG for precise adherence
            "steps": 35,  # More steps for quality
            "width": 768,  # Portrait aspect ratio
            "height": 1024,
            "sampler": "dpmpp_2m"
        }

    def init_database(self):
        """Initialize learning database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Prompt success tracking
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS prompt_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                character_name TEXT NOT NULL,
                base_prompt TEXT NOT NULL,
                enhanced_prompt TEXT NOT NULL,
                parameters TEXT NOT NULL,
                success BOOLEAN NOT NULL,
                detected_faces INTEGER,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                failure_reason TEXT,
                image_path TEXT
            )
        ''')

        # Character-specific learning
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS character_learnings (
                character_name TEXT PRIMARY KEY,
                successful_prompts TEXT,  -- JSON array
                failed_prompts TEXT,      -- JSON array
                best_parameters TEXT,     -- JSON object
                enhancement_patterns TEXT, -- JSON array
                last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Dynamic enhancement rules
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS enhancement_rules (
                rule_id TEXT PRIMARY KEY,
                trigger_context TEXT,
                enhancement TEXT,
                success_rate REAL DEFAULT 0.5,
                usage_count INTEGER DEFAULT 0,
                last_used DATETIME
            )
        ''')

        conn.commit()
        conn.close()

    def load_character_templates(self):
        """Load base character templates from project files"""
        characters_dir = Path("/opt/tower-anime-production/workflows/projects/tokyo_debt_desire/characters")

        if characters_dir.exists():
            for char_file in characters_dir.glob("*.json"):
                try:
                    with open(char_file) as f:
                        char_data = json.load(f)
                        char_name = char_data.get('name', char_file.stem)
                        self.character_base_templates[char_name] = char_data
                        logger.info(f"Loaded template for {char_name}")
                except Exception as e:
                    logger.error(f"Failed to load character template {char_file}: {e}")

    def build_dynamic_prompt(self, character_name: str, scene_context: str = "portrait",
                           previous_failures: List[Dict] = None) -> Dict:
        """Build context-aware prompt with learning from failures"""

        # Get base character data
        char_template = self.character_base_templates.get(character_name, {})
        base_prompt = char_template.get('generation_prompts', {}).get('visual_description', '')

        # Analyze previous failures
        failure_patterns = self.analyze_failure_patterns(character_name, previous_failures or [])

        # Build enhanced prompt
        enhanced_prompt = self.enhance_prompt_dynamically(
            base_prompt, character_name, scene_context, failure_patterns
        )

        # Get adaptive parameters
        parameters = self.get_adaptive_parameters(character_name, scene_context, failure_patterns)

        # Generate unique prompt ID for tracking
        prompt_hash = hashlib.md5(
            f"{character_name}_{enhanced_prompt}_{json.dumps(parameters)}".encode()
        ).hexdigest()[:8]

        return {
            'prompt_id': prompt_hash,
            'character_name': character_name,
            'base_prompt': base_prompt,
            'enhanced_prompt': enhanced_prompt,
            'negative_prompt': self.build_context_negative(scene_context, failure_patterns),
            'parameters': parameters,
            'generation_strategy': self.get_generation_strategy(failure_patterns),
            'expected_result': self.define_success_criteria(character_name, scene_context)
        }

    def enhance_prompt_dynamically(self, base_prompt: str, character_name: str,
                                 scene_context: str, failure_patterns: Dict) -> str:
        """Dynamically enhance prompt based on context and learned patterns"""

        enhanced = base_prompt

        # Character-specific learned enhancements
        learned_enhancements = self.get_character_learnings(character_name)
        for enhancement in learned_enhancements.get('successful_patterns', []):
            if enhancement not in enhanced:
                enhanced += f", {enhancement}"

        # Context-specific enhancements
        if scene_context == "portrait" or "solo" in base_prompt:
            # Ultra-aggressive solo enforcement
            for enhancer in self.solo_enhancers[:3]:  # Use top 3 most effective
                if enhancer not in enhanced:
                    enhanced = f"{enhancer}, {enhanced}"

            # Add quality enhancers
            quality_tags = [
                "perfect anatomy", "correct proportions", "detailed hands",
                "realistic body proportions", "professional photography",
                "extremely detailed", "8k uhd", "dslr", "soft lighting",
                "high quality", "film grain", "Fujifilm XT3"
            ]
            enhanced += f", {', '.join(quality_tags)}"

        # Failure-specific corrections
        if failure_patterns.get('multiple_people_detected', 0) > 2:
            # Very aggressive single person enforcement
            enhanced = f"((((solo)))), ((((1girl)))), ((((single person)))), {enhanced}"

        if failure_patterns.get('anatomy_issues', 0) > 1:
            enhanced += ", perfect hands, perfect face, correct anatomy, no deformities"

        return enhanced

    def build_context_negative(self, scene_context: str, failure_patterns: Dict) -> str:
        """Build dynamic negative prompts based on context and failures"""

        negatives = [
            "bad quality", "blurry", "deformed", "ugly", "low resolution",
            "watermark", "text", "logo", "cartoon", "3d", "anime style",
            "sketch", "drawing", "painting", "illustration"
        ]

        # Solo scene negatives
        if scene_context == "portrait" or scene_context == "solo":
            negatives.extend(self.solo_mega_negatives)

        # Failure-specific negatives
        if failure_patterns.get('multiple_people_detected', 0) > 1:
            negatives.extend([
                "((((multiple people))))", "((((group))))", "((((twins))))",
                "((((duplicates))))", "reflection", "mirror", "clone"
            ])

        if failure_patterns.get('anatomy_issues', 0) > 1:
            negatives.extend([
                "bad anatomy", "bad hands", "deformed hands", "extra fingers",
                "missing fingers", "fused fingers", "bad proportions",
                "distorted face", "malformed"
            ])

        return ", ".join(negatives)

    def get_adaptive_parameters(self, character_name: str, scene_context: str,
                              failure_patterns: Dict) -> Dict:
        """Get context-aware generation parameters"""

        # Start with base parameters
        params = self.solo_params.copy()

        # Character-specific adjustments
        char_learnings = self.get_character_learnings(character_name)
        if char_learnings.get('best_parameters'):
            params.update(char_learnings['best_parameters'])

        # Failure-pattern adjustments
        if failure_patterns.get('multiple_people_detected', 0) > 2:
            params['cfg'] = min(params['cfg'] + 1.0, 10.0)  # Increase CFG for better adherence
            params['steps'] = min(params['steps'] + 5, 40)   # More steps for precision

        # Random seed for variety unless we have a proven successful seed
        params['seed'] = random.randint(100000, 999999)

        return params

    def analyze_failure_patterns(self, character_name: str, recent_failures: List[Dict]) -> Dict:
        """Analyze patterns in recent failures"""
        patterns = {
            'multiple_people_detected': 0,
            'anatomy_issues': 0,
            'quality_issues': 0,
            'total_attempts': len(recent_failures)
        }

        for failure in recent_failures:
            if 'multiple people' in failure.get('reason', '').lower():
                patterns['multiple_people_detected'] += 1
            if 'anatomy' in failure.get('reason', '').lower():
                patterns['anatomy_issues'] += 1
            if 'quality' in failure.get('reason', '').lower():
                patterns['quality_issues'] += 1

        return patterns

    def get_character_learnings(self, character_name: str) -> Dict:
        """Get learned patterns for specific character"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT successful_prompts, failed_prompts, best_parameters, enhancement_patterns
            FROM character_learnings WHERE character_name = ?
        ''', (character_name,))

        result = cursor.fetchone()
        conn.close()

        if result:
            return {
                'successful_patterns': json.loads(result[0] or '[]'),
                'failed_patterns': json.loads(result[1] or '[]'),
                'best_parameters': json.loads(result[2] or '{}'),
                'enhancement_patterns': json.loads(result[3] or '[]')
            }

        return {'successful_patterns': [], 'failed_patterns': [], 'best_parameters': {}, 'enhancement_patterns': []}

    def get_generation_strategy(self, failure_patterns: Dict) -> str:
        """Determine generation strategy based on failure patterns"""
        if failure_patterns['multiple_people_detected'] > 2:
            return "ULTRA_SOLO_ENFORCEMENT"
        elif failure_patterns['anatomy_issues'] > 1:
            return "ANATOMY_FOCUSED"
        elif failure_patterns['total_attempts'] > 3:
            return "PARAMETER_VARIATION"
        else:
            return "STANDARD_ENHANCED"

    def define_success_criteria(self, character_name: str, scene_context: str) -> Dict:
        """Define what success looks like for this generation"""
        return {
            'expected_faces': 1 if scene_context in ['portrait', 'solo'] else None,
            'max_acceptable_faces': 1 if scene_context in ['portrait', 'solo'] else 3,
            'required_quality_score': 7.0,
            'character_consistency_required': True
        }

    def record_result(self, prompt_data: Dict, success: bool, detected_faces: int = 0,
                     failure_reason: str = None, image_path: str = None):
        """Record generation result for learning"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO prompt_results
            (character_name, base_prompt, enhanced_prompt, parameters, success,
             detected_faces, failure_reason, image_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            prompt_data['character_name'],
            prompt_data['base_prompt'],
            prompt_data['enhanced_prompt'],
            json.dumps(prompt_data['parameters']),
            success,
            detected_faces,
            failure_reason,
            image_path
        ))

        conn.commit()
        conn.close()

        # Update character learnings
        if success:
            self.update_character_learnings(prompt_data, success=True)

def test_dynamic_prompts():
    """Test the dynamic prompt system"""
    dps = DynamicPromptSystem()

    # Simulate previous failures
    previous_failures = [
        {'reason': 'multiple people detected', 'detected_faces': 2},
        {'reason': 'multiple people detected', 'detected_faces': 3},
        {'reason': 'anatomy issues with hands', 'detected_faces': 1}
    ]

    print("=== Dynamic Prompt System Test ===")

    # Test for Yuki with failure history
    yuki_prompt = dps.build_dynamic_prompt(
        "Yuki Tanaka", "portrait", previous_failures
    )

    print(f"\nCharacter: Yuki Tanaka")
    print(f"Strategy: {yuki_prompt['generation_strategy']}")
    print(f"Enhanced Prompt: {yuki_prompt['enhanced_prompt'][:200]}...")
    print(f"Parameters: {json.dumps(yuki_prompt['parameters'], indent=2)}")
    print(f"Success Criteria: {yuki_prompt['expected_result']}")

if __name__ == "__main__":
    test_dynamic_prompts()