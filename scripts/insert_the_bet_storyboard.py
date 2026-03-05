#!/usr/bin/env python3
"""Insert 'The Bet' storyboard into anime-studio Postgres DB.

Maps storyboard JSON to the real scenes/shots schema for project_id=24
(Tokyo Debt Desire). Adds missing columns via ALTER TABLE if needed.

Usage:
    # Print SQL only (review before running):
    python3 scripts/insert_the_bet_storyboard.py

    # Execute against DB:
    python3 scripts/insert_the_bet_storyboard.py --execute
"""

import json
import sys

PROJECT_ID = 24

# ---------------------------------------------------------------------------
# Storyboard data — from the scene design for "The Bet"
# Placeholders like {ACTION_DETAIL} are LITERAL TEXT, not to be expanded here.
# ---------------------------------------------------------------------------

SCENE_DATA = {
    "scene_number": 1,
    "title": "The Bet",
    "location": "cramped Tokyo apartment, living room",
    "time_of_day": "evening",
    "mood": "warm overhead light, cluttered kotatsu table, beer cans, convenience store bags",
    "emotional_tone": "comedic",
    "narrative_text": (
        "Roommates Yui and Saki are both home when Kenji stumbles in after a "
        "failed odd job. A petty argument over who gets to comfort him turns "
        "into competitive one-upmanship that escalates from verbal sparring "
        "to physical proximity to an intimate standoff."
    ),
    "camera_directions": (
        "Arc: calm domestic → comedic rivalry → physical escalation → intimate tension. "
        "Use symmetrical framing for rivalry beats. Overhead shot at climax."
    ),
}

