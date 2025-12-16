# Git Workflow for Project-Agnostic Anime Production System

## Branch Structure

```
main                    # Production-ready releases
├── development        # Integration branch for features
├── feature/*          # New features and enhancements
│   ├── feature/agnostic-architecture-v2  # Current: Clean architecture
│   ├── feature/echo-orchestration-engine  # Echo AI improvements
│   └── feature/anime-system-redesign      # System overhaul
└── hotfix/*           # Emergency production fixes
```

## Commit Convention

We follow conventional commits for clear history:

```bash
feat:     # New features
fix:      # Bug fixes
docs:     # Documentation only
style:    # Code style changes (formatting)
refactor: # Code restructuring
perf:     # Performance improvements
test:     # Test additions/changes
chore:    # Build/tooling changes
```

### Examples:
```bash
feat: Add project template system for rapid bootstrapping
fix: Resolve Echo AI cross-project contamination
docs: Update README with agnostic architecture guide
refactor: Extract genre patterns to shared library
perf: Optimize CLIP consistency checking with caching
```

## Project Isolation Rules

### What to Commit:
✅ System core files (`/src/`, `/api/`)
✅ Templates (`/system/templates/`)
✅ Genre libraries (`/system/genre_libraries/`)
✅ Documentation (`*.md`)
✅ Configuration (`/system/core.json`)

### What NOT to Commit:
❌ Project-specific renders (`/projects/*/rendered/`)
❌ Echo learning data (`/projects/*/echo_learning/decisions.json`)
❌ Generated images (`*.png`, `*.jpg`)
❌ Temporary files (`*.backup`, `*.log`)

## Workflow Commands

### Starting New Feature:
```bash
git checkout development
git pull origin development
git checkout -b feature/your-feature-name
```

### Daily Work:
```bash
# Check what changed
git status

# Stage specific files (avoid -A for safety)
git add src/new_feature.py
git add system/templates/new_template.json

# Commit with clear message
git commit -m "feat: Add cyberpunk rain effect pattern"

# Push to remote
git push origin feature/your-feature-name
```

### Merging Feature:
```bash
# Update your feature branch
git checkout feature/your-feature-name
git rebase development

# Push and create PR
git push origin feature/your-feature-name
# Create PR on GitHub/GitLab

# After approval, merge
git checkout development
git merge --no-ff feature/your-feature-name
git push origin development
```

## Project-Specific Git Usage

### Creating New Project:
```bash
# Projects are isolated - no git needed inside project dirs
python3 src/project_agnostic_core.py \
  --create "new_project" \
  --template "cyberpunk_action"

# The project config is tracked, but not renders
git add projects/new_project/project_config.json
git add projects/new_project/project_state.json
git commit -m "feat: Initialize new_project with cyberpunk template"
```

### Sharing Genre Patterns:
```bash
# After successful project patterns
python3 contribute_patterns.py \
  --project cyberpunk_goblin_slayer \
  --pattern lighting

# Commit the updated library
git add system/genre_libraries/cyberpunk.json
git commit -m "feat: Add neon rain patterns from goblin slayer"
```

## Pre-commit Hooks

The system runs automatic checks before commits:

1. **Python Syntax**: All `.py` files validated
2. **JSON Validation**: Templates and configs checked
3. **Service Health**: API and ComfyUI running
4. **Test Suite**: Core functionality tested
5. **File Size**: Prevents large media commits

## Backup Strategy

### Before Major Changes:
```bash
# Tag current stable state
git tag -a v2.0.0-stable -m "Stable before major refactor"
git push origin v2.0.0-stable

# Create backup branch
git checkout -b backup/pre-refactor-$(date +%Y%m%d)
git push origin backup/pre-refactor-$(date +%Y%m%d)
```

### Project Archival:
```bash
# Archive completed project (outside git)
tar -czf archives/cyberpunk_goblin_slayer_$(date +%Y%m%d).tar.gz \
  projects/cyberpunk_goblin_slayer/

# Remove renders from git tracking
git rm -r --cached projects/cyberpunk_goblin_slayer/rendered/
git commit -m "chore: Archive cyberpunk project renders"
```

## Collaboration Guidelines

### Pull Request Template:
```markdown
## Changes
- Brief description of what changed

## Type
- [ ] feat: New feature
- [ ] fix: Bug fix
- [ ] refactor: Code improvement
- [ ] docs: Documentation

## Testing
- [ ] Ran test_isolation.py
- [ ] Verified no cross-contamination
- [ ] Tested with existing projects

## Projects Affected
- [ ] Core system only
- [ ] Templates modified
- [ ] Genre libraries updated
```

## Emergency Procedures

### Reverting Bad Commit:
```bash
# Revert specific commit
git revert <commit-hash>

# Or reset to known good state
git reset --hard <good-commit-hash>
```

### Recovering Deleted Project:
```bash
# Find when it was deleted
git log --diff-filter=D --summary | grep "delete.*projects/"

# Restore from commit
git checkout <commit-before-deletion> -- projects/lost_project/
```

## Version Tags

We use semantic versioning:

```bash
# Major: Breaking changes
git tag -a v3.0.0 -m "Breaking: New architecture"

# Minor: New features
git tag -a v2.1.0 -m "Feature: Template system"

# Patch: Bug fixes
git tag -a v2.0.1 -m "Fix: Echo isolation bug"

git push origin --tags
```

## Current State (2025-12-16)

- **Current Branch**: feature/agnostic-architecture-v2
- **Latest Commit**: 4002fbc - Architecture migration v2.0
- **System Version**: 2.0.0
- **Architecture**: Project-agnostic with isolation

## Quick Reference

```bash
# See what's staged
git status

# View history
git log --oneline -10

# Check branches
git branch -a

# Push current branch
git push origin HEAD

# Update from remote
git pull origin $(git branch --show-current)
```

---

Remember: **Projects are isolated, system is shared**. Commit accordingly.