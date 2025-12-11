-- ============================================================================
-- PERSISTENT CREATIVITY DATABASE SCHEMA
-- Echo Brain Orchestrated Anime Production System
-- ============================================================================
-- This schema enables true AI-augmented creativity with learning and adaptation
-- Author: Claude Code + Patrick Vestal
-- Created: 2025-12-11
-- Branch: feature/echo-orchestration-engine
-- ============================================================================

-- 1. USER CREATIVE DNA - The core of personalized AI creativity
CREATE TABLE IF NOT EXISTS user_creative_dna (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(255) UNIQUE NOT NULL,

    -- Style Signatures: Your unique creative fingerprint
    style_signatures JSONB DEFAULT '{}',
    -- Example: {"lighting": "dramatic_chiaroscuro", "palette": "muted_cyberpunk", "composition": "dutch_angles"}

    -- Character Archetypes: Your go-to character templates
    character_archetypes JSONB DEFAULT '[]',
    -- Example: [{"type": "mysterious_hacker", "traits": ["silver_hair", "cybernetic_eye"]}, ...]

    -- Narrative Patterns: Favorite story structures and themes
    narrative_patterns JSONB DEFAULT '{}',
    -- Example: {"preferred_genres": ["cyberpunk", "urban_fantasy"], "story_beats": ["slow_burn", "dramatic_climax"]}

    -- Evolution Log: How creativity changes over time
    evolution_log JSONB DEFAULT '[]',
    -- Example: [{"timestamp": "2025-12-11", "change": "started preferring warmer lighting", "confidence": 0.85}]

    -- Adaptive Learning Settings
    learning_rate FLOAT DEFAULT 0.1,  -- How quickly to adapt to new preferences
    creativity_variance FLOAT DEFAULT 0.2,  -- How much variation to allow in style

    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    total_projects INTEGER DEFAULT 0,
    total_generations INTEGER DEFAULT 0
);

-- 2. PROJECT MEMORY STACK - Git-like versioning for creative projects
CREATE TABLE IF NOT EXISTS project_memory (
    project_id UUID DEFAULT gen_random_uuid(),
    timeline_commit VARCHAR(64), -- Git-like commit hash for versions
    commit_message TEXT,
    parent_commit VARCHAR(64), -- For branching/merging

    -- Project Context
    project_name VARCHAR(255) NOT NULL,
    project_bible JSONB, -- Complete project context and rules
    user_id UUID REFERENCES user_creative_dna(user_id),

    -- Creative Decision Log
    creative_decisions JSONB DEFAULT '[]',
    -- Example: [{"action": "character_edit", "before": {...}, "after": {...}, "reasoning": "more mysterious"}]

    -- Character Consistency Tracking
    character_consistency_scores JSONB DEFAULT '{}',
    -- Example: {"Yuki": {"face_similarity": 0.92, "style_consistency": 0.87, "total_scenes": 15}}

    -- Style Application History
    style_application_log JSONB DEFAULT '[]',
    -- Example: [{"scene_id": "scene_12", "style": "neon_rain", "success": true, "user_feedback": "perfect"}]

    -- Version Control Metadata
    is_main_branch BOOLEAN DEFAULT false,
    is_active BOOLEAN DEFAULT true,
    commit_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (project_id, timeline_commit)
);

-- 3. ECHO INTELLIGENCE LOG - How Echo learns from every interaction
CREATE TABLE IF NOT EXISTS echo_intelligence (
    session_id UUID DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES user_creative_dna(user_id),
    project_id UUID, -- Can be NULL for general learning

    -- Interaction Context
    interaction_source VARCHAR(50), -- 'telegram', 'browser_studio', 'api'
    user_intent TEXT, -- What the user wanted to achieve
    user_command TEXT, -- Exact command/request

    -- Echo Response & Learning
    echo_response JSONB, -- What Echo decided to do
    echo_reasoning TEXT, -- Why Echo made this decision
    learning_outcomes JSONB, -- What was learned from this interaction

    -- Success Metrics
    success_metrics JSONB DEFAULT '{}',
    -- Example: {"user_satisfaction": 0.9, "technical_quality": 0.85, "creative_alignment": 0.92}

    -- Failure Analysis (when things go wrong)
    failure_analysis JSONB DEFAULT NULL,
    -- Example: {"error_type": "multiple_people", "correction_applied": true, "learned_adjustment": "stronger_solo_prompts"}

    -- Adaptation Data
    style_adjustments JSONB DEFAULT '{}',
    prompt_improvements JSONB DEFAULT '{}',
    parameter_optimizations JSONB DEFAULT '{}',

    -- Metadata
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processing_time_ms INTEGER,
    confidence_score FLOAT DEFAULT 0.5
);

