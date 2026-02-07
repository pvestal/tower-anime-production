"""
Scene Description Data Models
Professional scene description structures for anime production
"""

from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from decimal import Decimal
from pydantic import BaseModel, Field
from enum import Enum

class TimeOfDay(str, Enum):
    """Time of day options for scenes"""
    DAWN = "dawn"
    MORNING = "morning"
    MIDDAY = "midday"
    AFTERNOON = "afternoon"
    EVENING = "evening"
    DUSK = "dusk"
    NIGHT = "night"
    MIDNIGHT = "midnight"

class Mood(str, Enum):
    """Mood options for scenes"""
    DRAMATIC = "dramatic"
    COMEDIC = "comedic"
    ROMANTIC = "romantic"
    SUSPENSEFUL = "suspenseful"
    ACTION = "action"
    PEACEFUL = "peaceful"
    MELANCHOLIC = "melancholic"
    MYSTERIOUS = "mysterious"
    ENERGETIC = "energetic"
    CONTEMPLATIVE = "contemplative"

class CameraAngle(str, Enum):
    """Camera angle options"""
    WIDE_SHOT = "wide_shot"
    MEDIUM_SHOT = "medium_shot"
    CLOSE_UP = "close_up"
    EXTREME_CLOSE_UP = "extreme_close_up"
    BIRD_EYE_VIEW = "bird_eye_view"
    WORMS_EYE_VIEW = "worms_eye_view"
    OVER_SHOULDER = "over_shoulder"
    TWO_SHOT = "two_shot"
    ESTABLISHING_SHOT = "establishing_shot"

class CameraMovement(str, Enum):
    """Camera movement types"""
    STATIC = "static"
    PAN = "pan"
    TILT = "tilt"
    ZOOM_IN = "zoom_in"
    ZOOM_OUT = "zoom_out"
    DOLLY_IN = "dolly_in"
    DOLLY_OUT = "dolly_out"
    TRACKING = "tracking"
    HANDHELD = "handheld"
    CRANE = "crane"

class LightingType(str, Enum):
    """Lighting types for scenes"""
    NATURAL = "natural"
    DRAMATIC = "dramatic"
    SOFT = "soft"
    HARSH = "harsh"
    BACKLIT = "backlit"
    SILHOUETTE = "silhouette"
    GOLDEN_HOUR = "golden_hour"
    BLUE_HOUR = "blue_hour"
    ARTIFICIAL = "artificial"
    MIXED = "mixed"

# Request Models
class CreateSceneRequest(BaseModel):
    """Request model for creating a new scene"""
    script_id: int = Field(..., description="ID of the script this scene belongs to")
    scene_number: int = Field(..., description="Scene number in the script")
    title: Optional[str] = Field(None, description="Scene title")
    location: str = Field(..., description="Scene location")
    time_of_day: TimeOfDay = Field(..., description="Time of day for the scene")
    characters: List[str] = Field(..., description="Characters present in the scene")
    action_summary: str = Field(..., description="Brief summary of the action")
    mood: Mood = Field(..., description="Overall mood of the scene")
    style_preferences: Optional[Dict[str, Any]] = Field(None, description="Style preferences")
    created_by: str = Field("autonomous", description="Creator identifier")

class UpdateSceneRequest(BaseModel):
    """Request model for updating a scene"""
    title: Optional[str] = None
    location: Optional[str] = None
    time_of_day: Optional[TimeOfDay] = None
    characters: Optional[List[str]] = None
    action_summary: Optional[str] = None
    mood: Optional[Mood] = None
    visual_description: Optional[str] = None
    cinematography_notes: Optional[str] = None
    atmosphere_description: Optional[str] = None
    timing_notes: Optional[str] = None
    regenerate_description: bool = Field(False, description="Regenerate scene description")

class BatchSceneRequest(BaseModel):
    """Request model for batch scene generation"""
    script_id: int = Field(..., description="Script ID to generate scenes for")
    scene_count: int = Field(..., ge=1, le=50, description="Number of scenes to generate")
    style_preferences: Optional[Dict[str, Any]] = Field(None, description="Style preferences")
    revenue_optimization: bool = Field(True, description="Enable revenue optimization")

class ExportAnimeRequest(BaseModel):
    """Request model for exporting to anime production"""
    scene_ids: List[int] = Field(..., description="Scene IDs to export")
    project_id: Optional[int] = Field(None, description="Target anime project ID")
    export_options: Dict[str, Any] = Field(default_factory=dict, description="Export options")