SHOTS_DATA = [
    {
        "shot_number": 1,
        "shot_type": "wide",
        "camera_angle": "establishing, slightly elevated",
        "characters_present": ["yui", "saki"],
        "character_positions": "Yui lounges on the left side of a worn couch scrolling her phone. Saki sits cross-legged on the floor at the kotatsu, eating cup ramen.",
        "lighting": "warm overhead fluorescent with yellow cast, evening blue through window blinds",
        "emotional_beat": "calm_before_storm",
        "viewer_should_feel": "Cozy domesticity, deceptive peace — the audience knows this won't last.",
        "motion_prompt": "subtle idle animation, Yui scrolls phone, Saki slurps noodles, steam rises from cup",
        "duration_seconds": 4,
        "prompt_template": "wide shot, cramped Tokyo apartment living room, warm fluorescent lighting, evening, two women relaxing separately, {ENVIRONMENT_DETAIL}, anime style, detailed background, kotatsu table with clutter",
        "notes": "Establish the space. This is the 'normal' baseline before chaos.",
    },
    {
        "shot_number": 2,
        "shot_type": "medium",
        "camera_angle": "eye-level, from hallway entrance",
        "characters_present": ["kenji"],
        "character_positions": "Kenji stands in the genkan doorway, shoulders slumped, shirt untucked, holding a crumpled envelope. One shoe half off.",
        "lighting": "hallway fluorescent behind him creating slight silhouette, warm room light on his face",
        "emotional_beat": "defeated_arrival",
        "viewer_should_feel": "Sympathy mixed with comedy — he looks pathetic but endearing.",
        "motion_prompt": "character stumbles through doorway, exhausted slouch, drops bag on floor",
        "duration_seconds": 3,
        "prompt_template": "medium shot, young man entering apartment doorway, exhausted defeated posture, untucked shirt, crumpled envelope in hand, {CHARACTER_DETAIL_KENJI}, backlit from hallway, anime style",
        "notes": "The catalyst. His arrival triggers the competition.",
    },
    {
        "shot_number": 3,
        "shot_type": "close-up",
        "camera_angle": "low angle, slight upward tilt",
        "characters_present": ["yui"],
        "character_positions": "Yui perks up on the couch, phone lowered, eyes locked on Kenji with a sly competitive smile. She shifts to sit upright.",
        "lighting": "warm key light from overhead, catch light in eyes",
        "emotional_beat": "predatory_interest",
        "viewer_should_feel": "She spotted her opportunity first. Playful danger.",
        "motion_prompt": "character's eyes widen slightly, smile forms, leans forward with interest",
        "duration_seconds": 2,
        "prompt_template": "close-up, young woman on couch looking up with competitive smirk, {CHARACTER_DETAIL_YUI}, warm lighting, catch light in eyes, anime style, expressive face",
        "notes": "Quick reaction shot. Yui moves first.",
    },
    {
        "shot_number": 4,
        "shot_type": "close-up",
        "camera_angle": "low angle from floor level",
        "characters_present": ["saki"],
        "character_positions": "Saki at the kotatsu notices Yui's reaction, chopsticks frozen mid-bite. Her expression shifts from surprise to narrow-eyed determination.",
        "lighting": "warm underlight from kotatsu blanket glow, overhead fill",
        "emotional_beat": "rivalry_triggered",
        "viewer_should_feel": "The competition is ON. Classic anime rival beat.",
        "motion_prompt": "character's expression shifts from surprise to determination, chopsticks pause mid-air",
        "duration_seconds": 2,
        "prompt_template": "close-up, young woman at kotatsu looking sideways with competitive determination, chopsticks held mid-air, {CHARACTER_DETAIL_SAKI}, warm underlighting, anime style, expressive face",
        "notes": "Mirror shot to #3. Parallel reaction establishes the rivalry dynamic.",
    },
    {
        "shot_number": 5,
        "shot_type": "medium",
        "camera_angle": "over-the-shoulder from Kenji's POV",
        "characters_present": ["yui", "saki"],
        "character_positions": "Both women are now standing, facing Kenji (camera). Yui has stepped in from the left, hand on hip. Saki has risen from the kotatsu on the right, arms crossed. They flank the frame like a standoff.",
        "lighting": "warm overhead, slight dramatic shadow between them",
        "emotional_beat": "comedic_standoff",
        "viewer_should_feel": "Kenji is trapped. Comedy of being the 'prize' in a contest he didn't enter.",
        "motion_prompt": "two characters step toward camera from opposite sides, competitive postures, slight lean forward",
        "duration_seconds": 3,
        "prompt_template": "medium shot, POV from doorway, two women standing facing camera from opposite sides of room, competitive poses, {CHARACTER_DETAIL_YUI} on left hand on hip, {CHARACTER_DETAIL_SAKI} on right arms crossed, warm apartment lighting, anime style",
        "notes": "Classic harem-comedy framing. Symmetrical composition emphasizes the rivalry.",
    },
    {
        "shot_number": 6,
        "shot_type": "medium",
        "camera_angle": "side profile, tracking",
        "characters_present": ["yui", "kenji"],
        "character_positions": "Yui has crossed the room and grabbed Kenji's arm, pulling him toward the couch. She's physically close, guiding him by the elbow. Kenji stumbles slightly, off-balance.",
        "lighting": "warm, slightly golden hour feel from a floor lamp",
        "emotional_beat": "yui_makes_first_move",
        "viewer_should_feel": "Yui is assertive and fast — she acts while Saki was still posturing.",
        "motion_prompt": "woman pulls man by arm toward couch, he stumbles forward, she leads confidently",
        "duration_seconds": 3,
        "prompt_template": "medium side profile shot, woman pulling man by the arm toward couch, she leads confidently, he stumbles, {CHARACTER_DETAIL_YUI}, {CHARACTER_DETAIL_KENJI}, warm apartment lighting, anime style, dynamic motion",
        "notes": "Physical comedy. Yui's assertiveness is her weapon.",
    },
    {
        "shot_number": 7,
        "shot_type": "medium",
        "camera_angle": "three-quarter angle from couch side",
        "characters_present": ["saki", "kenji"],
        "character_positions": "Saki has intercepted, placing herself between Kenji and the couch. She faces Kenji with hands on his chest, stopping his momentum. Their faces are close. Yui still has his arm.",
        "lighting": "warm key, rim light on Saki's hair from window",
        "emotional_beat": "saki_intercepts",
        "viewer_should_feel": "Escalation — now he's physically caught between them. Tension rises.",
        "motion_prompt": "woman steps between man and couch, hands on his chest stopping him, faces close together, tense pause",
        "duration_seconds": 3,
        "prompt_template": "medium three-quarter shot, woman blocking man's path with hands on his chest, faces close, {CHARACTER_DETAIL_SAKI}, {CHARACTER_DETAIL_KENJI}, {PROXIMITY_DETAIL}, warm rim lighting, anime style, dramatic tension",
        "notes": "The physical triangle forms. Saki uses proximity as her weapon.",
    },
    {
        "shot_number": 8,
        "shot_type": "close-up",
        "camera_angle": "tight on Kenji's face, slight fish-eye",
        "characters_present": ["kenji"],
        "character_positions": "Kenji's face fills the frame. Sweat drop on temple. Eyes darting left and right. Classic anime panic expression.",
        "lighting": "flat comedic lighting, bright",
        "emotional_beat": "comedic_panic",
        "viewer_should_feel": "Pure comedy. He's in over his head and the audience should laugh.",
        "motion_prompt": "character's eyes dart left and right rapidly, sweat drop appears on temple, comedic panic expression",
        "duration_seconds": 2,
        "prompt_template": "extreme close-up, young man's face, anime panic expression, sweat drop, eyes darting, {CHARACTER_DETAIL_KENJI}, bright comedic lighting, fish-eye distortion, anime style",
        "notes": "Comedy beat. Break tension before the next escalation.",
    },
    {
        "shot_number": 9,
        "shot_type": "wide",
        "camera_angle": "overhead bird's-eye, looking straight down",
        "characters_present": ["yui", "saki", "kenji"],
        "character_positions": "All three have tumbled onto the couch area. Kenji is seated center on the couch. Yui is pressed against his left side. Saki is pressed against his right side. Both women lean into him, each claiming a side. Their postures are intimate and competitive — mirrored but asymmetric.",
        "lighting": "warm overhead pool of light on the couch, rest of room darker",
        "emotional_beat": "intimate_escalation",
        "viewer_should_feel": "The rivalry has become physical closeness. Tension shifts from comedic to suggestive.",
        "motion_prompt": "three characters settle into couch, women lean into man from both sides, subtle competitive adjustments",
        "duration_seconds": 4,
        "prompt_template": "overhead bird's-eye shot looking down, three people on couch, man seated center, {CHARACTER_DETAIL_YUI} pressed against his left, {CHARACTER_DETAIL_SAKI} pressed against his right, {INTIMATE_POSITIONING_DETAIL}, warm pool of light, dark surrounding room, anime style",
        "notes": "Key composition shot. The overhead removes the viewer from the intimacy, making it feel observed.",
    },
    {
        "shot_number": 10,
        "shot_type": "medium",
        "camera_angle": "low angle from coffee table height",
        "characters_present": ["yui", "saki", "kenji"],
        "character_positions": "Yui whispers something to Kenji, hand on his knee. Saki responds by leaning across Kenji to glare at Yui, which puts her physically draped across him. Kenji is frozen, arms up in surrender pose.",
        "lighting": "warm intimate, lamp light from side creating dramatic shadows on faces",
        "emotional_beat": "escalation_peak",
        "viewer_should_feel": "This is the tipping point. The competition has escalated beyond posturing into real physical intimacy.",
        "motion_prompt": "woman whispers to man while touching his knee, other woman leans across him to glare at first woman, man raises hands in surrender",
        "duration_seconds": 4,
        "prompt_template": "medium low-angle shot, three people on couch, {CHARACTER_DETAIL_YUI} whispering to man's ear hand on knee, {CHARACTER_DETAIL_SAKI} leaning across him confrontationally, {ACTION_DETAIL}, {BODY_DETAIL}, warm intimate lamp lighting, dramatic side shadows, anime style",
        "notes": "Peak escalation. Multiple placeholders for explicit fills.",
    },
    {
        "shot_number": 11,
        "shot_type": "extreme_close-up",
        "camera_angle": "tight on intertwined hands",
        "characters_present": ["yui", "saki", "kenji"],
        "character_positions": "Close-up of three hands: Yui's hand gripping Kenji's left wrist, Saki's hand gripping his right. His hands are open, passive. Visual metaphor for the tug-of-war.",
        "lighting": "shallow depth of field, warm bokeh background",
        "emotional_beat": "symbolic_tension",
        "viewer_should_feel": "The stakes are real. This isn't just comedy anymore.",
        "motion_prompt": "close-up of hands gripping wrists, subtle tension in fingers, slight pulling in opposite directions",
        "duration_seconds": 2,
        "prompt_template": "extreme close-up, three hands, two women's hands gripping man's wrists from opposite sides, shallow depth of field, warm bokeh, {SKIN_DETAIL}, anime style, symbolic composition",
        "notes": "Transition shot. Symbolic. Works as a cut point to explicit sequence.",
    },
    {
        "shot_number": 12,
        "shot_type": "wide",
        "camera_angle": "through doorway frame, voyeuristic",
        "characters_present": ["yui", "saki", "kenji"],
        "character_positions": "Framed through the apartment hallway doorway. The three figures on the couch are seen from a distance, partially obscured by the door frame. Silhouetted and suggestive but not explicit at this camera distance.",
        "lighting": "couch area warmly lit, hallway dark, creating a natural frame-within-frame",
        "emotional_beat": "voyeuristic_transition",
        "viewer_should_feel": "Pulled back to observe. The intimacy is happening but the viewer is at a distance.",
        "motion_prompt": "distant figures on couch in intimate positioning, seen through dark doorway frame, subtle movement",
        "duration_seconds": 3,
        "prompt_template": "wide shot through dark doorway frame, three silhouetted figures on warmly lit couch in distance, {INTIMATE_SILHOUETTE_DETAIL}, frame within frame composition, voyeuristic angle, anime style, atmospheric",
        "notes": "Final safe shot. Doorway framing is the natural transition to explicit content.",
    },
]


