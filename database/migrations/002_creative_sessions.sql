-- Creative Sessions Schema for AI Director System
-- Bridges frontend sessions, anime pipeline, and Echo Brain
-- Run this after echo_brain_creative_schema.sql

-- =============================================================================
-- CREATIVE SESSIONS TABLE
-- Core table for AI Director workflow sessions
-- =============================================================================

CREATE TABLE IF NOT EXISTS creative_sessions (
    id BIGSERIAL PRIMARY KEY,

    -- Identification
    session_uuid UUID DEFAULT gen_random_uuid() UNIQUE NOT NULL,
    user_id BIGINT,  -- Optional user reference
    project_id BIGINT REFERENCES projects(id) ON DELETE CASCADE,

    -- Echo Brain Integration
    echo_conversation_id VARCHAR(100),  -- Links to Echo Brain conversation
    echo_session_state JSONB,  -- Serialized Echo Brain session

    -- Creative State
    current_scene_id BIGINT REFERENCES movie_scenes(id) ON DELETE SET NULL,
    current_mode VARCHAR(50) DEFAULT 'planning'
        CHECK (current_mode IN ('planning', 'directing', 'reviewing', 'generating')),
    current_character_ids BIGINT[],  -- Array of character IDs in focus

    -- Context Cache (Optimized for fast loading)
    cached_context JSONB DEFAULT '{}'::jsonb,
    -- Structure:
    --   scene_location: string
    --   time_of_day: string
    --   mood: string
    --   active_characters: array
    --   last_generation_results: array
    --   camera_settings: object
    --   style_preferences: object

    -- AI Memory
    director_notes JSONB DEFAULT '[]'::jsonb,  -- Array of AI suggestions/decisions
    style_decisions JSONB DEFAULT '{}'::jsonb,  -- Visual style choices
    narrative_arc TEXT,  -- Current narrative context
    prompt_history JSONB DEFAULT '[]'::jsonb,  -- Recent prompts for learning

    -- Activity Tracking
    interaction_count INTEGER DEFAULT 0,
    last_interaction_type VARCHAR(50),
    generation_count INTEGER DEFAULT 0,
    successful_generations INTEGER DEFAULT 0,

    -- Timestamps with timezone
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    last_interaction_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP + INTERVAL '24 hours',

    -- Status
    status VARCHAR(20) DEFAULT 'active'
        CHECK (status IN ('active', 'paused', 'completed', 'archived', 'expired'))
);

-- Performance indexes
CREATE INDEX IF NOT EXISTS idx_creative_sessions_uuid ON creative_sessions(session_uuid);
CREATE INDEX IF NOT EXISTS idx_creative_sessions_user ON creative_sessions(user_id, status);
CREATE INDEX IF NOT EXISTS idx_creative_sessions_project ON creative_sessions(project_id);
CREATE INDEX IF NOT EXISTS idx_creative_sessions_echo ON creative_sessions(echo_conversation_id);
CREATE INDEX IF NOT EXISTS idx_creative_sessions_active ON creative_sessions(status) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_creative_sessions_expires ON creative_sessions(expires_at) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_creative_sessions_mode ON creative_sessions(current_mode);

-- =============================================================================
-- SESSION CONTEXT SNAPSHOTS TABLE
-- Tracks context changes for debugging and learning
-- =============================================================================

