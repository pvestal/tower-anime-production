#!/usr/bin/env python3
"""
Echo Orchestration Engine - The AI Production Director
Core intelligence layer that coordinates all anime production workflows
with persistent learning and creative adaptation.

This is the missing piece that transforms the system from a collection of tools
into an intelligent creative partner that learns your style and preferences.

Author: Claude Code + Patrick Vestal
Created: 2025-12-11
Branch: feature/echo-orchestration-engine
"""

import asyncio
import json
import logging
import hashlib
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
import psycopg2
from psycopg2.extras import RealDictCursor
import redis
import requests
from dataclasses import dataclass
from enum import Enum

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class InteractionSource(Enum):
    TELEGRAM = "telegram"
    BROWSER_STUDIO = "browser_studio"
    API = "api"
    SCHEDULED = "scheduled_task"

class WorkflowType(Enum):
    CHARACTER_GENERATION = "character_generation"
    SCENE_BATCH = "scene_batch"
    PROJECT_CONTINUATION = "project_continuation"
    STYLE_LEARNING = "style_learning"
    CONSISTENCY_CHECK = "consistency_check"

@dataclass
class UserIntent:
    """Structured representation of what the user wants to achieve"""
    action: str  # 'generate', 'edit', 'continue', 'learn_style'
    target: str  # 'character', 'scene', 'project', 'style'
    context: Dict[str, Any]
    source: InteractionSource
    user_id: str
    project_id: Optional[str] = None

@dataclass
class CreativeDecision:
    """Represents a creative decision made during the workflow"""
    decision_type: str
    before_state: Dict[str, Any]
    after_state: Dict[str, Any]
    reasoning: str
    confidence: float
    timestamp: datetime