# ---------------------------------------------------------------------------
# Engine mapping — based on shot_type + character count
# Maps to actual video_engine values used by anime-studio engine_selector
# ---------------------------------------------------------------------------

def pick_video_engine(shot_type: str, characters: list[str]) -> str:
    """Map shot characteristics to video_engine value.

    User-requested mapping:
        wide                          → wan (T2V multi-char wide)
        medium + 2-3 chars            → wan22_14b (I2V multi-char)
        medium + 1 char               → framepack (I2V solo)
        close-up / extreme_close-up   → framepack (detail shots)
    """
    st = shot_type.lower().replace("-", "_").replace(" ", "_")
    n_chars = len(characters)

    if st == "wide":
        return "wan"
    if st == "medium":
        if n_chars >= 2:
            return "wan22_14b"
        return "framepack"
    if st in ("close_up", "close-up", "extreme_close_up", "extreme_close-up"):
        return "framepack"
    # fallback
    return "framepack"


# ---------------------------------------------------------------------------
# SQL generation
# ---------------------------------------------------------------------------

def generate_sql() -> str:
    lines = []

    # -- Schema additions for storyboard metadata columns ----------------------
    lines.append("-- Add storyboard metadata columns if they don't exist yet")
    new_shot_cols = [
        ("character_positions", "TEXT"),
        ("lighting", "TEXT"),
        ("emotional_beat", "VARCHAR(50)"),
        ("viewer_should_feel", "TEXT"),
        ("storyboard_notes", "TEXT"),
    ]
    for col, typ in new_shot_cols:
        lines.append(
            f"ALTER TABLE shots ADD COLUMN IF NOT EXISTS {col} {typ};"
        )
    lines.append("")

    # -- Scene INSERT ----------------------------------------------------------
    lines.append("-- Scene: The Bet")
    s = SCENE_DATA
    lines.append(f"""INSERT INTO scenes (
    project_id, scene_number, title, location, time_of_day, mood,
    emotional_tone, narrative_text, camera_directions,
    generation_status, total_shots
) VALUES (
    {PROJECT_ID},
    {s['scene_number']},
    {_sql_str(s['title'])},
    {_sql_str(s['location'])},
    {_sql_str(s['time_of_day'])},
    {_sql_str(s['mood'])},
    {_sql_str(s['emotional_tone'])},
    {_sql_str(s['narrative_text'])},
    {_sql_str(s['camera_directions'])},
    'draft',
    {len(SHOTS_DATA)}
) RETURNING id;""")
    lines.append("")

    # -- Shots INSERTs ---------------------------------------------------------
    lines.append("-- Store the returned scene id in a variable for shot inserts.")
    lines.append("-- In psql: \\gset  then use :id")
    lines.append("-- In Python: scene_id = cursor.fetchone()[0]")
    lines.append("")

    for shot in SHOTS_DATA:
        engine = pick_video_engine(shot["shot_type"], shot["characters_present"])
        chars_pg = _pg_array(shot["characters_present"])

        lines.append(f"-- Shot {shot['shot_number']}: {shot['shot_type']} | {shot['emotional_beat']}")
        lines.append(f"""INSERT INTO shots (
    scene_id, shot_number, shot_type, camera_angle,
    characters_present, character_positions,
    lighting, emotional_beat, viewer_should_feel,
    motion_prompt, duration_seconds,
    generation_prompt, storyboard_notes,
    video_engine, status
) VALUES (
    :scene_id,
    {shot['shot_number']},
    {_sql_str(shot['shot_type'])},
    {_sql_str(shot['camera_angle'])},
    {chars_pg},
    {_sql_str(shot['character_positions'])},
    {_sql_str(shot['lighting'])},
    {_sql_str(shot['emotional_beat'])},
    {_sql_str(shot['viewer_should_feel'])},
    {_sql_str(shot['motion_prompt'])},
    {shot['duration_seconds']},
    {_sql_str(shot['prompt_template'])},
    {_sql_str(shot['notes'])},
    {_sql_str(engine)},
    'pending'
);""")
        lines.append("")

    return "\n".join(lines)