CREATE TABLE IF NOT EXISTS session_context_snapshots (
    id BIGSERIAL PRIMARY KEY,
    session_id BIGINT REFERENCES creative_sessions(id) ON DELETE CASCADE,

    -- What changed
    context_key VARCHAR(100) NOT NULL,  -- e.g., "scene_location", "character_emotion"
    old_value JSONB,
    new_value JSONB NOT NULL,

    -- Why it changed
    change_source VARCHAR(50) NOT NULL
        CHECK (change_source IN ('user', 'ai_suggestion', 'generation_result', 'system', 'auto')),
    change_reason TEXT,

    -- Linked generation if applicable
    generation_id BIGINT,  -- References production_jobs(id)

    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_snapshots_session ON session_context_snapshots(session_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_key ON session_context_snapshots(context_key);
CREATE INDEX IF NOT EXISTS idx_snapshots_source ON session_context_snapshots(change_source);
CREATE INDEX IF NOT EXISTS idx_snapshots_time ON session_context_snapshots(created_at);

-- =============================================================================
-- LEARNING FEEDBACK TABLE
-- Stores generation quality feedback for AI learning loop
-- =============================================================================

CREATE TABLE IF NOT EXISTS learning_feedback (
    id BIGSERIAL PRIMARY KEY,

    -- What was generated
    session_id BIGINT REFERENCES creative_sessions(id) ON DELETE CASCADE,
    generation_id BIGINT,  -- References production_jobs(id)
    prompt_used TEXT NOT NULL,
    enhanced_prompt TEXT,  -- AI-enhanced version
    negative_prompt TEXT,

    -- Generation parameters
    generation_params JSONB,  -- All params used
    character_ids BIGINT[],  -- Characters involved
    pose_ids BIGINT[],  -- Poses used

    -- Quality metrics from FramePack/Quality Analyzer
    quality_scores JSONB NOT NULL,  -- {"ssim": 0.85, "optical_flow": 0.72, "character_consistency": 0.90}
    quality_category VARCHAR(20)
        CHECK (quality_category IN ('excellent', 'good', 'acceptable', 'poor', 'failed')),
    overall_score FLOAT,

    -- AI analysis
    ai_analysis JSONB,  -- What worked/didn't work
    learned_patterns TEXT[],  -- Extracted patterns for future use
    confidence_adjustments JSONB,  -- How this affects future suggestions
    improvement_suggestions TEXT[],  -- AI suggestions for improvement

    -- User feedback
    user_rating INTEGER CHECK (user_rating >= 1 AND user_rating <= 5),
    user_comments TEXT,
    user_accepted BOOLEAN,  -- Did user accept the result?

    -- Context tags for pattern matching
    context_tags TEXT[],  -- ["indoor", "action", "closeup", etc.]
    style_tags TEXT[],  -- ["anime", "realistic", "cel-shaded", etc.]

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    analyzed_at TIMESTAMPTZ,

    -- Ensure we have quality data
    CONSTRAINT feedback_has_quality CHECK (quality_scores IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_learning_feedback_session ON learning_feedback(session_id);
CREATE INDEX IF NOT EXISTS idx_learning_feedback_quality ON learning_feedback(quality_category);
CREATE INDEX IF NOT EXISTS idx_learning_feedback_score ON learning_feedback(overall_score);
CREATE INDEX IF NOT EXISTS idx_learning_feedback_patterns ON learning_feedback USING GIN(learned_patterns);
CREATE INDEX IF NOT EXISTS idx_learning_feedback_context ON learning_feedback USING GIN(context_tags);
CREATE INDEX IF NOT EXISTS idx_learning_feedback_style ON learning_feedback USING GIN(style_tags);
CREATE INDEX IF NOT EXISTS idx_learning_feedback_accepted ON learning_feedback(user_accepted);

-- =============================================================================
-- AI PROMPT PATTERNS TABLE
-- Stores successful prompt patterns for reuse
-- =============================================================================

CREATE TABLE IF NOT EXISTS ai_prompt_patterns (
    id BIGSERIAL PRIMARY KEY,

    -- Pattern identification
    pattern_name VARCHAR(255) NOT NULL,
    pattern_category VARCHAR(100),  -- "character_intro", "action_scene", "emotional", etc.

    -- Pattern content
    base_template TEXT NOT NULL,  -- Template with {placeholders}
    style_keywords TEXT[],
    negative_keywords TEXT[],

    -- Usage tracking
    usage_count INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    average_quality_score FLOAT,
    last_used_at TIMESTAMPTZ,

    -- Context applicability
    applicable_emotions TEXT[],
    applicable_actions TEXT[],
    applicable_camera_angles TEXT[],

    -- Learning metadata
    source_feedbacks BIGINT[],  -- learning_feedback IDs this was derived from
    confidence_score FLOAT DEFAULT 0.5,

    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(pattern_name, pattern_category)
);

CREATE INDEX IF NOT EXISTS idx_patterns_category ON ai_prompt_patterns(pattern_category);
CREATE INDEX IF NOT EXISTS idx_patterns_quality ON ai_prompt_patterns(average_quality_score);
CREATE INDEX IF NOT EXISTS idx_patterns_confidence ON ai_prompt_patterns(confidence_score);

-- =============================================================================
-- DIRECTOR SUGGESTIONS TABLE
-- Stores AI-generated suggestions for the director interface
-- =============================================================================

CREATE TABLE IF NOT EXISTS director_suggestions (
    id BIGSERIAL PRIMARY KEY,
    session_id BIGINT REFERENCES creative_sessions(id) ON DELETE CASCADE,

    -- Suggestion details
    suggestion_type VARCHAR(50) NOT NULL
        CHECK (suggestion_type IN ('pose', 'camera', 'lighting', 'prompt', 'sequence', 'style', 'transition')),
    suggestion_data JSONB NOT NULL,
    explanation TEXT,

    -- AI confidence
    confidence_score FLOAT,
    model_used VARCHAR(100),

    -- User response
    status VARCHAR(20) DEFAULT 'pending'
        CHECK (status IN ('pending', 'accepted', 'rejected', 'modified', 'expired')),
    user_response_at TIMESTAMPTZ,
    user_modification JSONB,  -- If modified, what they changed

    -- Context when suggested
    context_snapshot JSONB,

    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP + INTERVAL '1 hour'
);

CREATE INDEX IF NOT EXISTS idx_suggestions_session ON director_suggestions(session_id);
CREATE INDEX IF NOT EXISTS idx_suggestions_type ON director_suggestions(suggestion_type);
CREATE INDEX IF NOT EXISTS idx_suggestions_status ON director_suggestions(status);
CREATE INDEX IF NOT EXISTS idx_suggestions_pending ON director_suggestions(status, session_id) WHERE status = 'pending';

-- =============================================================================
-- MATERIALIZED VIEW FOR PATTERN ANALYSIS
-- Pre-computed statistics for prompt patterns
-- =============================================================================

CREATE MATERIALIZED VIEW IF NOT EXISTS learning_patterns_analysis AS
SELECT
    unnest(learned_patterns) as pattern,
    quality_category,
    COUNT(*) as frequency,
    AVG(user_rating) as avg_rating,
    AVG(overall_score) as avg_quality,
    AVG((quality_scores->>'ssim')::float) as avg_ssim,
    AVG((quality_scores->>'character_consistency')::float) as avg_consistency,
    array_agg(DISTINCT unnest(context_tags)) as common_contexts
FROM learning_feedback
WHERE learned_patterns IS NOT NULL
GROUP BY unnest(learned_patterns), quality_category
WITH DATA;

CREATE UNIQUE INDEX IF NOT EXISTS idx_patterns_analysis_unique
    ON learning_patterns_analysis(pattern, quality_category);

-- Function to refresh the materialized view
CREATE OR REPLACE FUNCTION refresh_learning_patterns()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY learning_patterns_analysis;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- TRIGGERS
-- =============================================================================

-- Update timestamps and interaction tracking
CREATE OR REPLACE FUNCTION update_creative_session_activity()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    NEW.last_interaction_at = CURRENT_TIMESTAMP;
    NEW.interaction_count = COALESCE(OLD.interaction_count, 0) + 1;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER creative_sessions_activity_trigger
BEFORE UPDATE ON creative_sessions
FOR EACH ROW
EXECUTE FUNCTION update_creative_session_activity();

-- Auto-categorize quality based on scores
CREATE OR REPLACE FUNCTION categorize_quality()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.overall_score IS NULL AND NEW.quality_scores IS NOT NULL THEN
        -- Calculate overall score as average of available metrics
        NEW.overall_score = (
            COALESCE((NEW.quality_scores->>'ssim')::float, 0) +
            COALESCE((NEW.quality_scores->>'optical_flow')::float, 0) +
            COALESCE((NEW.quality_scores->>'character_consistency')::float, 0)
        ) / 3.0;
    END IF;

    -- Categorize based on overall score
    IF NEW.overall_score >= 0.85 THEN
        NEW.quality_category = 'excellent';
    ELSIF NEW.overall_score >= 0.70 THEN
        NEW.quality_category = 'good';
    ELSIF NEW.overall_score >= 0.50 THEN
        NEW.quality_category = 'acceptable';
    ELSIF NEW.overall_score >= 0.30 THEN
        NEW.quality_category = 'poor';
    ELSE
        NEW.quality_category = 'failed';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER learning_feedback_categorize_trigger
BEFORE INSERT OR UPDATE ON learning_feedback
FOR EACH ROW
EXECUTE FUNCTION categorize_quality();

-- Update pattern confidence when feedback is analyzed
CREATE OR REPLACE FUNCTION update_pattern_confidence()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.analyzed_at IS NOT NULL AND NEW.learned_patterns IS NOT NULL THEN
        -- Update confidence scores for patterns
        UPDATE ai_prompt_patterns
        SET
            usage_count = usage_count + 1,
            success_count = success_count + CASE WHEN NEW.quality_category IN ('excellent', 'good') THEN 1 ELSE 0 END,
            average_quality_score = (
                (average_quality_score * usage_count + NEW.overall_score) / (usage_count + 1)
            ),
            confidence_score = (success_count + 1.0) / (usage_count + 2.0),
            last_used_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE pattern_name = ANY(NEW.learned_patterns);
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER learning_feedback_update_patterns_trigger
AFTER UPDATE ON learning_feedback
FOR EACH ROW
WHEN (OLD.analyzed_at IS NULL AND NEW.analyzed_at IS NOT NULL)
EXECUTE FUNCTION update_pattern_confidence();

-- =============================================================================
-- HELPER FUNCTIONS
-- =============================================================================

-- Get or create a session for a project
CREATE OR REPLACE FUNCTION get_or_create_session(
    p_project_id BIGINT,
    p_user_id BIGINT DEFAULT NULL
) RETURNS creative_sessions AS $$
DECLARE
    v_session creative_sessions;
BEGIN
    -- Try to find existing active session
    SELECT * INTO v_session
    FROM creative_sessions
    WHERE project_id = p_project_id
    AND (p_user_id IS NULL OR user_id = p_user_id)
    AND status = 'active'
    AND expires_at > CURRENT_TIMESTAMP
    ORDER BY last_interaction_at DESC
    LIMIT 1;

    -- Create new if not found
    IF v_session IS NULL THEN
        INSERT INTO creative_sessions (project_id, user_id)
        VALUES (p_project_id, p_user_id)
        RETURNING * INTO v_session;
    END IF;

    RETURN v_session;
END;
$$ LANGUAGE plpgsql;

-- Get session context with all related data
CREATE OR REPLACE FUNCTION get_session_with_context(p_session_uuid UUID)
RETURNS JSONB AS $$
DECLARE
    v_result JSONB;
BEGIN
    SELECT jsonb_build_object(
        'session', row_to_json(cs),
        'recent_snapshots', (
            SELECT jsonb_agg(row_to_json(scs))
            FROM session_context_snapshots scs
            WHERE scs.session_id = cs.id
            ORDER BY scs.created_at DESC
            LIMIT 20
        ),
        'pending_suggestions', (
            SELECT jsonb_agg(row_to_json(ds))
            FROM director_suggestions ds
            WHERE ds.session_id = cs.id
            AND ds.status = 'pending'
        ),
        'recent_feedback', (
            SELECT jsonb_agg(row_to_json(lf))
            FROM learning_feedback lf
            WHERE lf.session_id = cs.id
            ORDER BY lf.created_at DESC
            LIMIT 10
        )
    ) INTO v_result
    FROM creative_sessions cs
    WHERE cs.session_uuid = p_session_uuid;

    RETURN v_result;
END;
$$ LANGUAGE plpgsql;

-- Get best patterns for a context
CREATE OR REPLACE FUNCTION get_best_patterns_for_context(
    p_context_tags TEXT[],
    p_limit INTEGER DEFAULT 5
) RETURNS TABLE (
    pattern_name VARCHAR,
    pattern_category VARCHAR,
    base_template TEXT,
    confidence_score FLOAT,
    avg_quality FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        ap.pattern_name,
        ap.pattern_category,
        ap.base_template,
        ap.confidence_score,
        ap.average_quality_score
    FROM ai_prompt_patterns ap
    WHERE ap.confidence_score > 0.5
    ORDER BY
        ap.confidence_score DESC,
        ap.average_quality_score DESC
    LIMIT p_limit;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- GRANTS
-- =============================================================================

GRANT ALL ON ALL TABLES IN SCHEMA public TO patrick;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO patrick;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO patrick;

-- =============================================================================
-- COMMENTS
-- =============================================================================

COMMENT ON TABLE creative_sessions IS 'Core table for AI Director workflow sessions, bridging frontend, anime pipeline, and Echo Brain';
COMMENT ON TABLE session_context_snapshots IS 'Tracks all context changes within a session for debugging and learning';
COMMENT ON TABLE learning_feedback IS 'Stores generation quality feedback for AI learning loop';
COMMENT ON TABLE ai_prompt_patterns IS 'Learned prompt patterns for reuse based on quality feedback';
COMMENT ON TABLE director_suggestions IS 'AI-generated suggestions for the director interface';
