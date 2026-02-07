-- ============================================================
-- STORY BIBLE SCHEMA EXTENSION
-- Run AFTER inspecting existing tables (Phase 0)
-- ============================================================

BEGIN;

-- -----------------------------------------------------------
-- STORY ARCS: Multi-episode narrative threads
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS story_arcs (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    arc_type VARCHAR(50) DEFAULT 'narrative',  -- narrative, comedy, dark, character_growth, meta
    status VARCHAR(30) DEFAULT 'active',       -- active, resolved, dormant
    tension_start FLOAT DEFAULT 0.3,           -- 0.0-1.0 tension at arc introduction
    tension_peak FLOAT DEFAULT 0.8,            -- 0.0-1.0 peak tension target
    resolution_style VARCHAR(50),              -- cathartic, ironic, ambiguous, cliffhanger
    themes TEXT[],                             -- ['isolation','ai_consciousness','imposter_syndrome']
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_story_arcs_project ON story_arcs(project_id);

-- -----------------------------------------------------------
-- ARC-EPISODE JUNCTION: Which arcs touch which episodes
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS arc_episodes (
    id SERIAL PRIMARY KEY,
    arc_id INTEGER NOT NULL REFERENCES story_arcs(id) ON DELETE CASCADE,
    episode_id UUID NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
    arc_phase VARCHAR(30) DEFAULT 'rising',    -- setup, rising, climax, falling, resolution
    tension_level FLOAT DEFAULT 0.5,
    notes TEXT,
    UNIQUE(arc_id, episode_id)
);

-- -----------------------------------------------------------
-- ARC-SCENE JUNCTION: Fine-grained arc-to-scene mapping
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS arc_scenes (
    id SERIAL PRIMARY KEY,
    arc_id INTEGER NOT NULL REFERENCES story_arcs(id) ON DELETE CASCADE,
    scene_id UUID NOT NULL REFERENCES scenes(id) ON DELETE CASCADE,
    relevance FLOAT DEFAULT 1.0,               -- 0.0-1.0 how central this scene is to the arc
    UNIQUE(arc_id, scene_id)
);

-- -----------------------------------------------------------
-- WORLD RULES: Tone, visual, and narrative constraints per project
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS world_rules (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    rule_category VARCHAR(50) NOT NULL,        -- tone, visual, narrative, character, meta
    rule_key VARCHAR(100) NOT NULL,
    rule_value TEXT NOT NULL,
    priority INTEGER DEFAULT 50,               -- higher = more important (0-100)
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(project_id, rule_category, rule_key)
);

-- -----------------------------------------------------------
-- CHARACTER EXTENSIONS: Add story-bible fields to existing characters table
-- Only add columns that don't already exist
-- -----------------------------------------------------------
-- CHECK existing columns first. These are the columns we WANT:
--   visual_prompt_template TEXT       -- ComfyUI prompt fragment for consistent generation
--   voice_profile JSONB              -- TTS model, pitch, speed, style settings
--   personality_tags TEXT[]           -- ['passive_aggressive','overly_helpful','cryptic']
--   character_role VARCHAR(50)        -- protagonist, ai_character, supporting, narrator
--   relationships JSONB              -- {"claude": "collaborator_nemesis", "deepseek": "suspicious_ally"}

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='characters' AND column_name='visual_prompt_template') THEN
        ALTER TABLE characters ADD COLUMN visual_prompt_template TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='characters' AND column_name='voice_profile') THEN
        ALTER TABLE characters ADD COLUMN voice_profile JSONB DEFAULT '{}';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='characters' AND column_name='personality_tags') THEN
        ALTER TABLE characters ADD COLUMN personality_tags TEXT[];
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='characters' AND column_name='character_role') THEN
        ALTER TABLE characters ADD COLUMN character_role VARCHAR(50) DEFAULT 'supporting';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='characters' AND column_name='relationships') THEN
        ALTER TABLE characters ADD COLUMN relationships JSONB DEFAULT '{}';
    END IF;
END $$;

-- -----------------------------------------------------------
-- SCENE EXTENSIONS: Add story-bible fields to existing scenes table
-- -----------------------------------------------------------
-- CHECK existing columns first. We WANT:
--   narrative_text TEXT              -- The actual scene script/narrative
--   emotional_tone VARCHAR(50)       -- melancholic, comedic, tense, absurd, reflective
--   generation_status VARCHAR(30)    -- draft, prompted, generating, rendered, composited, final
--   dialogue JSONB                   -- [{"character_id":1,"line":"...","timing":0.0},...]
--   narration TEXT                   -- Voiceover/narrator text
--   setting_description TEXT         -- Physical environment description
--   camera_directions TEXT           -- Shot composition notes
--   audio_mood VARCHAR(50)           -- lo-fi, tense, ambient, comedic_sting, silence

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='scenes' AND column_name='narrative_text') THEN
        ALTER TABLE scenes ADD COLUMN narrative_text TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='scenes' AND column_name='emotional_tone') THEN
        ALTER TABLE scenes ADD COLUMN emotional_tone VARCHAR(50);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='scenes' AND column_name='generation_status') THEN
        ALTER TABLE scenes ADD COLUMN generation_status VARCHAR(30) DEFAULT 'draft';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='scenes' AND column_name='dialogue') THEN
        ALTER TABLE scenes ADD COLUMN dialogue JSONB DEFAULT '[]';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='scenes' AND column_name='narration') THEN
        ALTER TABLE scenes ADD COLUMN narration TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='scenes' AND column_name='setting_description') THEN
        ALTER TABLE scenes ADD COLUMN setting_description TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='scenes' AND column_name='camera_directions') THEN
        ALTER TABLE scenes ADD COLUMN camera_directions TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='scenes' AND column_name='audio_mood') THEN
        ALTER TABLE scenes ADD COLUMN audio_mood VARCHAR(50);
    END IF;
