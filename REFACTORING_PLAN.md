# Tower Anime Production - Refactoring Plan

## Problem Statement
Multiple duplicate files created through browser coder sessions, causing confusion and maintenance issues.

## Current Duplicates

### 1. Quality Metrics
- **Keep**: `services/quality_metrics_v2.py` (most recent, has QC-SSOT integration)
- **Remove**:
  - `anime-system-modular/backend/services/quality_metrics.py`
  - Archive versions in `/archive/root_duplicates/`

### 2. Character Consistency
- **Keep**: `services/character_consistency_v2.py` (most recent)
- **Remove**:
  - `anime-system-modular/backend/services/character_consistency.py`
  - `api/character_consistency_*.py` (5 files)
  - `src/character_consistency*.py` (4 files)
  - Archive versions

### 3. Secured API
- **Keep**: `api/secured_api_refactored.py` (has SQLAlchemy integration)
- **Rename**: to `api/secured_api.py` after backup
- **Remove**: Original `api/secured_api.py` (in-memory version)

## Refactoring Steps

### Phase 1: Consolidate Core Services
1. Rename `quality_metrics_v2.py` → `quality_metrics.py`
2. Rename `character_consistency_v2.py` → `character_consistency.py`
3. Update all imports across the codebase

### Phase 2: Clean API Layer
1. Backup current `secured_api.py`
2. Rename `secured_api_refactored.py` → `secured_api.py`
3. Remove duplicate character consistency endpoints
4. Consolidate into single API router

### Phase 3: Remove Duplicates
1. Archive old files to `/archive/pre-refactor-2025-12-31/`
2. Delete duplicate implementations
3. Update imports and dependencies

### Phase 4: Standardize Structure
```
/opt/tower-anime-production/
├── api/
│   ├── secured_api.py         # Main API with SQLAlchemy
│   └── routes/                 # Organized route modules
├── services/
│   ├── quality_metrics.py     # QC-SSOT system
│   └── character_consistency.py # Character tracking
├── workflows/
│   └── video/                  # Video generation workflows
└── archive/                    # Historical code
```

## Import Updates Required

### Before:
```python
from services.quality_metrics_v2 import QualityMetrics
from api.secured_api import app
from src.character_consistency import CharacterConsistency
```

### After:
```python
from services.quality_metrics import QualityMetrics
from api.secured_api import app
from services.character_consistency import CharacterConsistency
```

## Testing Plan
1. Verify all imports work after renaming
2. Test API endpoints still function
3. Confirm QC-SSOT integration intact
4. Validate character consistency tracking

## Timeline
- Estimated: 1-2 hours for complete refactoring
- Risk: Low (mostly file organization)
- Benefit: Cleaner codebase, easier maintenance