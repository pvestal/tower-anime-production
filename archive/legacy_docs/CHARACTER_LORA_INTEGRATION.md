# Character LoRA Integration Documentation

## Overview
This document explains how character-specific LoRA models are integrated into the anime production system to generate consistent character appearances.

## Architecture Flow

### 1. Database Structure
```
ai_models (stores LoRA files)
├── id
├── name (e.g., "mei_working_v1")
├── type ("lora")
├── model_path (e.g., "mei_working_v1.safetensors")
└── file_path (full path: "/mnt/1TB-storage/models/loras/mei_working_v1.safetensors")

generation_profiles (links characters to LoRAs)
├── id
├── name (e.g., "tokyo_debt_realism")
├── checkpoint_id → ai_models (base model)
├── lora_id → ai_models (character LoRA)
└── video_workflow_template_id → video_workflow_templates

characters
├── id
├── name (e.g., "Mei Kobayashi")
├── project_id → projects
└── description
```

### 2. Workflow Templates
All workflows in `video_workflow_templates` table include a LoraLoader node (node ID "10"):
```json
{
  "10": {
    "inputs": {
      "lora_name": "mei_working_v1.safetensors",
      "strength_model": 0.8,
      "strength_clip": 0.8,
      "model": ["4", 0],
      "clip": ["4", 1]
    },
    "class_type": "LoraLoader",
    "_meta": {"title": "Load LoRA"}
  }
}
```

### 3. API Flow (`/api/anime/characters/{id}/generate`)

1. **Character Lookup**: Get character details from database
2. **Profile Selection**: Choose generation profile based on project
   - Tokyo Debt Desire → "tokyo_debt_realism"
   - Cyberpunk Goblin → "cyberpunk_anime"
3. **LoRA Injection**: API dynamically updates workflow with character's LoRA
4. **ComfyUI Submission**: Send workflow with correct LoRA to ComfyUI
5. **Generation**: ComfyUI applies LoRA to base model for consistent character

### 4. API Implementation Details

The key function is `generate_with_fixed_animatediff_workflow()` in `/opt/tower-anime-production/api/main.py`:

```python
# Lines 519-524: Dynamic LoRA injection
if node.get("class_type") == "LoraLoader" and lora_name:
    workflow[node_id]["inputs"]["lora_name"] = lora_name
    logger.info(f"Updated LoRA to '{lora_name}'")
```

### 5. File Locations

- **LoRA Models**: `/mnt/1TB-storage/models/loras/`
  - Currently only `mei_working_v1.safetensors` (18MB) exists
  - Other characters need LoRA training

- **Generated Output**: `/mnt/1TB-storage/ComfyUI/output/`
  - Images: `anime_image_{timestamp}_00001.png`
  - Videos: `anime_video_{timestamp}_00001_.mp4`

## Current Status

### ✅ Working
- Mei Kobayashi generation with her specific LoRA
- Database SSOT for all configuration
- Dynamic LoRA injection in workflows
- API endpoints for character generation

### ⚠️ Limitations
- Only Mei has a trained LoRA model
- Other characters (Rina, Yuki, Takeshi, Goblin Slayer) need LoRA training
- Without character-specific LoRAs, other characters use base model only

## Testing

### Integration Test
```bash
python3 /tmp/test_mei_lora_generation.py
```

### All Characters Test
```bash
python3 /tmp/test_all_characters.py
```

## Next Steps

1. **Train LoRAs for remaining characters**:
   - Rina Suzuki (elegant, supportive)
   - Yuki Tanaka (energetic, youthful)
   - Takeshi Sato (authoritative, stern)
   - Goblin Slayer (armored, cyberpunk)

2. **Create character reference sheets**:
   - Collect training images for each character
   - Define consistent visual features
   - Document personality traits for poses

3. **Implement LoRA training pipeline**:
   - Use Kohya_ss or similar for LoRA training
   - Automate training workflow
   - Quality validation system

## Troubleshooting

### LoRA Not Applied
1. Check workflow has LoraLoader node: `SELECT workflow_template FROM video_workflow_templates`
2. Verify LoRA file exists: `ls /mnt/1TB-storage/models/loras/`
3. Check API logs: `sudo journalctl -u tower-anime-production -f`

### Wrong Character Generated
1. Verify correct LoRA in profile: `SELECT * FROM generation_profiles WHERE name = 'profile_name'`
2. Check character ID mapping: `SELECT * FROM characters WHERE name = 'character_name'`
3. Ensure LoRA strength is sufficient (0.8 recommended)

## SQL Queries

### View character-profile-LoRA mapping
```sql
SELECT
    c.name as character,
    p.name as project,
    gp.name as profile,
    m.model_path as lora_file
FROM characters c
JOIN projects p ON c.project_id = p.id
LEFT JOIN generation_profiles gp ON gp.name = CASE
    WHEN p.name LIKE '%Tokyo%' THEN 'tokyo_debt_realism'
    WHEN p.name LIKE '%Cyberpunk%' THEN 'cyberpunk_anime'
    ELSE 'tokyo_debt_realism'
END
LEFT JOIN ai_models m ON gp.lora_id = m.id;
```

### Check workflow LoraLoader nodes
```sql
SELECT
    name,
    workflow_template->'10'->>'class_type' as node_type,
    workflow_template->'10'->'inputs'->>'lora_name' as default_lora
FROM video_workflow_templates
WHERE workflow_template->'10' IS NOT NULL;
```

## Architecture Diagram

```
User Request
    ↓
API Endpoint (/api/anime/characters/{id}/generate)
    ↓
Character Lookup (database)
    ↓
Profile Selection (based on project)
    ↓
Workflow Loading (from video_workflow_templates)
    ↓
LoRA Injection (dynamic update)
    ↓
ComfyUI Submission
    ↓
Generation with Character LoRA
    ↓
Output (consistent character appearance)
```

---

Last Updated: 2025-01-02
Author: Claude with Tower System Integration