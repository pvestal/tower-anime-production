-- Timeline Management Schema for Anime Production
-- Enables parallel universes and branching narratives

-- Timeline branches table
CREATE TABLE IF NOT EXISTS timeline_branches (
    id SERIAL PRIMARY KEY,
    parent_branch_id INTEGER REFERENCES timeline_branches(id),
    branch_name VARCHAR(255) NOT NULL,
    divergence_point TEXT NOT NULL,  -- Description of the decision that created this branch
    divergence_episode_id UUID REFERENCES episodes(id),
    choice_made TEXT,  -- The specific choice that was made
    world_state JSONB NOT NULL DEFAULT '{}',  -- Current state of this timeline's world
    character_states JSONB DEFAULT '{}',  -- Character development in this timeline
    is_canon BOOLEAN DEFAULT false,  -- Is this the main timeline?
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(100) DEFAULT 'system',

    -- Ensure unique branch names per project
    CONSTRAINT unique_branch_name UNIQUE (branch_name)
);

-- Episode-timeline mapping
CREATE TABLE IF NOT EXISTS episode_timelines (
    id SERIAL PRIMARY KEY,
    episode_id UUID REFERENCES episodes(id) ON DELETE CASCADE,
    timeline_branch_id INTEGER REFERENCES timeline_branches(id) ON DELETE CASCADE,
    is_primary BOOLEAN DEFAULT false,  -- Is this the primary version of this episode?
    viewer_choices JSONB DEFAULT '[]',  -- Array of choices made by viewer
    variations JSONB DEFAULT '{}',  -- How this episode differs in this timeline
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Ensure one episode per timeline
    CONSTRAINT unique_episode_timeline UNIQUE (episode_id, timeline_branch_id)
);

-- Character development across timelines
CREATE TABLE IF NOT EXISTS character_timeline_states (
    id SERIAL PRIMARY KEY,
    character_id INTEGER REFERENCES characters(id) ON DELETE CASCADE,
    timeline_branch_id INTEGER REFERENCES timeline_branches(id) ON DELETE CASCADE,
    episode_id UUID REFERENCES episodes(id),
    state_data JSONB NOT NULL,  -- Character state at this point
    personality_shifts JSONB DEFAULT '{}',  -- How character changed
    relationships JSONB DEFAULT '{}',  -- Relationship states
    skills_gained JSONB DEFAULT '[]',  -- New abilities/knowledge
    trauma_events JSONB DEFAULT '[]',  -- Major events affecting character
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Track character per timeline per episode
    CONSTRAINT unique_char_timeline_episode UNIQUE (character_id, timeline_branch_id, episode_id)
);