def _sql_str(val: str) -> str:
    """Escape a string for SQL literal. Uses $$ quoting for strings with apostrophes."""
    if "'" in val and "$$" not in val:
        return f"$${val}$$"
    return "'" + val.replace("'", "''") + "'"


def _pg_array(items: list[str]) -> str:
    """Format a Python list as a Postgres text array literal."""
    inner = ", ".join(f"'{item}'" for item in items)
    return f"ARRAY[{inner}]::VARCHAR(255)[]"


# ---------------------------------------------------------------------------
# Python-driven execution (alternative to raw SQL)
# ---------------------------------------------------------------------------

PYTHON_INSERT_TEMPLATE = '''
import asyncio
import asyncpg

PROJECT_ID = 24

async def insert_the_bet():
    conn = await asyncpg.connect(
        host="192.168.50.135", port=5432,
        user="patrick", password="RP78eIrW7cI2jYvL5akt1yurE",
        database="anime_production",
    )

    # Add storyboard columns if missing
    for col, typ in [
        ("character_positions", "TEXT"),
        ("lighting", "TEXT"),
        ("emotional_beat", "VARCHAR(50)"),
        ("viewer_should_feel", "TEXT"),
        ("storyboard_notes", "TEXT"),
    ]:
        await conn.execute(
            f"ALTER TABLE shots ADD COLUMN IF NOT EXISTS {col} {typ}"
        )

    # Insert scene
    scene_id = await conn.fetchval("""
        INSERT INTO scenes (
            project_id, scene_number, title, location, time_of_day, mood,
            emotional_tone, narrative_text, camera_directions,
            generation_status, total_shots
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'draft', $10)
        RETURNING id
    """, PROJECT_ID, %(scene_number)d, %(title)r, %(location)r,
        %(time_of_day)r, %(mood)r, %(emotional_tone)r,
        %(narrative_text)r, %(camera_directions)r, %(total_shots)d)

    print(f"Created scene: {scene_id}")

    # Insert shots
    for shot in SHOTS:
        await conn.execute("""
            INSERT INTO shots (
                scene_id, shot_number, shot_type, camera_angle,
                characters_present, character_positions,
                lighting, emotional_beat, viewer_should_feel,
                motion_prompt, duration_seconds,
                generation_prompt, storyboard_notes,
                video_engine, status
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, 'pending'
            )
        """, scene_id, shot["shot_number"], shot["shot_type"],
            shot["camera_angle"], shot["characters_present"],
            shot["character_positions"], shot["lighting"],
            shot["emotional_beat"], shot["viewer_should_feel"],
            shot["motion_prompt"], shot["duration_seconds"],
            shot["prompt_template"], shot["notes"],
            shot["video_engine"])

    print(f"Inserted {len(SHOTS)} shots")
    await conn.close()

asyncio.run(insert_the_bet())
'''


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Insert 'The Bet' storyboard")
    parser.add_argument("--execute", action="store_true",
                        help="Execute SQL against Postgres (default: print only)")
    parser.add_argument("--format", choices=["sql", "json", "python"],
                        default="sql", help="Output format")
    args = parser.parse_args()

    if args.format == "json":
        # Output the enriched shot data with engine assignments
        enriched = []
        for shot in SHOTS_DATA:
            entry = dict(shot)
            entry["video_engine"] = pick_video_engine(
                shot["shot_type"], shot["characters_present"]
            )
            enriched.append(entry)
        print(json.dumps(enriched, indent=2))
        return

    if args.format == "python":
        print(PYTHON_INSERT_TEMPLATE)
        return

    sql = generate_sql()

    if args.execute:
        _execute_sql(sql)
    else:
        print(sql)
        print("\n-- Run with --execute to insert into DB, or pipe to psql:")
        print("--   python3 scripts/insert_the_bet_storyboard.py | psql -h 192.168.50.135 -U patrick -d anime_production")