-- 4. CHARACTER CONSISTENCY MEMORY - Per-character learning and evolution
CREATE TABLE IF NOT EXISTS character_consistency_memory (
    character_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    character_name VARCHAR(255) NOT NULL,
    project_id UUID REFERENCES project_memory(project_id),
    user_id UUID REFERENCES user_creative_dna(user_id),

    -- Character Definition Evolution
    base_definition JSONB, -- Original character bible
    evolved_definition JSONB, -- How character has evolved through usage

    -- Visual Consistency Tracking
    successful_prompts JSONB DEFAULT '[]', -- Prompts that generated consistent results
    failed_prompts JSONB DEFAULT '[]', -- Prompts that failed consistency checks
    optimal_parameters JSONB DEFAULT '{}', -- Best generation parameters for this character

    -- Face/Visual Embeddings (for consistency checking)
    face_embeddings JSONB DEFAULT '[]', -- ArcFace embeddings from successful generations
    style_embeddings JSONB DEFAULT '[]', -- Style vectors for this character

    -- Learning Statistics
    total_generations INTEGER DEFAULT 0,
    consistency_score FLOAT DEFAULT 0.5, -- Overall consistency across all generations
    last_successful_generation TIMESTAMP,

    -- Adaptive Improvements
    enhancement_patterns JSONB DEFAULT '[]', -- Learned enhancements that work for this character
    negative_patterns JSONB DEFAULT '[]', -- Things to avoid for this character

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(character_name, project_id)
);

-- 5. STYLE MEMORY ENGINE - Persistent style learning and application
CREATE TABLE IF NOT EXISTS style_memory_engine (
    style_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    style_name VARCHAR(255) NOT NULL,
    user_id UUID REFERENCES user_creative_dna(user_id),

    -- Style Definition
    style_description TEXT,
    style_tags JSONB DEFAULT '[]', -- ["dramatic_lighting", "cyberpunk", "neon_aesthetic"]

    -- Prompt Engineering
    positive_prompt_patterns JSONB DEFAULT '[]',
    negative_prompt_patterns JSONB DEFAULT '[]',
    parameter_adjustments JSONB DEFAULT '{}',

    -- Learning Data
    successful_applications JSONB DEFAULT '[]', -- When this style worked well
    failed_applications JSONB DEFAULT '[]', -- When this style didn't work

    -- User Feedback Integration
    user_refinements JSONB DEFAULT '[]', -- How user has refined this style
    confidence_score FLOAT DEFAULT 0.5,
    usage_frequency INTEGER DEFAULT 0,

    -- Evolution Tracking
    style_evolution_log JSONB DEFAULT '[]',
    -- Example: [{"date": "2025-12-11", "change": "added warmer tones", "trigger": "user_feedback"}]

    -- Context Applicability
    scene_types JSONB DEFAULT '[]', -- What scenes this style works best for
    character_compatibility JSONB DEFAULT '{}', -- Which characters this style suits

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT true,

    UNIQUE(style_name, user_id)
);

-- 6. WORKFLOW ORCHESTRATION LOG - How Echo coordinates complex workflows
CREATE TABLE IF NOT EXISTS workflow_orchestration_log (
    orchestration_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES user_creative_dna(user_id),
    project_id UUID,

    -- Workflow Context
    workflow_type VARCHAR(100), -- 'character_generation', 'scene_batch', 'project_continuation'
    trigger_source VARCHAR(50), -- 'telegram_command', 'browser_studio', 'scheduled_task'
    initial_request TEXT,

    -- Orchestration Steps
    planned_steps JSONB, -- What Echo planned to do
    executed_steps JSONB, -- What actually happened
    step_results JSONB, -- Results of each step

    -- Decision Making Process
    context_analysis JSONB, -- How Echo analyzed the situation
    decision_reasoning JSONB, -- Why Echo chose this approach
    alternative_approaches JSONB, -- Other options Echo considered

    -- Quality Control Integration
    qc_checkpoints JSONB DEFAULT '[]', -- Quality checks performed during workflow
    adaptive_adjustments JSONB DEFAULT '[]', -- How Echo adapted during execution

    -- Success Metrics
    workflow_success BOOLEAN DEFAULT false,
    completion_time_ms INTEGER,
    user_satisfaction_score FLOAT,
    technical_quality_score FLOAT,

    -- Learning Integration
    lessons_learned JSONB DEFAULT '{}',
    workflow_improvements JSONB DEFAULT '{}',

    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    status VARCHAR(50) DEFAULT 'in_progress'
);