-- Decision points that can create branches
CREATE TABLE IF NOT EXISTS decision_points (
    id SERIAL PRIMARY KEY,
    episode_id UUID REFERENCES episodes(id) ON DELETE CASCADE,
    scene_id UUID REFERENCES scenes(id),
    decision_description TEXT NOT NULL,
    choices JSONB NOT NULL,  -- Array of possible choices
    default_choice VARCHAR(100),  -- What happens if no choice made
    impact_level VARCHAR(50) DEFAULT 'minor',  -- minor, major, critical
    affects_characters JSONB DEFAULT '[]',  -- Which characters are affected
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Timeline merge points (where branches can reconverge)
CREATE TABLE IF NOT EXISTS timeline_convergence (
    id SERIAL PRIMARY KEY,
    source_branch_id INTEGER REFERENCES timeline_branches(id),
    target_branch_id INTEGER REFERENCES timeline_branches(id),
    convergence_episode_id UUID REFERENCES episodes(id),
    merge_conditions TEXT,  -- What needs to happen for timelines to merge
    is_complete BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Viewer timeline tracking (for interactive viewing)
CREATE TABLE IF NOT EXISTS viewer_timelines (
    id SERIAL PRIMARY KEY,
    viewer_id VARCHAR(100) NOT NULL,  -- Session or user ID
    current_branch_id INTEGER REFERENCES timeline_branches(id),
    choices_made JSONB DEFAULT '[]',
    episodes_watched JSONB DEFAULT '[]',
    last_episode_id UUID REFERENCES episodes(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Echo Brain integration tracking
CREATE TABLE IF NOT EXISTS echo_story_sessions (
    id SERIAL PRIMARY KEY,
    conversation_id VARCHAR(255) NOT NULL,
    project_id INTEGER REFERENCES projects(id),
    timeline_branch_id INTEGER REFERENCES timeline_branches(id),
    context_data JSONB DEFAULT '{}',  -- Context sent to Echo
    echo_response JSONB DEFAULT '{}',  -- Echo's creative output
    parsed_data JSONB DEFAULT '{}',  -- Parsed structure
    success BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_timeline_parent ON timeline_branches(parent_branch_id);
CREATE INDEX IF NOT EXISTS idx_episode_timeline ON episode_timelines(episode_id, timeline_branch_id);
CREATE INDEX IF NOT EXISTS idx_character_timeline ON character_timeline_states(character_id, timeline_branch_id);
CREATE INDEX IF NOT EXISTS idx_decision_episode ON decision_points(episode_id);
CREATE INDEX IF NOT EXISTS idx_viewer_current ON viewer_timelines(viewer_id, current_branch_id);
CREATE INDEX IF NOT EXISTS idx_echo_sessions ON echo_story_sessions(conversation_id, project_id);

-- Create main timeline for existing projects
INSERT INTO timeline_branches (branch_name, divergence_point, world_state, is_canon)
VALUES ('main', 'Original timeline', '{"status": "stable"}', true)
ON CONFLICT (branch_name) DO NOTHING;

-- Function to create a timeline branch
CREATE OR REPLACE FUNCTION create_timeline_branch(
    p_parent_id INTEGER,
    p_decision_point TEXT,
    p_choice TEXT,
    p_episode_id UUID,
    p_world_state JSONB DEFAULT '{}'
) RETURNS INTEGER AS $$
DECLARE
    v_branch_id INTEGER;
    v_branch_name VARCHAR(255);
BEGIN
    -- Generate unique branch name
    v_branch_name := 'branch_' || p_episode_id || '_' || md5(p_choice)::varchar(8);

    -- Insert new branch
    INSERT INTO timeline_branches (
        parent_branch_id,
        branch_name,
        divergence_point,
        divergence_episode_id,
        choice_made,
        world_state
    ) VALUES (
        p_parent_id,
        v_branch_name,
        p_decision_point,
        p_episode_id,
        p_choice,
        p_world_state
    ) RETURNING id INTO v_branch_id;

    -- Copy character states from parent timeline
    INSERT INTO character_timeline_states (character_id, timeline_branch_id, state_data)
    SELECT character_id, v_branch_id, state_data
    FROM character_timeline_states
    WHERE timeline_branch_id = p_parent_id
      AND episode_id = p_episode_id;

    RETURN v_branch_id;
END;
$$ LANGUAGE plpgsql;

-- Function to get timeline history
CREATE OR REPLACE FUNCTION get_timeline_history(p_branch_id INTEGER)
RETURNS TABLE (
    branch_id INTEGER,
    branch_name VARCHAR(255),
    divergence_point TEXT,
    choice_made TEXT,
    depth INTEGER
) AS $$
WITH RECURSIVE timeline_tree AS (
    SELECT
        id,
        branch_name,
        divergence_point,
        choice_made,
        parent_branch_id,
        0 as depth
    FROM timeline_branches
    WHERE id = p_branch_id

    UNION ALL

    SELECT
        tb.id,
        tb.branch_name,
        tb.divergence_point,
        tb.choice_made,
        tb.parent_branch_id,
        tt.depth + 1
    FROM timeline_branches tb
    JOIN timeline_tree tt ON tb.id = tt.parent_branch_id
)
SELECT
    id as branch_id,
    branch_name,
    divergence_point,
    choice_made,
    depth
FROM timeline_tree
ORDER BY depth DESC;
$$ LANGUAGE SQL;

-- View for timeline visualization
CREATE OR REPLACE VIEW timeline_tree_view AS
WITH RECURSIVE tree AS (
    SELECT
        id,
        branch_name,
        parent_branch_id,
        divergence_point,
        is_canon,
        0 as level,
        ARRAY[id] as path
    FROM timeline_branches
    WHERE parent_branch_id IS NULL

    UNION ALL

    SELECT
        tb.id,
        tb.branch_name,
        tb.parent_branch_id,
        tb.divergence_point,
        tb.is_canon,
        t.level + 1,
        t.path || tb.id
    FROM timeline_branches tb
    JOIN tree t ON tb.parent_branch_id = t.id
)
SELECT * FROM tree ORDER BY path;