def _execute_sql(sql: str):
    """Execute via asyncpg against the real DB."""
    import asyncio

    async def run():
        import asyncpg
        conn = await asyncpg.connect(
            host="127.0.0.1", port=5432,
            user="patrick", password="RP78eIrW7cI2jYvL5akt1yurE",
            database="anime_production",
        )

        # Run ALTER TABLE statements first
        for line in sql.split("\n"):
            line = line.strip()
            if line.startswith("ALTER TABLE"):
                await conn.execute(line)

        # Insert scene, get ID
        scene_id = await conn.fetchval(f"""
            INSERT INTO scenes (
                project_id, scene_number, title, location, time_of_day, mood,
                emotional_tone, narrative_text, camera_directions,
                generation_status, total_shots
            ) VALUES (
                {PROJECT_ID},
                {SCENE_DATA['scene_number']},
                $1, $2, $3, $4, $5, $6, $7, 'draft', {len(SHOTS_DATA)}
            ) RETURNING id
        """,
            SCENE_DATA["title"],
            SCENE_DATA["location"],
            SCENE_DATA["time_of_day"],
            SCENE_DATA["mood"],
            SCENE_DATA["emotional_tone"],
            SCENE_DATA["narrative_text"],
            SCENE_DATA["camera_directions"],
        )
        print(f"Scene created: {scene_id}")

        # Insert shots
        for shot in SHOTS_DATA:
            engine = pick_video_engine(shot["shot_type"], shot["characters_present"])
            await conn.execute("""
                INSERT INTO shots (
                    scene_id, shot_number, shot_type, camera_angle,
                    characters_present, character_positions,
                    lighting, emotional_beat, viewer_should_feel,
                    motion_prompt, duration_seconds,
                    generation_prompt, storyboard_notes,
                    video_engine, status
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, 'pending'
                )
            """,
                scene_id,
                shot["shot_number"],
                shot["shot_type"],
                shot["camera_angle"],
                shot["characters_present"],
                shot["character_positions"],
                shot["lighting"],
                shot["emotional_beat"],
                shot["viewer_should_feel"],
                shot["motion_prompt"],
                shot["duration_seconds"],
                shot["prompt_template"],  # → generation_prompt column
                shot["notes"],            # → storyboard_notes column
                engine,
            )
            print(f"  Shot {shot['shot_number']}: {shot['shot_type']} → {engine}")

        print(f"\nDone. {len(SHOTS_DATA)} shots inserted.")
        await conn.close()

    asyncio.run(run())


if __name__ == "__main__":
    main()