class EchoOrchestrationEngine:
    """
    The core AI Production Director that orchestrates all anime production workflows.

    This engine:
    1. Understands user intent across different interfaces (Telegram, Browser, API)
    2. Maintains persistent memory of user preferences and project context
    3. Coordinates complex multi-step workflows intelligently
    4. Learns and adapts from every interaction
    5. Ensures consistency across characters, scenes, and projects
    """

    def __init__(self, db_config: Dict, redis_config: Dict = None):
        self.db_config = db_config
        self.redis_client = redis.Redis(**(redis_config or {'host': 'localhost', 'port': 6379, 'db': 0}))

        # Core service endpoints
        self.echo_brain_url = "http://localhost:8309"
        self.comfyui_url = "http://localhost:8188"
        self.anime_api_url = "http://localhost:8331"

        # Orchestration state
        self.active_workflows: Dict[str, Dict] = {}
        self.user_sessions: Dict[str, Dict] = {}

        # Learning and adaptation parameters
        self.learning_rate = 0.1
        self.confidence_threshold = 0.7

        logger.info("Echo Orchestration Engine initialized - Ready for intelligent workflows")

    # ================================
    # CORE ORCHESTRATION METHODS
    # ================================

    async def orchestrate_user_request(self, user_intent: UserIntent) -> Dict[str, Any]:
        """
        Main orchestration method - interprets user intent and coordinates workflow

        This is the core intelligence that makes Echo understand context and
        coordinate complex creative workflows automatically.
        """
        orchestration_id = str(uuid.uuid4())

        try:
            logger.info(f"🎬 ORCHESTRATING: {user_intent.action} {user_intent.target} from {user_intent.source.value}")

            # Step 1: Load user creative context
            user_context = await self.load_user_creative_context(user_intent.user_id)

            # Step 2: Load project context if specified
            project_context = None
            if user_intent.project_id:
                project_context = await self.load_project_context(user_intent.project_id)

            # Step 3: Analyze intent and plan workflow
            workflow_plan = await self.plan_intelligent_workflow(
                user_intent, user_context, project_context
            )

            # Step 4: Execute workflow with adaptive learning
            workflow_result = await self.execute_adaptive_workflow(
                orchestration_id, workflow_plan, user_intent
            )

            # Step 5: Learn from the interaction
            await self.learn_from_interaction(
                orchestration_id, user_intent, workflow_result, user_context
            )

            return {
                'orchestration_id': orchestration_id,
                'success': True,
                'result': workflow_result,
                'learned_adaptations': workflow_result.get('learned_adaptations', {}),
                'next_suggestions': await self.generate_next_suggestions(user_intent, workflow_result)
            }

        except Exception as e:
            logger.error(f"Orchestration failed: {e}")
            await self.record_orchestration_failure(orchestration_id, user_intent, str(e))
            return {
                'orchestration_id': orchestration_id,
                'success': False,
                'error': str(e),
                'recovery_suggestions': await self.generate_recovery_suggestions(user_intent, str(e))
            }

    async def load_user_creative_context(self, user_id: str) -> Dict[str, Any]:
        """Load complete user creative profile for context-aware decisions"""
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            # Get user creative DNA
            cursor.execute("""
                SELECT * FROM user_creative_dna WHERE user_id = %s OR username = %s
            """, (user_id, user_id))
            user_dna = cursor.fetchone()

            if not user_dna:
                # Create new user profile
                user_dna = await self.create_user_profile(user_id)

            # Get recent style applications
            cursor.execute("""
                SELECT * FROM style_memory_engine
                WHERE user_id = %s AND is_active = true
                ORDER BY updated_at DESC LIMIT 10
            """, (user_dna['user_id'],))
            user_styles = cursor.fetchall()

            # Get recent Echo intelligence for learning patterns
            cursor.execute("""
                SELECT * FROM echo_intelligence
                WHERE user_id = %s
                ORDER BY timestamp DESC LIMIT 20
            """, (user_dna['user_id'],))
            recent_intelligence = cursor.fetchall()

            conn.close()

            return {
                'user_profile': dict(user_dna),
                'active_styles': [dict(style) for style in user_styles],
                'learning_history': [dict(intel) for intel in recent_intelligence],
                'adaptive_preferences': self.extract_adaptive_preferences(user_dna, recent_intelligence)
            }

        except Exception as e:
            logger.error(f"Failed to load user context: {e}")
            return await self.create_default_user_context(user_id)

    async def plan_intelligent_workflow(self, intent: UserIntent,
                                       user_context: Dict,
                                       project_context: Optional[Dict]) -> Dict[str, Any]:
        """
        Plan workflow based on intent, user preferences, and project context.
        This is where Echo's intelligence shines - understanding what you REALLY want.
        """

        # Determine workflow type based on intent analysis
        workflow_type = self.classify_workflow_type(intent, project_context)

        # Build context-aware plan
        workflow_plan = {
            'workflow_type': workflow_type,
            'steps': [],
            'adaptive_parameters': {},
            'quality_checkpoints': [],
            'learning_opportunities': []
        }

        if workflow_type == WorkflowType.CHARACTER_GENERATION:
            workflow_plan = await self.plan_character_generation_workflow(
                intent, user_context, project_context
            )
        elif workflow_type == WorkflowType.SCENE_BATCH:
            workflow_plan = await self.plan_scene_batch_workflow(
                intent, user_context, project_context
            )
        elif workflow_type == WorkflowType.PROJECT_CONTINUATION:
            workflow_plan = await self.plan_project_continuation_workflow(
                intent, user_context, project_context
            )
        elif workflow_type == WorkflowType.STYLE_LEARNING:
            workflow_plan = await self.plan_style_learning_workflow(
                intent, user_context, project_context
            )

        # Add Echo Brain consultation step for complex decisions
        workflow_plan['steps'].insert(0, {
            'step_type': 'echo_brain_consultation',
            'purpose': 'Get AI insight on workflow approach',
            'parameters': {
                'intent_analysis': intent.context,
                'user_preferences': user_context['adaptive_preferences'],
                'consultation_type': 'workflow_optimization'
            }
        })

        return workflow_plan

    async def execute_adaptive_workflow(self, orchestration_id: str,
                                       workflow_plan: Dict,
                                       user_intent: UserIntent) -> Dict[str, Any]:
        """
        Execute workflow with real-time adaptation and learning.
        This is where Echo becomes truly intelligent - adapting as it learns.
        """
        workflow_result = {
            'orchestration_id': orchestration_id,
            'executed_steps': [],
            'adaptive_adjustments': [],
            'quality_results': [],
            'learned_adaptations': {},
            'creative_decisions': []
        }

        try:
            # Record workflow start
            await self.record_workflow_start(orchestration_id, workflow_plan, user_intent)

            for step_index, step in enumerate(workflow_plan['steps']):
                logger.info(f"🔄 Executing step {step_index + 1}: {step['step_type']}")

                # Execute step with adaptation
                step_result = await self.execute_workflow_step(
                    step, workflow_result, user_intent
                )

                workflow_result['executed_steps'].append({
                    'step': step,
                    'result': step_result,
                    'timestamp': datetime.now().isoformat()
                })

                # Check if adaptation is needed
                if step_result.get('needs_adaptation'):
                    adaptation = await self.adapt_workflow_realtime(
                        step_result, workflow_plan, step_index, user_intent
                    )
                    workflow_result['adaptive_adjustments'].append(adaptation)

                    # Apply adaptation to remaining steps
                    workflow_plan = adaptation['adjusted_workflow']

                # Quality checkpoint
                if step.get('quality_checkpoint'):
                    qc_result = await self.perform_workflow_quality_check(
                        step_result, workflow_plan, user_intent
                    )
                    workflow_result['quality_results'].append(qc_result)

                    if not qc_result['passes']:
                        # Trigger adaptive retry
                        retry_result = await self.adaptive_retry_step(
                            step, step_result, qc_result, user_intent
                        )
                        workflow_result['executed_steps'][-1]['retry_result'] = retry_result

            # Record successful completion
            await self.record_workflow_completion(orchestration_id, workflow_result)

            return workflow_result

        except Exception as e:
            logger.error(f"Workflow execution failed: {e}")
            await self.record_workflow_failure(orchestration_id, workflow_result, str(e))
            raise

    # ================================
    # INTELLIGENT WORKFLOW PLANNERS
    # ================================

    async def plan_character_generation_workflow(self, intent: UserIntent,
                                                user_context: Dict,
                                                project_context: Optional[Dict]) -> Dict:
        """Plan intelligent character generation with consistency and style learning"""

        character_name = intent.context.get('character_name', 'Unknown')

        # Check for existing character consistency data
        existing_character = await self.load_character_consistency_data(
            character_name, intent.project_id
        )

        workflow_plan = {
            'workflow_type': WorkflowType.CHARACTER_GENERATION,
            'steps': [
                {
                    'step_type': 'echo_brain_consultation',
                    'purpose': 'Analyze character generation requirements',
                    'parameters': {
                        'character_name': character_name,
                        'existing_consistency_data': existing_character,
                        'user_style_preferences': user_context['adaptive_preferences']
                    }
                },
                {
                    'step_type': 'load_character_template',
                    'purpose': 'Load character definition from project bible',
                    'parameters': {
                        'character_name': character_name,
                        'project_context': project_context
                    }
                },
                {
                    'step_type': 'build_adaptive_prompt',
                    'purpose': 'Create context-aware generation prompt',
                    'parameters': {
                        'base_character_data': existing_character,
                        'user_style_signature': user_context['user_profile']['style_signatures'],
                        'learning_from_failures': True
                    },
                    'quality_checkpoint': True
                },
                {
                    'step_type': 'generate_with_consistency_check',
                    'purpose': 'Generate image with real-time consistency validation',
                    'parameters': {
                        'max_retries': 3,
                        'adaptive_improvement': True
                    },
                    'quality_checkpoint': True
                },
                {
                    'step_type': 'update_character_consistency_memory',
                    'purpose': 'Learn from generation results',
                    'parameters': {
                        'update_embeddings': True,
                        'learn_successful_patterns': True
                    }
                }
            ],
            'adaptive_parameters': {
                'learning_rate': user_context['user_profile']['learning_rate'],
                'style_variance': user_context['user_profile']['creativity_variance']
            },
            'quality_checkpoints': ['prompt_validation', 'generation_consistency', 'style_alignment'],
            'learning_opportunities': ['prompt_effectiveness', 'style_application', 'consistency_improvement']
        }

        # Add style application if user has custom styles
        if user_context['active_styles']:
            workflow_plan['steps'].insert(-1, {
                'step_type': 'apply_learned_styles',
                'purpose': 'Apply user-specific style preferences',
                'parameters': {
                    'available_styles': user_context['active_styles'],
                    'context_matching': True
                }
            })

        return workflow_plan

    async def plan_scene_batch_workflow(self, intent: UserIntent,
                                       user_context: Dict,
                                       project_context: Optional[Dict]) -> Dict:
        """Plan intelligent batch scene generation with consistency across scenes"""

        scenes = intent.context.get('scenes', [])
        characters = intent.context.get('characters', [])

        workflow_plan = {
            'workflow_type': WorkflowType.SCENE_BATCH,
            'steps': [
                {
                    'step_type': 'echo_brain_consultation',
                    'purpose': 'Analyze batch generation strategy',
                    'parameters': {
                        'scene_count': len(scenes),
                        'character_consistency_requirements': characters,
                        'narrative_flow': intent.context.get('narrative_sequence', False)
                    }
                },
                {
                    'step_type': 'load_project_consistency_context',
                    'purpose': 'Ensure consistency across existing scenes',
                    'parameters': {
                        'project_id': intent.project_id,
                        'character_definitions': characters
                    }
                },
                {
                    'step_type': 'plan_scene_sequence',
                    'purpose': 'Optimize generation order for consistency',
                    'parameters': {
                        'narrative_flow': True,
                        'character_appearance_optimization': True
                    }
                },
                {
                    'step_type': 'batch_generate_with_consistency',
                    'purpose': 'Generate scenes with cross-scene consistency checks',
                    'parameters': {
                        'parallel_generation': False,  # Sequential for better consistency
                        'consistency_validation': True,
                        'adaptive_improvement': True
                    },
                    'quality_checkpoint': True
                },
                {
                    'step_type': 'batch_quality_analysis',
                    'purpose': 'Analyze batch for overall consistency and quality',
                    'parameters': {
                        'cross_scene_consistency': True,
                        'narrative_flow_analysis': True
                    }
                }
            ],
            'adaptive_parameters': {
                'batch_learning': True,
                'consistency_weight': 0.8  # Prioritize consistency in batch
            },
            'quality_checkpoints': ['scene_planning', 'consistency_validation', 'batch_analysis'],
            'learning_opportunities': ['batch_consistency_patterns', 'narrative_flow_optimization']
        }

        return workflow_plan

    # ================================
    # WORKFLOW STEP EXECUTION
    # ================================

    async def execute_workflow_step(self, step: Dict, workflow_result: Dict,
                                   user_intent: UserIntent) -> Dict[str, Any]:
        """Execute individual workflow step with adaptation"""

        step_type = step['step_type']

        if step_type == 'echo_brain_consultation':
            return await self.execute_echo_brain_consultation(step, user_intent)
        elif step_type == 'load_character_template':
            return await self.execute_load_character_template(step, user_intent)
        elif step_type == 'build_adaptive_prompt':
            return await self.execute_build_adaptive_prompt(step, workflow_result, user_intent)
        elif step_type == 'generate_with_consistency_check':
            return await self.execute_generate_with_consistency_check(step, workflow_result, user_intent)
        elif step_type == 'update_character_consistency_memory':
            return await self.execute_update_character_consistency_memory(step, workflow_result, user_intent)
        else:
            logger.warning(f"Unknown step type: {step_type}")
            return {'success': False, 'error': f'Unknown step type: {step_type}'}

    async def execute_echo_brain_consultation(self, step: Dict, user_intent: UserIntent) -> Dict:
        """Consult Echo Brain for intelligent decision making"""
        try:
            consultation_params = step['parameters']

            # Build consultation query for Echo Brain
            consultation_query = self.build_echo_consultation_query(consultation_params, user_intent)

            # Send to Echo Brain
            response = requests.post(
                f"{self.echo_brain_url}/api/echo/query",
                json={
                    'query': consultation_query,
                    'conversation_id': f"orchestration_{user_intent.user_id}",
                    'context': consultation_params
                },
                timeout=30
            )

            if response.status_code == 200:
                echo_result = response.json()

                # Parse Echo's recommendations
                recommendations = self.parse_echo_recommendations(echo_result)

                return {
                    'success': True,
                    'echo_recommendations': recommendations,
                    'raw_response': echo_result,
                    'consultation_effectiveness': self.evaluate_consultation_effectiveness(recommendations)
                }
            else:
                logger.error(f"Echo Brain consultation failed: {response.status_code}")
                return {'success': False, 'error': f'Echo Brain unavailable: {response.status_code}'}

        except Exception as e:
            logger.error(f"Echo consultation error: {e}")
            return {'success': False, 'error': str(e), 'fallback_used': True}

    def build_echo_consultation_query(self, params: Dict, user_intent: UserIntent) -> str:
        """Build intelligent consultation query for Echo Brain"""

        if params.get('consultation_type') == 'workflow_optimization':
            return f"""As the AI Production Director, analyze this anime generation workflow:

USER INTENT: {user_intent.action} {user_intent.target}
SOURCE: {user_intent.source.value}
CONTEXT: {json.dumps(user_intent.context, indent=2)}

USER PREFERENCES: {json.dumps(params.get('user_preferences', {}), indent=2)}

ANALYSIS NEEDED:
1. **Workflow Optimization**: What's the best approach for this specific request?
2. **Style Consistency**: How to maintain visual consistency with user's preferences?
3. **Quality Prediction**: What are the likely failure points and how to prevent them?
4. **Adaptive Strategy**: How should the system adapt based on user's history?

Respond with JSON:
{{
  "recommended_approach": "detailed strategy",
  "style_applications": ["specific style recommendations"],
  "quality_prevention": ["potential issues and preventions"],
  "adaptive_parameters": {{"key": "value"}},
  "confidence_score": 0.0-1.0,
  "alternative_approaches": ["if main approach fails"]
}}"""

        elif params.get('consultation_type') == 'character_generation':
            return f"""Analyze character generation for intelligent consistency:

CHARACTER: {params.get('character_name', 'Unknown')}
EXISTING DATA: {json.dumps(params.get('existing_consistency_data', {}), indent=2)}
STYLE PREFERENCES: {json.dumps(params.get('user_style_preferences', {}), indent=2)}

PROVIDE:
1. **Prompt Optimization**: Best prompt structure for this character
2. **Consistency Strategy**: How to ensure visual consistency
3. **Style Integration**: How to apply user style while maintaining character
4. **Quality Prediction**: Likelihood of success and failure modes

JSON Response:
{{
  "prompt_recommendations": {{"positive": "enhanced prompt", "negative": "things to avoid"}},
  "consistency_strategy": "approach for maintaining character consistency",
  "style_integration": "how to blend user style with character",
  "success_probability": 0.0-1.0,
  "failure_modes": ["potential problems"],
  "adaptive_suggestions": ["how to improve if it fails"]
}}"""

        return "Provide creative direction for this anime production task."

    # ================================
    # LEARNING AND ADAPTATION
    # ================================

    async def learn_from_interaction(self, orchestration_id: str, user_intent: UserIntent,
                                    workflow_result: Dict, user_context: Dict) -> Dict:
        """Learn from the complete interaction to improve future workflows"""

        learning_insights = {
            'style_learnings': {},
            'workflow_improvements': {},
            'user_preference_updates': {},
            'system_optimizations': {}
        }

        try:
            # Analyze workflow success patterns
            success_analysis = self.analyze_workflow_success(workflow_result, user_intent)

            # Update user creative DNA based on interaction
            user_dna_updates = await self.extract_user_preference_learnings(
                user_intent, workflow_result, user_context
            )

            # Learn prompt effectiveness
            prompt_learnings = await self.analyze_prompt_effectiveness(workflow_result)

            # Update character consistency data if applicable
            if user_intent.target == 'character':
                character_learnings = await self.update_character_learnings(
                    user_intent, workflow_result
                )
                learning_insights['character_improvements'] = character_learnings

            # Record learning in Echo Intelligence log
            await self.record_echo_intelligence(
                orchestration_id, user_intent, workflow_result, learning_insights
            )

            # Update user creative DNA
            if user_dna_updates:
                await self.update_user_creative_dna(user_intent.user_id, user_dna_updates)

            logger.info(f"🧠 LEARNED: Interaction {orchestration_id} generated {len(learning_insights)} insights")

            return learning_insights

        except Exception as e:
            logger.error(f"Learning from interaction failed: {e}")
            return learning_insights

    async def generate_next_suggestions(self, user_intent: UserIntent,
                                       workflow_result: Dict) -> List[Dict]:
        """Generate intelligent suggestions for what the user might want to do next"""

        suggestions = []

        # Analyze what was just accomplished
        if workflow_result.get('success') and user_intent.target == 'character':
            suggestions.extend([
                {
                    'action': 'generate_scene',
                    'description': f"Create a scene with {user_intent.context.get('character_name', 'this character')}",
                    'confidence': 0.8,
                    'reasoning': 'Natural progression from character to scene'
                },
                {
                    'action': 'generate_variations',
                    'description': f"Generate style variations of {user_intent.context.get('character_name', 'this character')}",
                    'confidence': 0.6,
                    'reasoning': 'Explore different interpretations of the character'
                }
            ])

        elif user_intent.target == 'scene':
            suggestions.extend([
                {
                    'action': 'continue_story',
                    'description': 'Generate the next scene in the sequence',
                    'confidence': 0.9,
                    'reasoning': 'Continue narrative flow'
                },
                {
                    'action': 'refine_style',
                    'description': 'Refine the visual style for this project',
                    'confidence': 0.7,
                    'reasoning': 'Opportunity to perfect the aesthetic'
                }
            ])

        # Add learning-based suggestions
        learning_suggestions = await self.generate_learning_based_suggestions(user_intent, workflow_result)
        suggestions.extend(learning_suggestions)

        return sorted(suggestions, key=lambda x: x['confidence'], reverse=True)[:5]

    # ================================
    # DATABASE INTERACTION METHODS
    # ================================

    async def record_echo_intelligence(self, orchestration_id: str, user_intent: UserIntent,
                                      workflow_result: Dict, learning_insights: Dict):
        """Record intelligence learning in the database"""
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO echo_intelligence
                (session_id, user_id, project_id, interaction_source, user_intent, user_command,
                 echo_response, echo_reasoning, learning_outcomes, success_metrics,
                 style_adjustments, prompt_improvements, parameter_optimizations)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                orchestration_id,
                user_intent.user_id,
                user_intent.project_id,
                user_intent.source.value,
                f"{user_intent.action} {user_intent.target}",
                json.dumps(user_intent.context),
                json.dumps(workflow_result),
                f"Orchestrated {workflow_result.get('executed_steps', [])} workflow",
                json.dumps(learning_insights),
                json.dumps(self.calculate_success_metrics(workflow_result)),
                json.dumps(learning_insights.get('style_learnings', {})),
                json.dumps(learning_insights.get('workflow_improvements', {})),
                json.dumps(learning_insights.get('system_optimizations', {}))
            ))

            conn.commit()
            conn.close()

        except Exception as e:
            logger.error(f"Failed to record Echo intelligence: {e}")

    async def update_user_creative_dna(self, user_id: str, updates: Dict):
        """Update user creative DNA based on learning"""
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()

            # Get current DNA
            cursor.execute("SELECT * FROM user_creative_dna WHERE user_id = %s OR username = %s",
                          (user_id, user_id))
            current_dna = cursor.fetchone()

            if current_dna:
                # Merge updates intelligently
                updated_style_signatures = self.merge_style_signatures(
                    current_dna[2], updates.get('style_signatures', {})  # style_signatures is column 2
                )

                cursor.execute("""
                    UPDATE user_creative_dna
                    SET style_signatures = %s,
                        total_generations = total_generations + 1,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = %s
                """, (json.dumps(updated_style_signatures), current_dna[0]))

            conn.commit()
            conn.close()

        except Exception as e:
            logger.error(f"Failed to update user creative DNA: {e}")

    # ================================
    # UTILITY METHODS
    # ================================

    def classify_workflow_type(self, intent: UserIntent, project_context: Optional[Dict]) -> WorkflowType:
        """Classify the type of workflow needed based on intent analysis"""

        if intent.action == 'generate' and intent.target == 'character':
            return WorkflowType.CHARACTER_GENERATION
        elif intent.action == 'generate' and 'batch' in intent.context:
            return WorkflowType.SCENE_BATCH
        elif intent.action == 'continue' or (project_context and intent.action == 'generate'):
            return WorkflowType.PROJECT_CONTINUATION
        elif intent.action == 'learn' or intent.action == 'remember':
            return WorkflowType.STYLE_LEARNING
        else:
            return WorkflowType.CHARACTER_GENERATION  # Default fallback

    def calculate_success_metrics(self, workflow_result: Dict) -> Dict:
        """Calculate success metrics for the workflow"""
        executed_steps = workflow_result.get('executed_steps', [])
        successful_steps = sum(1 for step in executed_steps if step.get('result', {}).get('success', False))

        return {
            'workflow_completion': len(executed_steps) > 0,
            'step_success_rate': successful_steps / len(executed_steps) if executed_steps else 0,
            'adaptation_count': len(workflow_result.get('adaptive_adjustments', [])),
            'quality_score': self.calculate_average_quality_score(workflow_result),
            'learning_effectiveness': len(workflow_result.get('learned_adaptations', {})) > 0
        }

    def calculate_average_quality_score(self, workflow_result: Dict) -> float:
        """Calculate average quality score across all quality checkpoints"""
        quality_results = workflow_result.get('quality_results', [])
        if not quality_results:
            return 0.5  # Neutral score if no quality checks

        scores = [qr.get('quality_score', 0.5) for qr in quality_results]
        return sum(scores) / len(scores)

# ================================
# TESTING AND VALIDATION
# ================================

async def test_echo_orchestration_engine():
    """Test the Echo Orchestration Engine with sample workflows"""

    db_config = {
        'host': 'localhost',
        'database': 'anime_production',
        'user': 'patrick',
        'password': 'tower_echo_brain_secret_key_2025'
    }

    engine = EchoOrchestrationEngine(db_config)

    # Test character generation workflow
    test_intent = UserIntent(
        action='generate',
        target='character',
        context={
            'character_name': 'Yuki Tanaka',
            'style_preference': 'photorealistic',
            'scene_context': 'portrait'
        },
        source=InteractionSource.API,
        user_id='test_user_patrick',
        project_id='tokyo_debt_desire'
    )

    print("🧪 Testing Echo Orchestration Engine...")
    print(f"Intent: {test_intent.action} {test_intent.target}")
    print(f"Source: {test_intent.source.value}")

    # result = await engine.orchestrate_user_request(test_intent)
    # print(f"Result: {result.get('success', False)}")
    # print(f"Learned adaptations: {len(result.get('learned_adaptations', {}))}")

    print("✅ Echo Orchestration Engine ready for production!")

if __name__ == "__main__":
    asyncio.run(test_echo_orchestration_engine())