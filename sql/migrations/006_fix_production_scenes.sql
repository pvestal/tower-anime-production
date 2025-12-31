-- Fix production_scenes table with correct foreign key types

-- Drop the failed table if it partially exists
DROP TABLE IF EXISTS production_scenes CASCADE;

-- 4. Production Scenes: The "Shot List" (Fixed)
CREATE TABLE production_scenes (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES anime_projects(id) ON DELETE CASCADE,
    episode_id UUID REFERENCES episodes(id) ON DELETE CASCADE,
    scene_number INTEGER,
    semantic_action_id INTEGER REFERENCES semantic_actions(id),
    style_angle_id INTEGER REFERENCES style_angle_library(id),
    duration_seconds INTEGER,
    character_ids INTEGER[], -- Array of character IDs
    status VARCHAR(20) DEFAULT 'pending', -- 'pending', 'generating', 'needs_review', 'approved'
    notes TEXT,
    generated_video_path TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Performance Indexes
CREATE INDEX idx_production_scenes_status ON production_scenes(status);
CREATE INDEX idx_production_scenes_project ON production_scenes(project_id, episode_id);

-- Comments
COMMENT ON TABLE production_scenes IS 'Shot list linking narrative scenes to technical generation';