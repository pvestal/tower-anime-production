# SSOT System Documentation (CLEANED UP)

## Single Source Files (NO DUPLICATES)

### Core SSOT System
- **File**: `/opt/tower-anime-production/ssot.py`
- **Purpose**: Single source of truth for all character and generation tracking

### Generation Script
- **File**: `/opt/tower-anime-production/generate_video_with_ssot.py`
- **Purpose**: Uses SSOT to generate videos with consistent characters

## Database Schema (anime_production)

### Tables Used
1. **projects** - Anime projects
2. **characters** - Character definitions with appearance_data
3. **project_generations** - Tracks all generations
4. **generation_styles** - Style configurations
5. **system_config** - System-wide settings

## Key Features

### Character Consistency
- Fixed seed per character (stored in characters.generation_seed)
- Body specifications locked in appearance_data
- Consistent prompt building from SSOT

### Methods in ssot.py
- `register_project()` - Get or create project
- `register_character()` - Get or create character
- `get_character_seed()` - Get consistent seed for character
- `get_body_specs()` - Get body specifications
- `build_consistent_prompt()` - Build prompt with all body parts
- `start_generation()` - Track generation start
- `complete_generation()` - Track generation completion

## Usage

```python
from ssot import RealSSoT

ssot = RealSSoT()

# Get character with consistency
char_id = ssot.register_character(project_id, character_data)
seed = ssot.get_character_seed(char_id)
prompt = ssot.build_consistent_prompt(char_id)

# Track generation
gen_id = ssot.start_generation(project_id, char_id, prompt)
# ... do generation ...
ssot.complete_generation(gen_id, output_path, quality_score)

ssot.close()
```

## Character IDs (Current)
- ID 3: Raze (Cyberpunk Goblin Slayer)
- ID 4: Kai Nakamura (Cyberpunk Goblin Slayer)
- ID 5: Xyrax (Cyberpunk Goblin Slayer)
- ID 7: Hiroshi Yamamoto (Cyberpunk Goblin Slayer)
- ID 8: Mei Kobayashi (Tokyo Debt Desire)
- ID 9: Rina Suzuki (Tokyo Debt Desire)
- ID 10: Yuki Tanaka (Tokyo Debt Desire)
- ID 11: Takeshi Sato (Tokyo Debt Desire)

## Testing

```bash
# Generate video with consistent character
python3 generate_video_with_ssot.py /path/to/character.json 1.0 8
```

## IMPORTANT
- NO duplicate SSOT files
- NO conflicting implementations
- ONE database, ONE set of tables
- Character consistency through fixed seeds and body specs