-- 7. ADAPTIVE QUALITY CONTROL - Learning-based QC system
CREATE TABLE IF NOT EXISTS adaptive_quality_control (
    qc_session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    image_path TEXT NOT NULL,
    user_id UUID REFERENCES user_creative_dna(user_id),
    character_id UUID REFERENCES character_consistency_memory(character_id),

    -- Original Generation Context
    original_prompt TEXT,
    generation_parameters JSONB,
    expected_outcome JSONB, -- What was supposed to be generated

    -- QC Analysis Results
    technical_analysis JSONB, -- Face count, anatomy check, quality metrics
    style_consistency_check JSONB, -- How well it matches expected style
    character_consistency_check JSONB, -- How consistent with character definition

    -- Echo's QC Decision
    echo_qc_decision BOOLEAN, -- Pass/Fail decision
    echo_confidence FLOAT, -- Confidence in the decision
    echo_reasoning TEXT, -- Why Echo made this decision

    -- Human Feedback Integration
    user_override BOOLEAN DEFAULT NULL, -- Did user disagree with Echo's decision?
    user_feedback TEXT, -- User's explanation of their override

    -- Adaptive Learning
    learned_adjustments JSONB DEFAULT '{}', -- What Echo learned from this QC session
    prompt_improvements JSONB DEFAULT '{}', -- How to improve prompts for similar cases

    -- QC Evolution
    qc_rule_updates JSONB DEFAULT '[]', -- How QC rules were updated based on this session

    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    was_regenerated BOOLEAN DEFAULT false,
    final_success BOOLEAN DEFAULT NULL -- Final outcome after any regenerations
);

-- ============================================================================
-- INDEXES FOR PERFORMANCE
-- ============================================================================

-- User Creative DNA indexes
CREATE INDEX IF NOT EXISTS idx_user_creative_dna_username ON user_creative_dna(username);
CREATE INDEX IF NOT EXISTS idx_user_creative_dna_updated ON user_creative_dna(updated_at DESC);

-- Project Memory indexes
CREATE INDEX IF NOT EXISTS idx_project_memory_user ON project_memory(user_id);
CREATE INDEX IF NOT EXISTS idx_project_memory_project ON project_memory(project_id);
CREATE INDEX IF NOT EXISTS idx_project_memory_main ON project_memory(is_main_branch, is_active);
CREATE INDEX IF NOT EXISTS idx_project_memory_timestamp ON project_memory(commit_timestamp DESC);

-- Echo Intelligence indexes
CREATE INDEX IF NOT EXISTS idx_echo_intelligence_user ON echo_intelligence(user_id);
CREATE INDEX IF NOT EXISTS idx_echo_intelligence_project ON echo_intelligence(project_id);
CREATE INDEX IF NOT EXISTS idx_echo_intelligence_source ON echo_intelligence(interaction_source);
CREATE INDEX IF NOT EXISTS idx_echo_intelligence_timestamp ON echo_intelligence(timestamp DESC);

-- Character Consistency indexes
CREATE INDEX IF NOT EXISTS idx_character_consistency_project ON character_consistency_memory(project_id);
CREATE INDEX IF NOT EXISTS idx_character_consistency_user ON character_consistency_memory(user_id);
CREATE INDEX IF NOT EXISTS idx_character_consistency_name ON character_consistency_memory(character_name);

-- Style Memory indexes
CREATE INDEX IF NOT EXISTS idx_style_memory_user ON style_memory_engine(user_id);
CREATE INDEX IF NOT EXISTS idx_style_memory_name ON style_memory_engine(style_name);
CREATE INDEX IF NOT EXISTS idx_style_memory_active ON style_memory_engine(is_active);

-- Workflow Orchestration indexes
CREATE INDEX IF NOT EXISTS idx_workflow_orchestration_user ON workflow_orchestration_log(user_id);
CREATE INDEX IF NOT EXISTS idx_workflow_orchestration_status ON workflow_orchestration_log(status);
CREATE INDEX IF NOT EXISTS idx_workflow_orchestration_type ON workflow_orchestration_log(workflow_type);

-- QC indexes
CREATE INDEX IF NOT EXISTS idx_adaptive_qc_user ON adaptive_quality_control(user_id);
CREATE INDEX IF NOT EXISTS idx_adaptive_qc_character ON adaptive_quality_control(character_id);
CREATE INDEX IF NOT EXISTS idx_adaptive_qc_timestamp ON adaptive_quality_control(timestamp DESC);