END $$;

-- -----------------------------------------------------------
-- EPISODE EXTENSIONS
-- -----------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='episodes' AND column_name='synopsis') THEN
        ALTER TABLE episodes ADD COLUMN synopsis TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='episodes' AND column_name='tone_profile') THEN
        ALTER TABLE episodes ADD COLUMN tone_profile JSONB DEFAULT '{}';
    END IF;
END $$;

-- -----------------------------------------------------------
-- STORY CHANGELOG: Track every mutation for change propagation
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS story_changelog (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    table_name VARCHAR(100) NOT NULL,
    record_id INTEGER NOT NULL,
    field_changed VARCHAR(100),
    old_value TEXT,
    new_value TEXT,
    change_type VARCHAR(20) NOT NULL,          -- insert, update, delete
    propagation_scope VARCHAR(20),             -- visual, writing, audio, all
    affected_scenes UUID[],                    -- scene IDs that need regeneration
    propagation_status VARCHAR(20) DEFAULT 'pending',  -- pending, processing, complete, skipped
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by VARCHAR(100) DEFAULT 'system'
);

CREATE INDEX IF NOT EXISTS idx_changelog_project ON story_changelog(project_id);
CREATE INDEX IF NOT EXISTS idx_changelog_status ON story_changelog(propagation_status);
CREATE INDEX IF NOT EXISTS idx_changelog_created ON story_changelog(created_at DESC);

-- -----------------------------------------------------------
-- PRODUCTION PROFILES: Per-project generation settings (DB-driven, not config files)
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS production_profiles (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    profile_type VARCHAR(30) NOT NULL,         -- visual, audio, caption, composition
    settings JSONB NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(project_id, profile_type)
);

-- -----------------------------------------------------------
-- GENERATION QUEUE: Scene-level production job tracking
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS scene_generation_queue (
    id SERIAL PRIMARY KEY,
    scene_id UUID NOT NULL REFERENCES scenes(id) ON DELETE CASCADE,
    generation_scope VARCHAR(20) NOT NULL,     -- writing, visual, audio, caption, composition, all
    priority INTEGER DEFAULT 50,
    status VARCHAR(20) DEFAULT 'queued',       -- queued, processing, complete, failed, stale
    triggered_by INTEGER REFERENCES story_changelog(id),
    worker_id VARCHAR(100),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_gen_queue_status ON scene_generation_queue(status);
CREATE INDEX IF NOT EXISTS idx_gen_queue_scene ON scene_generation_queue(scene_id);

-- -----------------------------------------------------------
-- SCENE ASSETS: Track generated outputs per scene
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS scene_assets (
    id SERIAL PRIMARY KEY,
    scene_id UUID NOT NULL REFERENCES scenes(id) ON DELETE CASCADE,
    asset_type VARCHAR(30) NOT NULL,           -- keyframe, video_clip, dialogue_track, music, sfx, caption_file, narration_audio, composite
    file_path TEXT NOT NULL,
    file_hash VARCHAR(64),                     -- SHA256 for cache invalidation
    generation_params JSONB,                   -- The exact params used to generate this asset
    quality_score FLOAT,                       -- 0.0-1.0 if auto-assessed
    is_current BOOLEAN DEFAULT TRUE,           -- FALSE for superseded versions
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_scene_assets_scene ON scene_assets(scene_id);
CREATE INDEX IF NOT EXISTS idx_scene_assets_current ON scene_assets(scene_id, is_current) WHERE is_current = TRUE;

-- -----------------------------------------------------------
-- REALITY FEED: Log real Echo Brain events for story material
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS reality_feed (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id),
    source VARCHAR(50) NOT NULL,               -- echo_brain_log, git_commit, comfyui_error, manual
    event_type VARCHAR(50),                    -- bug_fix, architecture_change, generation_failure, eureka_moment
    raw_content TEXT NOT NULL,                  -- The actual log entry, commit message, error, etc.
    comedic_potential FLOAT,                   -- 0.0-1.0 rated by AI or manual
    dramatic_potential FLOAT,                  -- 0.0-1.0
    used_in_scene UUID REFERENCES scenes(id),
    tags TEXT[],
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_reality_feed_potential ON reality_feed(comedic_potential DESC, dramatic_potential DESC);

COMMIT;