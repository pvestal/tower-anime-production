-- Migration 004: Multi-user support with content gating
-- Adds studio_users, user_project_access, share_links, review_comments tables
-- Normalizes content_rating values and seeds initial profiles

-- ═══════════════════════════════════════════════════════════════
-- Studio Users (bridges tower-auth to anime-studio)
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS studio_users (
    id SERIAL PRIMARY KEY,
    auth_user_id VARCHAR(16) UNIQUE,        -- from tower-auth (NULL for local-only profiles)
    display_name VARCHAR(255) NOT NULL,
    email VARCHAR(255),
    avatar_url TEXT,
    pin_hash VARCHAR(255),                  -- bcrypt hash for local profile picker
    role VARCHAR(20) NOT NULL DEFAULT 'viewer',  -- admin, creator, viewer
    max_rating VARCHAR(10) NOT NULL DEFAULT 'PG', -- G, PG, PG-13, R, NC-17, XXX
    ui_mode VARCHAR(10) NOT NULL DEFAULT 'easy',
    onboarded BOOLEAN NOT NULL DEFAULT FALSE,
    preferences JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    last_login TIMESTAMP
);

-- ═══════════════════════════════════════════════════════════════
-- Explicit project access (optional allowlist)
-- No rows = rating-only filter; rows = intersect with rating
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS user_project_access (
    user_id INTEGER NOT NULL REFERENCES studio_users(id) ON DELETE CASCADE,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    access_level VARCHAR(20) NOT NULL DEFAULT 'view',  -- view, edit, admin
    granted_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (user_id, project_id)
);

-- ═══════════════════════════════════════════════════════════════
-- Share links (Google login required to use)
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS share_links (
    id SERIAL PRIMARY KEY,
    token VARCHAR(64) NOT NULL UNIQUE,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    created_by INTEGER NOT NULL REFERENCES studio_users(id),
    label VARCHAR(255),
    max_rating VARCHAR(10) DEFAULT 'PG-13',
    expires_at TIMESTAMP NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ═══════════════════════════════════════════════════════════════
-- Reviewer comments on shared projects
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS review_comments (
    id SERIAL PRIMARY KEY,
    share_link_id INTEGER REFERENCES share_links(id) ON DELETE SET NULL,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    user_id INTEGER REFERENCES studio_users(id),
    reviewer_name VARCHAR(255),
    comment_text TEXT NOT NULL,
    asset_type VARCHAR(20),   -- image, video, scene, episode, general
    asset_id VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW()
);

-- ═══════════════════════════════════════════════════════════════
-- Indexes
-- ═══════════════════════════════════════════════════════════════
CREATE INDEX IF NOT EXISTS idx_studio_users_auth ON studio_users(auth_user_id);
CREATE INDEX IF NOT EXISTS idx_studio_users_role ON studio_users(role);
CREATE INDEX IF NOT EXISTS idx_share_links_token ON share_links(token);
CREATE INDEX IF NOT EXISTS idx_share_links_project ON share_links(project_id);
CREATE INDEX IF NOT EXISTS idx_review_comments_project ON review_comments(project_id);
CREATE INDEX IF NOT EXISTS idx_review_comments_share ON review_comments(share_link_id);

-- ═══════════════════════════════════════════════════════════════
-- Normalize existing content ratings
-- ═══════════════════════════════════════════════════════════════
UPDATE projects SET content_rating = 'NC-17' WHERE content_rating ILIKE '%TV-MA%' OR content_rating ILIKE '%18+%';
UPDATE projects SET content_rating = 'XXX'   WHERE content_rating ILIKE '%XXX%' OR content_rating ILIKE '%Adults Only%';
UPDATE projects SET content_rating = 'R'     WHERE content_rating ILIKE '%explicit%';
UPDATE projects SET content_rating = 'PG'    WHERE content_rating ILIKE '%PG%' AND content_rating NOT ILIKE '%PG-13%';
-- Unrated projects default to R (conservative)
UPDATE projects SET content_rating = 'R'     WHERE content_rating IS NULL OR content_rating = '';

-- ═══════════════════════════════════════════════════════════════
-- Seed Patrick as admin + kid profile
-- ═══════════════════════════════════════════════════════════════
INSERT INTO studio_users (display_name, role, max_rating, ui_mode, onboarded)
VALUES ('Patrick', 'admin', 'XXX', 'advanced', TRUE)
ON CONFLICT DO NOTHING;

INSERT INTO studio_users (display_name, role, max_rating, ui_mode)
VALUES ('Kid', 'viewer', 'PG', 'easy')
ON CONFLICT DO NOTHING;
