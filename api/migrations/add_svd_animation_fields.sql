-- Add SVD-specific fields to animation_sequences table
-- Migration: SVD Animation Support
-- Date: 2025-12-19

-- Create animation_sequences table if it doesn't exist
CREATE TABLE IF NOT EXISTS animation_sequences (
    id SERIAL PRIMARY KEY,
    character_id INTEGER REFERENCES character_generations(id),
    animation_type VARCHAR(50) NOT NULL,
    comfyui_prompt_id VARCHAR(255),
    status VARCHAR(50) DEFAULT 'pending',
    output_prefix VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT
);

-- Add SVD-specific columns
ALTER TABLE animation_sequences 
ADD COLUMN IF NOT EXISTS video_format VARCHAR(10) DEFAULT 'mp4',
ADD COLUMN IF NOT EXISTS total_frames INTEGER DEFAULT 25,
ADD COLUMN IF NOT EXISTS frame_count INTEGER,
ADD COLUMN IF NOT EXISTS fps INTEGER DEFAULT 6,
ADD COLUMN IF NOT EXISTS motion_bucket_id INTEGER DEFAULT 127,
ADD COLUMN IF NOT EXISTS augmentation_level FLOAT DEFAULT 0.0,
ADD COLUMN IF NOT EXISTS video_path VARCHAR(512);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_animation_character_id ON animation_sequences(character_id);
CREATE INDEX IF NOT EXISTS idx_animation_status ON animation_sequences(status);
