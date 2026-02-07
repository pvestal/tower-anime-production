"""
Pydantic models for the Story Engine.
These are the contracts between the story bible DB and all agents.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class GenerationStatus(str, Enum):
    DRAFT = "draft"
    PROMPTED = "prompted"
    GENERATING = "generating"
    RENDERED = "rendered"
    COMPOSITED = "composited"
    FINAL = "final"


class PropagationScope(str, Enum):
    VISUAL = "visual"
    WRITING = "writing"
    AUDIO = "audio"
    ALL = "all"


class ArcPhase(str, Enum):
    SETUP = "setup"
    RISING = "rising"
    CLIMAX = "climax"
    FALLING = "falling"
    RESOLUTION = "resolution"


# ── Character Models ──────────────────────────────────────────

class VoiceProfile(BaseModel):
    tts_model: str = "bark"
    voice_preset: str = "v2/en_speaker_6"
    pitch_shift: float = 0.0
    speed: float = 1.0
    style_tags: list[str] = Field(default_factory=list)  # ["polite","measured","slightly_condescending"]


class CharacterCreate(BaseModel):
    name: str
    project_id: int
    description: Optional[str] = None
    visual_prompt_template: Optional[str] = None
    voice_profile: VoiceProfile = Field(default_factory=VoiceProfile)
    personality_tags: list[str] = Field(default_factory=list)
    character_role: str = "supporting"
    relationships: dict = Field(default_factory=dict)


class CharacterRead(CharacterCreate):
    id: int
    created_at: datetime


# ── Scene Models ──────────────────────────────────────────────

class DialogueLine(BaseModel):
    character_id: int
    character_name: str  # Denormalized for convenience
    line: str
    timing_offset: float = 0.0  # Seconds from scene start
    emotion: str = "neutral"


class SceneCreate(BaseModel):
    episode_id: str  # UUID
    sequence_order: int
    narrative_text: str
    setting_description: str
    emotional_tone: str = "neutral"
    characters_present: list[int] = Field(default_factory=list)
    dialogue: list[DialogueLine] = Field(default_factory=list)
    narration: Optional[str] = None
    camera_directions: Optional[str] = None
    audio_mood: Optional[str] = None
    visual_style_override: Optional[dict] = None


class SceneRead(SceneCreate):
    id: str  # UUID
    generation_status: GenerationStatus = GenerationStatus.DRAFT
    created_at: datetime


# ── Episode Models ────────────────────────────────────────────

class EpisodeCreate(BaseModel):
    project_id: int
    episode_number: int
    title: str
    synopsis: Optional[str] = None
    tone_profile: dict = Field(default_factory=dict)  # {"comedy": 0.6, "dark": 0.3, "absurd": 0.8}


class EpisodeRead(EpisodeCreate):
    id: str  # UUID
    status: str = "outline"
    scene_count: int = 0


# ── Story Arc Models ──────────────────────────────────────────

class StoryArcCreate(BaseModel):
    project_id: int
    name: str
    description: Optional[str] = None
    arc_type: str = "narrative"
    themes: list[str] = Field(default_factory=list)
    tension_start: float = 0.3
    tension_peak: float = 0.8
    resolution_style: Optional[str] = None


class StoryArcRead(StoryArcCreate):
    id: int
    status: str = "active"
    episode_count: int = 0


# ── Production Profile Models ─────────────────────────────────

class VisualProfile(BaseModel):
    """Project-level visual generation defaults. Stored in production_profiles."""
    base_checkpoint: str = "counterfeit_v3"
    loras: list[dict] = Field(default_factory=list)  # [{"name":"arcane_offset","weight":0.7}]
    style_prompt_suffix: str = ""
    negative_prompt: str = "low quality, blurry, deformed"
    resolution_width: int = 1920
    resolution_height: int = 1080
    video_engine: str = "animatediff"  # Changed from framepack since AnimateDiff is available
    steps: int = 20
    cfg_scale: float = 7.0
    sampler: str = "euler_a"


class AudioProfile(BaseModel):
    """Project-level audio generation defaults."""
    tts_engine: str = "bark"
    music_style: str = "lo-fi cyberpunk"
    default_bgm_volume: float = 0.3
    dialogue_volume: float = 1.0
    mix_profile: str = "dialogue_forward"


class CaptionProfile(BaseModel):
    """Project-level caption/subtitle defaults."""
    style: str = "bottom_center"
    font: str = "monospace"
    font_size: int = 24
    color: str = "#FFFFFF"
    bg_color: str = "#000000AA"
    effect: str = "typewriter"  # typewriter, fade, instant


# ── Change Propagation Models ─────────────────────────────────

class ChangeEvent(BaseModel):
    project_id: int
    table_name: str
    record_id: int
    field_changed: Optional[str] = None
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    change_type: str  # insert, update, delete
    created_by: str = "system"


class PropagationResult(BaseModel):
    change_id: int
    affected_scene_ids: list[str]  # UUIDs
    scope: PropagationScope
    queued_jobs: int