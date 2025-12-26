-- Database migration for video generation v2 integration
-- Adds missing columns and tables for multi-project support

-- Add missing columns to video_generations table
ALTER TABLE video_generations
ADD COLUMN IF NOT EXISTS character_id INTEGER,
ADD COLUMN IF NOT EXISTS prompt_id VARCHAR(255),
ADD COLUMN IF NOT EXISTS settings JSONB,
ADD COLUMN IF NOT EXISTS outputs JSONB,
ADD COLUMN IF NOT EXISTS error TEXT;

-- Add foreign key for character
ALTER TABLE video_generations
ADD CONSTRAINT IF NOT EXISTS video_generations_character_id_fkey
FOREIGN KEY (character_id) REFERENCES characters(id);

-- Create project_characters linking table if not exists
CREATE TABLE IF NOT EXISTS project_characters (
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    character_id INTEGER REFERENCES characters(id) ON DELETE CASCADE,
    role VARCHAR(100) DEFAULT 'main',
    added_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (project_id, character_id)
);

-- Add project settings table
CREATE TABLE IF NOT EXISTS project_settings (
    project_id INTEGER PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
    video_format VARCHAR(10) DEFAULT 'mp4',
    default_resolution VARCHAR(20) DEFAULT '512x768',
    default_fps INTEGER DEFAULT 8,
    style_preset VARCHAR(100) DEFAULT 'anime',
    default_checkpoint VARCHAR(500),
    nsfw_allowed BOOLEAN DEFAULT FALSE,
    auto_cleanup_days INTEGER DEFAULT 7,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Add indexes for performance
CREATE INDEX IF NOT EXISTS idx_video_generations_prompt_id ON video_generations(prompt_id);
CREATE INDEX IF NOT EXISTS idx_video_generations_character_id ON video_generations(character_id);
CREATE INDEX IF NOT EXISTS idx_video_generations_project_id ON video_generations(project_id);
CREATE INDEX IF NOT EXISTS idx_video_generations_status ON video_generations(status);
CREATE INDEX IF NOT EXISTS idx_video_generations_created_at ON video_generations(created_at DESC);

-- Create video performance metrics table
CREATE TABLE IF NOT EXISTS video_performance_metrics (
    id SERIAL PRIMARY KEY,
    prompt_id VARCHAR(255) UNIQUE,
    project_id INTEGER REFERENCES projects(id),
    character_id INTEGER REFERENCES characters(id),
    generation_start TIMESTAMP,
    generation_end TIMESTAMP,
    duration_seconds FLOAT,
    gpu_memory_mb FLOAT,
    frame_count INTEGER,
    file_size_mb FLOAT,
    quality_score FLOAT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Create character consistency tracking table
CREATE TABLE IF NOT EXISTS character_consistency_scores (
    id SERIAL PRIMARY KEY,
    character_id INTEGER REFERENCES characters(id),
    project_id INTEGER REFERENCES projects(id),
    test_type VARCHAR(50), -- 'image_grid', 'video_frames', 'cross_scene'
    score FLOAT,
    details JSONB,
    test_date TIMESTAMP DEFAULT NOW()
);

-- Add style_preset column to projects if not exists
ALTER TABLE projects
ADD COLUMN IF NOT EXISTS style_preset VARCHAR(100) DEFAULT 'anime';