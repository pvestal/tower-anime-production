-- Character Consistency Schema for SQLite (Phase 1)
-- Simplified version compatible with SQLite fallback database

-- Character definitions and canonical references
CREATE TABLE IF NOT EXISTS characters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    project_id INTEGER,
    description TEXT,
    visual_traits TEXT, -- JSON as TEXT
    canonical_hash TEXT,
    status TEXT DEFAULT 'draft',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata TEXT -- JSON as TEXT
);

-- Character consistency anchors (reference poses and expressions)
CREATE TABLE IF NOT EXISTS character_anchors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id INTEGER REFERENCES characters(id) ON DELETE CASCADE,
    anchor_type TEXT NOT NULL,
    anchor_name TEXT NOT NULL,
    description TEXT,
    image_path TEXT NOT NULL,
    face_embedding BLOB,
    clip_embedding BLOB,
    generation_params TEXT, -- JSON as TEXT
    quality_score REAL,
    aesthetic_score REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata TEXT -- JSON as TEXT
);

-- Face embeddings for consistency validation
CREATE TABLE IF NOT EXISTS face_embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id INTEGER REFERENCES characters(id) ON DELETE CASCADE,
    anchor_id INTEGER REFERENCES character_anchors(id) ON DELETE CASCADE,
    embedding_type TEXT NOT NULL,
    embedding_vector BLOB NOT NULL,
    face_bbox TEXT, -- JSON as TEXT
    face_landmarks TEXT, -- JSON as TEXT
    confidence_score REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Character generation results and consistency scores
CREATE TABLE IF NOT EXISTS generation_consistency (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id INTEGER REFERENCES characters(id) ON DELETE CASCADE,
    generation_request_id TEXT,
    output_image_path TEXT NOT NULL,
    face_similarity_score REAL,
    style_similarity_score REAL,
    aesthetic_score REAL,
    overall_consistency_score REAL,
    quality_gates_passed BOOLEAN DEFAULT 0,
    validation_status TEXT DEFAULT 'pending',
    improvement_suggestions TEXT, -- JSON array as TEXT
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata TEXT -- JSON as TEXT
);

-- Quality gate configurations and thresholds
CREATE TABLE IF NOT EXISTS quality_gates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gate_name TEXT UNIQUE NOT NULL,
    gate_type TEXT NOT NULL,
    threshold_value REAL NOT NULL,
    is_active BOOLEAN DEFAULT 1,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata TEXT -- JSON as TEXT
);

-- Character style consistency tracking
CREATE TABLE IF NOT EXISTS style_consistency (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id INTEGER REFERENCES characters(id) ON DELETE CASCADE,
    style_element TEXT NOT NULL,
    reference_description TEXT,
    validation_prompt TEXT,
    consistency_threshold REAL DEFAULT 0.85,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- IPAdapter and InstantID workflow configurations
CREATE TABLE IF NOT EXISTS ipadapter_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    config_name TEXT UNIQUE NOT NULL,
    character_id INTEGER REFERENCES characters(id),
    model_path TEXT NOT NULL,
    weight REAL DEFAULT 1.0,
    start_at REAL DEFAULT 0.0,
    end_at REAL DEFAULT 1.0,
    faceid_v2 BOOLEAN DEFAULT 0,
    weight_v2 REAL DEFAULT 1.0,
    combine_embeds TEXT DEFAULT 'concat',
    embeds_scaling TEXT DEFAULT 'V only',
    is_active BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    config_data TEXT -- JSON as TEXT
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
INSERT OR IGNORE INTO quality_gates (gate_name, gate_type, threshold_value, description) VALUES
('face_similarity_minimum', 'face_similarity', 0.70, 'Minimum face cosine similarity threshold'),
('aesthetic_score_minimum', 'aesthetic_score', 5.5, 'Minimum LAION aesthetic predictor score'),
('style_clip_minimum', 'style_consistency', 0.85, 'Minimum CLIP similarity for style adherence'),
('overall_consistency_minimum', 'overall_consistency', 0.75, 'Minimum overall consistency score for approval');