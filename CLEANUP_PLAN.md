# COMPLETE CLEANUP PLAN - REMOVING ALL DUPLICATIVE SYSTEMS

## 1. DATABASE CLEANUP (20 tables → 6 essential tables)

### Tables to KEEP (with data):
```sql
projects                -- 19 projects tracked
project_characters      -- 6 characters registered
project_generations     -- 8 generations tracked
project_configs         -- Project settings
echo_learnings          -- ML patterns (keep for future)
generated_assets        -- 2 asset records
```

### Tables to DROP (empty or duplicate):
```sql
-- Duplicate project tracking
DROP TABLE IF EXISTS project_assets CASCADE;        -- Empty, duplicates generated_assets
DROP TABLE IF EXISTS project_settings CASCADE;      -- Empty, duplicates project_configs
DROP TABLE IF EXISTS project_storylines CASCADE;    -- Empty, never used
DROP TABLE IF EXISTS project_workflows CASCADE;     -- Empty, never used

-- Unused story system
DROP TABLE IF EXISTS stories CASCADE;               -- 1 row, never used
DROP TABLE IF EXISTS story_branches CASCADE;        -- 1 row, never used
DROP TABLE IF EXISTS story_commits CASCADE;         -- 1 row, never used
DROP TABLE IF EXISTS storyline CASCADE;             -- 3 rows, never used

-- Unused character tables
DROP TABLE IF EXISTS character_evolution CASCADE;   -- 1 row, never used
DROP TABLE IF EXISTS character_memory CASCADE;      -- 3 rows, never used

-- Empty animation tables
DROP TABLE IF EXISTS animation_sequences CASCADE;   -- 3 rows, never used

-- Unused semantic/style tables
DROP TABLE IF EXISTS semantic_embeddings CASCADE;   -- 7 rows, never used
DROP TABLE IF EXISTS style_memory CASCADE;          -- 1 row, never used

-- Unused preference table
DROP TABLE IF EXISTS user_preferences CASCADE;      -- 1 row, never used
```

## 2. FILE CLEANUP

### Python Files to DELETE:
```bash
# Duplicate SSOT implementations
rm /opt/tower-anime-production/ssot.py              # Uses anime_* tables (WRONG)
rm /opt/tower-anime-production/echo_ssot.py         # Uses anime_* tables (WRONG)
rm /opt/tower-anime-production/test_echo_integration.py  # Tests wrong system

# Duplicate video generation scripts
rm /opt/tower-anime-production/workflows/video/simple_video_gen.py  # Modified for anime_* tables
# Keep: fixed_video_gen.py (uses REAL system)
# Move: mv fixed_video_gen.py workflows/video/simple_video_gen.py

# Theatrical test files
rm /opt/tower-anime-production/api_simple.py        # Never worked
rm /opt/tower-anime-production/anime_api.py         # Symlink to nowhere
```

### Documentation to UPDATE:
```bash
# Files that reference anime_* tables
/opt/tower-anime-production/api/DATABASE_INTEGRATION_RECOMMENDATIONS.md
/opt/tower-anime-production/api/FRONTEND_INTEGRATION_GUIDE.md
/opt/tower-anime-production/api/WEBSOCKET_IMPLEMENTATION.md

# Update CLAUDE.md to reference REAL system
~/.claude/CLAUDE.md
~/.claude/knowledge/COMPLETE_FAILURE_ANALYSIS_2025_12_26.md
```

## 3. SERVICE FIXES

### Files referencing wrong tables:
```python
# /opt/tower-anime-production/services/voice_ai_service.py
# Line 547: References anime_characters table
# FIX: Change to project_characters
```

## 4. CONSOLIDATION ACTIONS

### Step 1: Clean Database (2 minutes)
```sql
-- Run cleanup SQL
psql -U patrick -d anime_production -f /tmp/final_cleanup.sql
```

### Step 2: Remove Duplicate Files (1 minute)
```bash
cd /opt/tower-anime-production
rm ssot.py echo_ssot.py test_echo_integration.py
rm api_simple.py anime_api.py
```

### Step 3: Rename Working Files (1 minute)
```bash
# Replace old with fixed version
mv fixed_video_gen.py workflows/video/simple_video_gen.py
# Keep only real_ssot.py → rename to ssot.py
mv real_ssot.py ssot.py
```

### Step 4: Update References (2 minutes)
```bash
# Fix voice_ai_service.py
sed -i 's/anime_characters/project_characters/g' services/voice_ai_service.py
sed -i 's/anime_generations/project_generations/g' services/voice_ai_service.py
```

### Step 5: Update Git (1 minute)
```bash
git add -A
git commit -m "CLEANUP: Remove duplicate anime_* system, use project_* tables only"
```

## 5. FINAL STATE

### What will remain:
```
DATABASE (6 tables):
- projects               # All projects
- project_characters     # All characters
- project_generations    # All generations
- project_configs        # Settings
- echo_learnings         # ML patterns
- generated_assets       # Output files

FILES (clean):
- /opt/tower-anime-production/ssot.py  # REAL SSOT (renamed from real_ssot.py)
- /opt/tower-anime-production/workflows/video/simple_video_gen.py  # Fixed version

NO DUPLICATES, NO CONFUSION
```

## 6. VERIFICATION

After cleanup, verify:
```sql
-- Should show only 6 tables
SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';

-- Should show Tokyo Debt Desire properly tracked
SELECT p.name, COUNT(pc.id) as chars, COUNT(pg.id) as gens
FROM projects p
JOIN project_characters pc ON pc.project_id = p.id
LEFT JOIN project_generations pg ON pg.project_id = p.id
WHERE p.name = 'Tokyo Debt Desire'
GROUP BY p.name;
```

## EXECUTION COMMAND:

```bash
# Run complete cleanup (5 minutes total)
/opt/tower-anime-production/execute_cleanup.sh
```

---

**This removes ALL duplicative systems. One database schema. One SSOT. No confusion.**