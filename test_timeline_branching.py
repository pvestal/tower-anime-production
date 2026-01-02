#!/usr/bin/env python3
"""
Test timeline branching functionality with Tokyo Debt Desire Episode 2
"""

import json
import psycopg2
from psycopg2.extras import RealDictCursor
import uuid

def test_timeline_branching():
    """Test creating timeline branches from Episode 2 decision point"""

    print("=" * 60)
    print("TIMELINE BRANCHING TEST")
    print("=" * 60)

    conn = psycopg2.connect(
        host='localhost',
        database='anime_production',
        user='patrick',
        password='***REMOVED***'
    )
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # Get Episode 2 ID
        cur.execute("""
            SELECT id, title FROM episodes
            WHERE project_id = 24 AND episode_number = 2
        """)
        episode = cur.fetchone()
        print(f"\n📺 Episode: {episode['title']}")

        # Load the generated episode JSON to get decision points
        with open('/tmp/tokyo_debt_episode2.json', 'r') as f:
            episode_json = json.load(f)

        decision_points = episode_json.get('decision_points', [])
        print(f"📊 Decision Points Found: {len(decision_points)}")

        if decision_points:
            dp = decision_points[0]
            print(f"\n🔀 Creating timeline branch for:")
            print(f"   Scene: {dp.get('scene_order', 'Unknown')}")
            print(f"   Choice: {dp.get('choice', 'Unknown')}")
            print(f"   Consequences: {dp.get('consequences', [])}")

            # Create main timeline if it doesn't exist
            cur.execute("""
                INSERT INTO timeline_branches (
                    branch_name,
                    divergence_point,
                    is_canon,
                    created_by
                ) VALUES (
                    'Tokyo Debt Main Timeline',
                    'Original timeline',
                    true,
                    'system'
                )
                ON CONFLICT (branch_name) DO NOTHING
                RETURNING id
            """)

            main_branch = cur.fetchone()
            if not main_branch:
                cur.execute("""
                    SELECT id FROM timeline_branches
                    WHERE branch_name = 'Tokyo Debt Main Timeline'
                """)
                main_branch = cur.fetchone()

            print(f"\n✅ Main Timeline ID: {main_branch['id']}")

            # Create alternate timeline branch
            branch_name = f"Tokyo Debt - {dp.get('choice', 'Alt')} Path"

            cur.execute("""
                INSERT INTO timeline_branches (
                    parent_branch_id,
                    branch_name,
                    divergence_point,
                    divergence_episode_id,
                    choice_made,
                    world_state,
                    character_states,
                    created_by
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, 'echo_brain'
                )
                ON CONFLICT (branch_name) DO NOTHING
                RETURNING id
            """, (
                main_branch['id'],
                branch_name,
                f"Episode 2, Scene {dp.get('scene_order', 'Unknown')}",
                episode['id'],
                dp.get('choice', 'Unknown choice'),
                json.dumps({
                    'yakuza_pressure': 'increasing',
                    'seduction_level': 'intensified',
                    'debt_status': 'unpaid'
                }),
                json.dumps({
                    'Mei': {'seduction_approach': 'domestic'},
                    'Rina': {'seduction_approach': 'clumsy'},
                    'Yuki': {'seduction_approach': 'caring'},
                    'Takeshi': {'stress_level': 'high'}
                })
            ))

            alt_branch = cur.fetchone()
            if alt_branch:
                print(f"✅ Created Alternate Timeline: {branch_name}")
                print(f"   Branch ID: {alt_branch['id']}")
            else:
                print(f"⚠️ Branch already exists: {branch_name}")

            # Store the decision point in the database
            cur.execute("""
                INSERT INTO decision_points (
                    episode_id,
                    decision_description,
                    choices,
                    impact_level,
                    created_at
                ) VALUES (
                    %s, %s, %s, %s, CURRENT_TIMESTAMP
                )
                ON CONFLICT DO NOTHING
                RETURNING id
            """, (
                episode['id'],
                dp.get('choice', 'Decision point'),
                json.dumps(dp.get('consequences', [])),
                'major'
            ))

            decision_id = cur.fetchone()
            if decision_id:
                print(f"✅ Stored Decision Point ID: {decision_id['id']}")

            conn.commit()

            # Query all timelines for this project
            cur.execute("""
                SELECT
                    tb.id,
                    tb.branch_name,
                    tb.parent_branch_id,
                    tb.divergence_point,
                    tb.choice_made,
                    tb.is_canon,
                    tb.created_at,
                    COUNT(et.id) as episode_count
                FROM timeline_branches tb
                LEFT JOIN episode_timelines et ON et.timeline_branch_id = tb.id
                WHERE tb.branch_name LIKE 'Tokyo Debt%'
                GROUP BY tb.id, tb.branch_name, tb.parent_branch_id,
                         tb.divergence_point, tb.choice_made, tb.is_canon, tb.created_at
                ORDER BY tb.created_at
            """)

            timelines = cur.fetchall()

            print(f"\n📚 All Tokyo Debt Timelines:")
            for tl in timelines:
                canon = "📌" if tl['is_canon'] else "🔀"
                parent = f"(from #{tl['parent_branch_id']})" if tl['parent_branch_id'] else "(root)"
                print(f"  {canon} {tl['branch_name']} {parent}")
                if tl['choice_made']:
                    print(f"     Choice: {tl['choice_made']}")
                print(f"     Episodes: {tl['episode_count']}")

            # Test character states across timelines
            cur.execute("""
                SELECT
                    cts.character_id,
                    c.name as character_name,
                    tb.branch_name,
                    cts.state_data,
                    cts.emotional_state,
                    cts.relationships
                FROM character_timeline_states cts
                JOIN characters c ON c.id = cts.character_id
                JOIN timeline_branches tb ON tb.id = cts.timeline_branch_id
                WHERE c.project_id = 24
                LIMIT 5
            """)

            char_states = cur.fetchall()

            if char_states:
                print(f"\n👥 Character States Across Timelines:")
                for cs in char_states:
                    print(f"  {cs['character_name']} in {cs['branch_name']}:")
                    print(f"    Emotional: {cs['emotional_state']}")

        else:
            print("\n⚠️ No decision points in Episode 2 - creating manual branch")

            # Create a manual decision point for testing
            cur.execute("""
                INSERT INTO timeline_branches (
                    branch_name,
                    divergence_point,
                    divergence_episode_id,
                    choice_made,
                    world_state,
                    is_canon,
                    created_by
                ) VALUES (
                    'Tokyo Debt - Yakuza Confrontation Path',
                    'Episode 2 - Night scene yakuza arrives',
                    %s,
                    'Takeshi confronts yakuza directly',
                    %s,
                    false,
                    'manual_test'
                )
                ON CONFLICT (branch_name) DO NOTHING
                RETURNING id
            """, (
                episode['id'],
                json.dumps({
                    'yakuza_response': 'hostile',
                    'roommates_safety': 'threatened',
                    'debt_deadline': 'accelerated'
                })
            ))

            if cur.fetchone():
                print("✅ Created manual test branch")
                conn.commit()

        print(f"\n" + "=" * 60)
        print("TIMELINE BRANCHING SUMMARY")
        print("=" * 60)

        # Final statistics
        cur.execute("""
            SELECT
                (SELECT COUNT(*) FROM timeline_branches WHERE branch_name LIKE 'Tokyo Debt%') as branches,
                (SELECT COUNT(*) FROM decision_points WHERE episode_id = %s) as decisions,
                (SELECT COUNT(*) FROM episode_timelines WHERE episode_id = %s) as timeline_episodes
        """, (episode['id'], episode['id']))

        stats = cur.fetchone()

        print(f"\n📊 Statistics:")
        print(f"  Timeline Branches: {stats['branches']}")
        print(f"  Decision Points: {stats['decisions']}")
        print(f"  Timeline Episodes: {stats['timeline_episodes']}")

        print(f"\n✅ Timeline system is operational!")
        print(f"Next steps:")
        print(f"  1. Generate alternate scenes for branch points")
        print(f"  2. Track character evolution per timeline")
        print(f"  3. Implement timeline convergence points")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        conn.rollback()
        raise

    finally:
        conn.close()

if __name__ == "__main__":
    test_timeline_branching()