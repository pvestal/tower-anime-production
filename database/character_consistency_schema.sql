-- Character Consistency Schema for Phase 1
-- Supports IPAdapter Plus and InstantID character consistency

-- Character definitions and canonical references
CREATE TABLE IF NOT EXISTS characters (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    project_id INTEGER,
    description TEXT,
    visual_traits JSONB, -- Physical characteristics, style, etc.
    canonical_hash VARCHAR(64), -- Hash of canonical reference data
    status VARCHAR(50) DEFAULT 'draft', -- draft, approved, archived
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB
);

-- Character consistency anchors (reference poses and expressions)
CREATE TABLE IF NOT EXISTS character_anchors (
    id SERIAL PRIMARY KEY,
    character_id INTEGER REFERENCES characters(id) ON DELETE CASCADE,
    anchor_type VARCHAR(50) NOT NULL, -- pose_reference, expression_reference, style_anchor
    anchor_name VARCHAR(255) NOT NULL, -- front_view, side_view, happy_expression, etc.
    description TEXT,
    image_path TEXT NOT NULL,
    face_embedding BYTEA, -- InsightFace ArcFace embedding
    clip_embedding BYTEA, -- CLIP embedding for style consistency
    generation_params JSONB, -- ComfyUI parameters used
    quality_score FLOAT, -- Overall quality assessment
    aesthetic_score FLOAT, -- LAION aesthetic score
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB
);

-- Face embeddings for consistency validation
CREATE TABLE IF NOT EXISTS face_embeddings (
    id SERIAL PRIMARY KEY,
    character_id INTEGER REFERENCES characters(id) ON DELETE CASCADE,
    anchor_id INTEGER REFERENCES character_anchors(id) ON DELETE CASCADE,
    embedding_type VARCHAR(50) NOT NULL, -- arcface, facenet, insightface
    embedding_vector BYTEA NOT NULL, -- Serialized numpy array
    face_bbox JSONB, -- Bounding box coordinates
    face_landmarks JSONB, -- Facial landmark points
    confidence_score FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Character generation results and consistency scores
CREATE TABLE IF NOT EXISTS generation_consistency (
    id SERIAL PRIMARY KEY,
    character_id INTEGER REFERENCES characters(id) ON DELETE CASCADE,
    generation_request_id VARCHAR(255),
    output_image_path TEXT NOT NULL,
    face_similarity_score FLOAT, -- Cosine similarity against canonical faces
    style_similarity_score FLOAT, -- CLIP similarity for style
    aesthetic_score FLOAT, -- LAION aesthetic predictor
    overall_consistency_score FLOAT, -- Combined consistency metric
    quality_gates_passed BOOLEAN DEFAULT FALSE,
    validation_status VARCHAR(50) DEFAULT 'pending', -- pending, approved, rejected
    improvement_suggestions TEXT[],
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB
);

-- Quality gate configurations and thresholds
CREATE TABLE IF NOT EXISTS quality_gates (
    id SERIAL PRIMARY KEY,
    gate_name VARCHAR(255) UNIQUE NOT NULL,
    gate_type VARCHAR(100) NOT NULL, -- face_similarity, aesthetic_score, style_consistency
    threshold_value FLOAT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB
);

-- Character style consistency tracking
CREATE TABLE IF NOT EXISTS style_consistency (
    id SERIAL PRIMARY KEY,
    character_id INTEGER REFERENCES characters(id) ON DELETE CASCADE,
    style_element VARCHAR(100) NOT NULL, -- hair_color, eye_shape, clothing_style
    reference_description TEXT,
    validation_prompt TEXT, -- Prompt to validate this style element
    consistency_threshold FLOAT DEFAULT 0.85,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- IPAdapter and InstantID workflow configurations
CREATE TABLE IF NOT EXISTS ipadapter_configs (
    id SERIAL PRIMARY KEY,
    config_name VARCHAR(255) UNIQUE NOT NULL,
    character_id INTEGER REFERENCES characters(id),
    model_path TEXT NOT NULL, -- IPAdapter model file
    weight FLOAT DEFAULT 1.0,
    start_at FLOAT DEFAULT 0.0,
    end_at FLOAT DEFAULT 1.0,
    faceid_v2 BOOLEAN DEFAULT FALSE,
    weight_v2 FLOAT DEFAULT 1.0,
    combine_embeds VARCHAR(50) DEFAULT 'concat', -- concat, add, subtract, average
    embeds_scaling VARCHAR(50) DEFAULT 'V only', -- V only, K+V, K+V w/ C penalty, K+mean(V) w/ C penalty
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    config_data JSONB
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_characters_name ON characters(name);
CREATE INDEX IF NOT EXISTS idx_characters_project_id ON characters(project_id);
CREATE INDEX IF NOT EXISTS idx_character_anchors_character_id ON character_anchors(character_id);
CREATE INDEX IF NOT EXISTS idx_character_anchors_type ON character_anchors(anchor_type);
CREATE INDEX IF NOT EXISTS idx_face_embeddings_character_id ON face_embeddings(character_id);
CREATE INDEX IF NOT EXISTS idx_generation_consistency_character_id ON generation_consistency(character_id);
CREATE INDEX IF NOT EXISTS idx_generation_consistency_score ON generation_consistency(overall_consistency_score);
CREATE INDEX IF NOT EXISTS idx_quality_gates_active ON quality_gates(is_active);
CREATE INDEX IF NOT EXISTS idx_style_consistency_character_id ON style_consistency(character_id);

-- Insert default quality gates
INSERT INTO quality_gates (gate_name, gate_type, threshold_value, description) VALUES
('face_similarity_minimum', 'face_similarity', 0.70, 'Minimum face cosine similarity threshold'),
('aesthetic_score_minimum', 'aesthetic_score', 5.5, 'Minimum LAION aesthetic predictor score'),
('style_clip_minimum', 'style_consistency', 0.85, 'Minimum CLIP similarity for style adherence'),
('overall_consistency_minimum', 'overall_consistency', 0.75, 'Minimum overall consistency score for approval')
ON CONFLICT (gate_name) DO NOTHING;

-- Create triggers for updated_at
CREATE TRIGGER update_characters_updated_at BEFORE UPDATE ON characters
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO patrick;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO patrick;