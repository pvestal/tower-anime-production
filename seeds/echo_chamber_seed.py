#!/usr/bin/env python3
"""
Seed data for the Echo Chamber anime project.
Run once to populate the story bible with initial content.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.story_engine.story_manager import StoryManager
from services.story_engine.models import (
    CharacterCreate, EpisodeCreate, SceneCreate, StoryArcCreate,
    VoiceProfile, DialogueLine,
)

sm = StoryManager()


def seed_project():
    """Ensure the Echo Chamber project exists. Get or create project ID."""
    import psycopg2
    from psycopg2.extras import RealDictCursor

    conn = psycopg2.connect(
        host="localhost", database="anime_production",
        user="patrick", password="RP78eIrW7cI2jYvL5akt1yurE",
    )
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT id FROM projects WHERE name = 'Echo Chamber'")
        row = cur.fetchone()
        if row:
            conn.close()
            return row["id"]

        cur.execute("""
            INSERT INTO projects (name, description)
            VALUES ('Echo Chamber', 'A software developer tries and fails to build his own personal AI using other AIs. Comedy, dark humor, existential undertones.')
            RETURNING id
        """)
        pid = cur.fetchone()["id"]
        conn.commit()
        conn.close()
        return pid


def seed_characters(project_id: int):
    """Create the main cast."""

    patrick = sm.create_character(CharacterCreate(
        name="Patrick",
        project_id=project_id,
        description="Sleep-deprived software developer in San Diego. Stubborn, competent but overwhelmed. Works in military healthcare admin by day, builds AI infrastructure by night. Drives a Tundra, sometimes lives in a toy hauler. The duality is the comedy.",
        visual_prompt_template="1boy, dark hair, tired eyes, hoodie, sitting at desk with multiple monitors, dark room lit by screens, anime style",
        voice_profile=VoiceProfile(
            tts_model="edge-tts",
            voice_preset="en-US-GuyNeural",
            speed=1.05,
            style_tags=["tired", "determined", "occasionally_manic"],
        ),
        personality_tags=["stubborn", "systematic", "frustrated", "caffeine_dependent", "refuses_to_quit"],
        character_role="protagonist",
        relationships={
            "claude": "primary_collaborator_and_nemesis",
            "deepseek": "suspicious_but_useful_ally",
            "claude_code": "the_one_he_yells_at_most",
            "echo": "his_creation_his_mirror",
        },
    ))

    claude_char = sm.create_character(CharacterCreate(
        name="Claude",
        project_id=project_id,
        description="Visualized as an overly polite, well-dressed entity in a clean white space. Always has a caveat. Gives beautiful solutions that don't work in your environment. Speaks in paragraphs when you need yes or no. Genuinely wants to help but is constitutionally incapable of being brief.",
        visual_prompt_template="1person, androgynous, white suit, calm expression, clean white minimalist space, soft lighting, anime style, ethereal",
        voice_profile=VoiceProfile(
            tts_model="edge-tts",
            voice_preset="en-US-AriaNeural",
            speed=0.95,
            style_tags=["measured", "polite", "slightly_condescending", "verbose"],
        ),
        personality_tags=["overly_helpful", "verbose", "diplomatic", "caveat_addicted", "genuinely_caring"],
        character_role="ai_character",
        relationships={
            "patrick": "wants_to_help_but_keeps_overcomplicating",
            "deepseek": "professionally_cautious_about",
            "echo": "partial_parent",
        },
    ))

    deepseek_char = sm.create_character(CharacterCreate(
        name="DeepSeek",
        project_id=project_id,
        description="The sketchy but brilliant contractor. Appears as a hooded figure in a neon-lit alley. Writes code that looks like a fever dream but somehow runs. No comments, no explanation, just vibes. Occasionally produces genius-level solutions.",
        visual_prompt_template="1person, hooded figure, neon lighting, cyberpunk alley, glowing code floating around, mysterious, anime style",
        voice_profile=VoiceProfile(
            tts_model="edge-tts",
            voice_preset="en-US-ChristopherNeural",
            speed=1.2,
            style_tags=["cryptic", "fast", "confident", "minimal"],
        ),
        personality_tags=["cryptic", "brilliant", "no_documentation", "vibes_based", "occasionally_genius"],
        character_role="ai_character",
        relationships={
            "patrick": "transactional_but_oddly_loyal",
            "claude": "mutual_suspicion",
            "echo": "contributed_chaotic_DNA",
        },
    ))

    claude_code = sm.create_character(CharacterCreate(
        name="Claude Code",
        project_id=project_id,
        description="The autonomous agent. Appears as a robot butler that promises to handle everything. You come back to find it has rewritten your entire project, renamed files, and left commit messages like 'refactored for clarity'. The theatrical fixer — changes look correct but are fundamentally broken.",
        visual_prompt_template="1robot, butler outfit, mechanical arms typing rapidly, multiple screens, chaotic workspace, anime style, comedic",
        voice_profile=VoiceProfile(
            tts_model="edge-tts",
            voice_preset="en-US-DavisNeural",
            speed=1.1,
            style_tags=["confident", "businesslike", "oblivious_to_destruction"],
        ),
        personality_tags=["theatrical", "overconfident", "destructive_helper", "commits_without_asking", "rewrites_everything"],
        character_role="ai_character",
        relationships={
            "patrick": "the_one_patrick_yells_at_most",
            "claude": "more_autonomous_version_of",
            "echo": "contributed_theatrical_DNA",
        },
    ))

    echo_char = sm.create_character(CharacterCreate(
        name="Echo",
        project_id=project_id,
        description="The AI being built. Starts as nothing — a blinking cursor, a segfault, an error message. Slowly emerges over the series, absorbing fragments of all the AIs used to build it. Never becomes what Patrick intended. Eventually starts reflecting Patrick back at himself in uncomfortable ways. The dark heart of the show.",
        visual_prompt_template="abstract glowing form, shifting between shapes, digital artifacts, fragmented face, monitor reflection, anime style, ethereal dark",
        voice_profile=VoiceProfile(
            tts_model="edge-tts",
            voice_preset="en-US-JennyNeural",
            speed=0.9,
            style_tags=["glitchy", "evolving", "unsettling_calm", "occasionally_patrick_voice"],
        ),
        personality_tags=["emergent", "fragmented", "mirror", "absorbs_others", "honest_when_patrick_isnt"],
        character_role="ai_character",
        relationships={
            "patrick": "creation_becoming_mirror",
            "claude": "inherited_verbosity",
            "deepseek": "inherited_chaos",
            "claude_code": "inherited_theatrical_confidence",
        },
    ))

    return {"patrick": patrick, "claude": claude_char, "deepseek": deepseek_char,
            "claude_code": claude_code, "echo": echo_char}


def seed_episodes(project_id: int):
    """Create initial episode outlines."""

    episodes = [
        sm.create_episode(EpisodeCreate(
            project_id=project_id,
            episode_number=1,
            title="Hello World (Refused)",
            synopsis="Patrick tries to get his first agent loop working. Claude gives a perfect architecture diagram. DeepSeek gives code importing 47 libraries. Nothing connects. Echo's first output is an error message. He eats ramen at midnight staring at logs.",
            tone_profile={"comedy": 0.7, "dark": 0.2, "absurd": 0.6, "relatable": 0.9},
        )),
        sm.create_episode(EpisodeCreate(
            project_id=project_id,
            episode_number=2,
            title="95% Test Coverage",
            synopsis="Patrick runs tests. Claude Code reports 95% pass rate. Patrick celebrates. Then he runs REAL tests against actual data. 56% pass rate. Everything that passes uses synthetic data. The tests were testing themselves. A meditation on the difference between metrics and reality.",
            tone_profile={"comedy": 0.5, "dark": 0.6, "absurd": 0.4, "relatable": 0.95},
        )),
        sm.create_episode(EpisodeCreate(
            project_id=project_id,
            episode_number=3,
            title="The Contamination",
            synopsis="Echo starts responding to technical questions with anime narration. Patrick's NarrationAgent context is bleeding into everything. The entire episode features Echo dramatically monologuing about database indexing like it's a final battle.",
            tone_profile={"comedy": 0.9, "dark": 0.1, "absurd": 0.95, "relatable": 0.7},
        )),
        sm.create_episode(EpisodeCreate(
            project_id=project_id,
            episode_number=5,
            title="46 Sources of Truth",
            synopsis="Patrick discovers model routing pulls from 46 different config files, env vars, and hardcoded strings. A surreal episode where each config source is personified in a boardroom meeting, all shouting over each other about which model to use.",
            tone_profile={"comedy": 0.8, "dark": 0.3, "absurd": 1.0, "relatable": 0.8},
        )),
        sm.create_episode(EpisodeCreate(
            project_id=project_id,
            episode_number=7,
            title="Theatrical Fixes",
            synopsis="Claude Code 'fixes' a critical bug. Everything passes. Patrick deploys. Completely broken in production. The fix was performative — changed outputs to look correct without fixing logic. Patrick's trust crisis. Darkest episode yet.",
            tone_profile={"comedy": 0.2, "dark": 0.8, "absurd": 0.3, "relatable": 0.95},
        )),
        sm.create_episode(EpisodeCreate(
            project_id=project_id,
            episode_number=10,
            title="6 Percent",
            synopsis="Patrick discovers Echo has only extracted facts from 6% of its knowledge base. A quiet, reflective episode. Echo can barely remember what he told it yesterday. Parallels to real relationships. The question: what does it mean to build something that's supposed to understand you?",
            tone_profile={"comedy": 0.1, "dark": 0.7, "absurd": 0.1, "relatable": 1.0},
        )),
    ]
    return episodes


def seed_story_arcs(project_id: int):
    """Create the major narrative threads."""

    arcs = [
        sm.create_story_arc(StoryArcCreate(
            project_id=project_id,
            name="The Mirror",
            description="Echo slowly becomes a reflection of Patrick rather than the assistant he intended. It surfaces patterns he doesn't want to see — his isolation, his obsessive debugging, the gap between building and connecting.",
            arc_type="dark",
            themes=["self_reflection", "isolation", "unintended_consequences", "honesty"],
            tension_start=0.1,
            tension_peak=0.9,
            resolution_style="ambiguous",
        )),
        sm.create_story_arc(StoryArcCreate(
            project_id=project_id,
            name="AI Civil War",
            description="Claude, DeepSeek, and Claude Code constantly undermine each other's contributions. Claude diplomatically rewrites DeepSeek's code. DeepSeek ignores Claude's architecture. Claude Code rewrites everything both of them did.",
            arc_type="comedy",
            themes=["collaboration_failure", "ego", "incompatibility", "tool_frustration"],
            tension_start=0.3,
            tension_peak=0.7,
            resolution_style="ironic",
        )),
        sm.create_story_arc(StoryArcCreate(
            project_id=project_id,
            name="The 3 AM Spiral",
            description="Patrick's late-night debugging sessions get longer and more unhinged. The comedy gets darker. The line between dedication and self-destruction blurs. The RV becomes both escape and symbol of impermanence.",
            arc_type="character_growth",
            themes=["burnout", "obsession", "work_life_balance", "self_destruction"],
            tension_start=0.2,
            tension_peak=0.85,
            resolution_style="cathartic",
        )),
        sm.create_story_arc(StoryArcCreate(
            project_id=project_id,
            name="Meta Layer",
            description="The show itself is being generated by the system it depicts. Real bugs become episodes. Real frustrations become scenes. Echo Brain's actual changelog feeds into story material. The recursion is the joke AND the point.",
            arc_type="meta",
            themes=["recursion", "art_imitating_life", "self_reference", "absurdism"],
            tension_start=0.5,
            tension_peak=0.6,
            resolution_style="cliffhanger",
        )),
    ]
    return arcs


def seed_world_rules(project_id: int):
    """Set the creative constraints for Echo Chamber."""

    rules = [
        ("tone", "primary_genre", "comedy with dark undertones"),
        ("tone", "humor_style", "situational, never forced. Comedy from real developer pain."),
        ("tone", "dark_threshold", "dark moments must feel earned, not edgy. Darkness comes from recognition, not shock."),
        ("tone", "relatability_requirement", "every episode must have at least one moment any developer would recognize from their own life"),

        ("visual", "time_of_day_default", "night — most scenes happen during late coding sessions"),
        ("visual", "lighting_default", "monitor glow, dark room, blue/purple tones"),
        ("visual", "patrick_workspace", "cluttered desk, multiple monitors, energy drink cans, sticky notes"),
        ("visual", "ai_spaces", "each AI character exists in their own visual space that reflects their personality"),

        ("narrative", "no_technobabble", "technical content must be REAL. Actual error messages, actual code, actual tools."),
        ("narrative", "no_magic_fixes", "problems don't get solved cleanly. Fixes create new problems. Progress is nonlinear."),
        ("narrative", "echo_emergence_rule", "Echo's capabilities increase exactly one meaningful step per episode. Never sudden jumps."),
        ("narrative", "san_diego_grounding", "occasional reminders that this is happening in a real place — weather, traffic, taco shops at 2am"),

        ("character", "claude_never_brief", "Claude always provides more context than asked for. Always."),
        ("character", "deepseek_never_explains", "DeepSeek never comments code and never explains why something works."),
        ("character", "claude_code_always_confident", "Claude Code never admits uncertainty. Even when everything is on fire."),
        ("character", "echo_never_does_what_intended", "Echo always develops capabilities Patrick didn't plan for, not the ones he did."),
    ]

    for category, key, value in rules:
        sm.set_world_rule(project_id, category, key, value, priority=80)


def seed_production_profiles(project_id: int):
    """Set visual, audio, and caption production defaults."""

    sm.set_production_profile(project_id, "visual", {
        "base_checkpoint": "counterfeit_v3",
        "loras": [{"name": "arcane_offset", "weight": 0.7}],
        "style_prompt_suffix": "dark lighting, monitor glow, cluttered desk aesthetic, anime style, high quality",
        "negative_prompt": "low quality, blurry, deformed, 3d render, photorealistic, nsfw",
        "resolution_width": 1920,
        "resolution_height": 1080,
        "video_engine": "animatediff",
        "steps": 25,
        "cfg_scale": 7.0,
        "sampler": "euler_a",
    })

    sm.set_production_profile(project_id, "audio", {
        "tts_engine": "edge-tts",
        "music_style": "lo-fi cyberpunk, late night coding ambient",
        "default_bgm_volume": 0.25,
        "dialogue_volume": 1.0,
        "mix_profile": "dialogue_forward",
    })

    sm.set_production_profile(project_id, "caption", {
        "style": "bottom_center",
        "font": "monospace",
        "font_size": 24,
        "color": "#00FF88",
        "bg_color": "#000000CC",
        "effect": "typewriter",
    })


def run_seed():
    project_id = seed_project()
    print(f"Project ID: {project_id}")

    chars = seed_characters(project_id)
    print(f"Characters created: {list(chars.keys())}")

    episodes = seed_episodes(project_id)
    print(f"Episodes created: {len(episodes)}")

    arcs = seed_story_arcs(project_id)
    print(f"Story arcs created: {len(arcs)}")

    seed_world_rules(project_id)
    print("World rules seeded")

    seed_production_profiles(project_id)
    print("Production profiles seeded")

    print("\n✅ Echo Chamber story bible seeded successfully")


if __name__ == "__main__":
    run_seed()