-- ============================================================================
-- TRIGGERS FOR AUTOMATIC UPDATES
-- ============================================================================

-- Update user_creative_dna.updated_at on changes
CREATE OR REPLACE FUNCTION update_user_creative_dna_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_user_creative_dna_timestamp
    BEFORE UPDATE ON user_creative_dna
    FOR EACH ROW
    EXECUTE FUNCTION update_user_creative_dna_timestamp();

-- Update character_consistency_memory.updated_at on changes
CREATE OR REPLACE FUNCTION update_character_consistency_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_character_consistency_timestamp
    BEFORE UPDATE ON character_consistency_memory
    FOR EACH ROW
    EXECUTE FUNCTION update_character_consistency_timestamp();

-- ============================================================================
-- VIEWS FOR COMMON QUERIES
-- ============================================================================

-- Active projects with latest commits
CREATE OR REPLACE VIEW active_projects_latest AS
SELECT DISTINCT ON (pm.project_id)
    pm.project_id,
    pm.project_name,
    pm.timeline_commit,
    pm.commit_message,
    pm.commit_timestamp,
    ucd.username,
    pm.user_id
FROM project_memory pm
JOIN user_creative_dna ucd ON pm.user_id = ucd.user_id
WHERE pm.is_active = true
ORDER BY pm.project_id, pm.commit_timestamp DESC;

-- User style preferences summary
CREATE OR REPLACE VIEW user_style_preferences AS
SELECT
    ucd.user_id,
    ucd.username,
    ucd.style_signatures,
    COUNT(sme.style_id) as custom_styles_count,
    AVG(sme.confidence_score) as avg_style_confidence,
    ucd.total_projects,
    ucd.total_generations
FROM user_creative_dna ucd
LEFT JOIN style_memory_engine sme ON ucd.user_id = sme.user_id AND sme.is_active = true
GROUP BY ucd.user_id, ucd.username, ucd.style_signatures, ucd.total_projects, ucd.total_generations;

-- Character performance analytics
CREATE OR REPLACE VIEW character_performance_analytics AS
SELECT
    ccm.character_name,
    ccm.project_id,
    ccm.consistency_score,
    ccm.total_generations,
    pm.project_name,
    ucd.username,
    CASE
        WHEN ccm.consistency_score >= 0.9 THEN 'Excellent'
        WHEN ccm.consistency_score >= 0.8 THEN 'Good'
        WHEN ccm.consistency_score >= 0.7 THEN 'Fair'
        ELSE 'Needs Improvement'
    END as consistency_grade
FROM character_consistency_memory ccm
JOIN project_memory pm ON ccm.project_id = pm.project_id AND pm.is_main_branch = true
JOIN user_creative_dna ucd ON ccm.user_id = ucd.user_id;

-- ============================================================================
-- INITIAL DATA SETUP
-- ============================================================================

-- Create default user for testing
INSERT INTO user_creative_dna (username, style_signatures, character_archetypes, narrative_patterns)
VALUES (
    'patrick_vestal',
    '{"lighting": "dramatic_chiaroscuro", "palette": "muted_cyberpunk", "composition": "dynamic_angles"}',
    '[{"type": "mysterious_hacker", "traits": ["cybernetic_enhancements", "determined_expression"]},
      {"type": "fierce_warrior", "traits": ["battle_scars", "intense_gaze"]}]',
    '{"preferred_genres": ["cyberpunk", "urban_fantasy", "slice_of_life"], "story_themes": ["debt_struggle", "character_growth"]}'
) ON CONFLICT (username) DO NOTHING;

-- ============================================================================
-- SCHEMA VALIDATION QUERIES
-- ============================================================================

-- Test that all tables exist and are properly connected
SELECT
    'user_creative_dna' as table_name,
    COUNT(*) as record_count
FROM user_creative_dna
UNION ALL
SELECT
    'project_memory' as table_name,
    COUNT(*) as record_count
FROM project_memory
UNION ALL
SELECT
    'echo_intelligence' as table_name,
    COUNT(*) as record_count
FROM echo_intelligence
UNION ALL
SELECT
    'character_consistency_memory' as table_name,
    COUNT(*) as record_count
FROM character_consistency_memory
UNION ALL
SELECT
    'style_memory_engine' as table_name,
    COUNT(*) as record_count
FROM style_memory_engine
UNION ALL
SELECT
    'workflow_orchestration_log' as table_name,
    COUNT(*) as record_count
FROM workflow_orchestration_log
UNION ALL
SELECT
    'adaptive_quality_control' as table_name,
    COUNT(*) as record_count
FROM adaptive_quality_control;