class EchoCollaborationRequest(BaseModel):
    """Request model for Echo Brain collaboration"""
    prompt: str = Field(..., description="Collaboration prompt")
    context: Dict[str, Any] = Field(default_factory=dict, description="Context information")
    creative_parameters: Optional[Dict[str, Any]] = Field(None, description="Creative parameters")

# Response Models
class TechnicalSpecifications(BaseModel):
    """Technical specifications for scene production"""
    camera_angle: CameraAngle
    camera_movement: CameraMovement
    lighting_type: LightingType
    color_palette: List[str]
    aspect_ratio: str = Field(default="16:9")
    frame_rate: int = Field(default=24)
    resolution: str = Field(default="1920x1080")
    duration_seconds: Optional[float] = None

class SceneResponse(BaseModel):
    """Response model for scene descriptions"""
    id: int
    script_id: int
    scene_number: int
    title: str
    location: str
    time_of_day: TimeOfDay
    characters: List[str]
    action_summary: str
    mood: Mood
    visual_description: str
    cinematography_notes: str
    atmosphere_description: str
    timing_notes: str
    technical_specifications: TechnicalSpecifications
    revenue_potential: Decimal
    status: str = Field(default="active")
    created_by: str
    created_at: datetime
    updated_at: datetime

class SceneAnalytics(BaseModel):
    """Analytics model for scene performance"""
    scene_id: int
    generation_time_seconds: float
    quality_score: float
    revenue_score: float
    audience_appeal: float
    production_feasibility: float
    last_analyzed: datetime

# Character Models for Scene Context
class CharacterInScene(BaseModel):
    """Character representation in a scene"""
    name: str
    role: str  # "protagonist", "antagonist", "supporting", "background"
    emotional_state: str
    physical_description: str
    costume_notes: str
    positioning: str  # Where they are in the scene
    interaction_level: str  # "primary", "secondary", "background"

class SceneTransition(BaseModel):
    """Scene transition specifications"""
    transition_type: str  # "cut", "fade", "dissolve", "wipe", etc.
    duration_seconds: float
    transition_notes: str

# Advanced Scene Models
class AdvancedSceneRequest(BaseModel):
    """Advanced scene creation with detailed specifications"""
    basic_info: CreateSceneRequest
    character_details: List[CharacterInScene]
    transition_in: Optional[SceneTransition] = None
    transition_out: Optional[SceneTransition] = None
    audio_notes: Optional[str] = None
    special_effects: Optional[List[str]] = None
    budget_constraints: Optional[Dict[str, Any]] = None
    deadline_requirements: Optional[datetime] = None

class SceneRevision(BaseModel):
    """Scene revision tracking"""
    revision_number: int
    changes_made: str
    reason_for_change: str
    revised_by: str
    revision_date: datetime
    approval_status: str  # "pending", "approved", "rejected"

# Production Integration Models
class ProductionRequirements(BaseModel):
    """Production requirements for scenes"""
    estimated_cost: Decimal
    production_time_hours: float
    required_assets: List[str]
    complexity_level: str  # "simple", "moderate", "complex", "highly_complex"
    special_requirements: List[str]

class QualityMetrics(BaseModel):
    """Quality assessment metrics"""
    visual_clarity: float = Field(..., ge=0.0, le=10.0)
    narrative_coherence: float = Field(..., ge=0.0, le=10.0)
    character_consistency: float = Field(..., ge=0.0, le=10.0)
    production_feasibility: float = Field(..., ge=0.0, le=10.0)
    market_appeal: float = Field(..., ge=0.0, le=10.0)
    overall_score: float = Field(..., ge=0.0, le=10.0)

# Revenue Optimization Models
class RevenueMetrics(BaseModel):
    """Revenue potential metrics"""
    estimated_view_count: int
    monetization_potential: Decimal
    merchandise_opportunity: float
    licensing_value: Decimal
    audience_retention_score: float
    viral_potential: float

class OptimizationSuggestions(BaseModel):
    """AI-generated optimization suggestions"""
    visual_improvements: List[str]
    narrative_enhancements: List[str]
    production_efficiencies: List[str]
    revenue_opportunities: List[str]
    market_positioning: List[str]

# Integration Models
class StoryBibleIntegration(BaseModel):
    """Integration with story bible system"""
    story_bible_id: int
    character_consistency_check: bool
    world_building_compliance: bool
    narrative_arc_alignment: bool

class ScriptWriterIntegration(BaseModel):
    """Integration with script writer system"""
    script_id: int
    dialogue_sync: bool
    pacing_alignment: bool
    character_action_match: bool

class AnimeProductionIntegration(BaseModel):
    """Integration with anime production system"""
    project_id: Optional[int] = None
    generation_ready: bool
    asset_requirements_met: bool
    technical_specs_validated: bool