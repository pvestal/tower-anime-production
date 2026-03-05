#!/usr/bin/env python3
"""Generate keyframes for ALL CGS scenes in story order.

Calls the keyframe-blitz endpoint sequentially per scene.
Skips shots that already have keyframes.
Retries on connection errors (server restart).
"""
import json
import sys
import time
import urllib.request
import urllib.error

# Force unbuffered output for background execution
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

API = "http://localhost:8401/api/scenes"
PROJECT = "Cyberpunk Goblin Slayer"
MAX_RETRIES = 5
RETRY_DELAY = 15  # seconds

# Scenes in story order (scene_number, id, title, shot_count)
SCENES = [
    (1, "57597341-ef33-4b45-b2d7-c67d3717d26e", "The Quest Board", 3),
    (2, "3fba404b-48fd-45a9-a652-d3201642192a", "Descent Into Darkness", 3),
    (3, "c3d10f1e-4ba9-434b-88b2-add44b3be660", "The Goblin Ambush", 3),
    (4, "b86e3034-bd90-4dea-9986-3810d25bd159", "The Armored Savior", 3),
    (5, "8c22d178-5cce-47be-8abe-f3a3e4fdff90", "Clearing the Nest", 3),
    (5, "2fabf677-6348-4a40-9b6a-2036bf06e8ac", "Tower Ascent - Reconnaissance", 3),
    (6, "31632842-7073-44fe-83d8-f5143789fc82", "First Light", 3),
    (6, "29fca162-7148-4151-8d4e-0290b3db116c", "Data Room Breach", 3),
    (7, "4d7c2d56-1977-44e6-a555-6f333a6eecee", "Goblin Network Echoes", 2),
    (8, "e89a7882-c45e-4b2e-9a79-0aa870689eeb", "Interrogation Room Confrontation", 3),
    (9, "4e2b6588-32e9-4cdd-8dc3-373db3eb5590", "Corporate Denial", 3),
    (10, "14889dca-34c0-42a3-bd67-4fd4428a2dbc", "Yamamoto's Data Decryption", 3),
    (11, "41073d72-08bf-47f6-8781-143b957a3fef", "Corporate Lobby Infiltration", 2),
    (12, "1d0b2a4b-195f-47e2-a8da-63d68e0b4acf", "Interrogation Room Observation", 3),
    (13, "17c0926f-b14e-4632-90da-7c16301682ad", "Cyber Goblin Alpha Encounter", 2),
    (14, "b51eebff-69e2-4f05-8117-760c06e2c375", "Yamamoto's Revelation", 2),
    (15, "903d32df-e7a3-4b64-8829-d8246b4f7e4b", "Interrogation Room Revelation", 3),
    (16, "1a749586-879e-4b87-9f0e-0457d7a866a6", "Yamamoto's Calculated Risk", 3),
    (17, "ac4e9026-abe2-40fc-ad70-6c5384045a49", "Al-Rashid's Desert Guidance", 3),
    (18, "05658e07-c533-48bb-9a57-eba55bc3c469", "Ryuu's Silent Watch", 3),
    (19, "95d699b6-6657-4731-b5d3-521cf5e54031", "Street Goblin Ambush", 3),
    (20, "17b942a7-4478-4caa-9c56-3842586ca8ed", "Marrakech Market Introduction", 3),
    (21, "3cf76916-83ca-46b0-9f04-990fc11cfe04", "Traditional Tea Ceremony", 3),
    (22, "6d539d37-0f98-44f6-a9da-294770d00666", "Ryuu's Silent Observation", 3),
    (23, "3a92d9c8-cbea-46e2-84c6-ab50ab3b473d", "Street Goblin Ambush - Echoes", 3),
    (24, "955ce5bc-2948-44d2-94b3-ce2ce42d0547", "Arctic Research Station - Distress", 3),
    (25, "c8e47443-ba0f-4a54-ab46-1655c7626190", "Frozen Wastelands - Approach", 3),
    (26, "704c65e7-68db-44c3-8df8-df274f6d4671", "Hybridization Lab - Horror", 4),
    (27, "fa7f9f7a-20ec-4305-8614-17298ad6d6c1", "Corporate Overseer - Revelation", 3),
    (28, "017cfbd1-81c6-4e76-9b08-cb974736be97", "Al-Rashid's Safehouse Revelation", 3),
    (29, "e049b754-8e28-43ae-94bf-30818e50bd24", "Street Goblin Ambush - Tehran", 3),
    (30, "fd716173-5f84-4fbd-a407-5a822e69e1c3", "Yamamoto's Analysis - Iran", 3),
    (31, "c7191519-eba1-4572-b0b9-d65895ae6736", "Marcus's Interrogation", 3),
    (32, "9b0f0de0-9e59-420e-9b85-49d2dd555620", "Safehouse Shadows", 3),
    (33, "8038d9c3-4807-4289-a748-90fdb7f8eec7", "Zara's Plea", 2),
    (34, "252c8615-946a-45b9-9d85-fe27f25f59be", "Neutrality's Cost", 2),
    (35, "df5649ea-6e03-41a4-ab26-d72f2b4d9a71", "Ryuu's Observation", 2),
    (36, "1f42686b-bc56-4dd7-ac84-64c06ea0af76", "Corporate Intervention", 2),
    (37, "f2dc783f-e71d-4cec-85c3-32ed0b2e5622", "Kai's Decision", 2),
    (38, "801a6044-0a4a-4424-a6b1-d2b80347bd8c", "Global Network Shutdown", 3),
    (39, "980ea1f2-2e8d-48af-820a-e5253b64b9e0", "Tehran Market Mayhem", 3),
    (40, "138b697f-be9c-4fbe-8ec1-9c981c0e0b15", "Corporate Vogue - Diversion", 3),
    (41, "cba16ebe-05ea-445e-bc0e-f0b18c55c35b", "Al-Rashid's Guidance", 3),
    (42, "d05a43ec-d77a-4605-929f-d5b31f88572d", "Cyber Goblin Alpha Confrontation", 3),
]


def wait_for_api():
    """Wait for the API to come back up after a crash."""
    for i in range(MAX_RETRIES):
        try:
            urllib.request.urlopen(f"http://localhost:8401/api/scenes", timeout=5)
            return True
        except Exception:
            pass
        # Also try a simple GET that returns 422 (means server is up)
        try:
            req = urllib.request.Request(f"http://localhost:8401/api/scenes", method="GET")
            urllib.request.urlopen(req, timeout=5)
            return True
        except urllib.error.HTTPError:
            return True  # 422 means server is responding
        except Exception:
            print(f"  Waiting for API ({i+1}/{MAX_RETRIES})...")
            time.sleep(RETRY_DELAY)
    return False


def blitz_scene(scene_id: str, skip_existing: bool = True) -> dict:
    url = f"{API}/{scene_id}/keyframe-blitz?skip_existing={str(skip_existing).lower()}"
    req = urllib.request.Request(url, method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=600)
        return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        return {"error": f"HTTP {e.code}: {body[:200]}"}
    except (ConnectionRefusedError, urllib.error.URLError, ConnectionResetError) as e:
        # Server crashed — wait for restart and retry
        print(f"  Connection lost, waiting for API restart...")
        if wait_for_api():
            print(f"  API is back, retrying...")
            try:
                resp = urllib.request.urlopen(req, timeout=600)
                return json.loads(resp.read())
            except Exception as e2:
                return {"error": f"Retry failed: {e2}"}
        return {"error": f"API did not recover: {e}"}
    except Exception as e:
        return {"error": str(e)}


def main():
    start_from = int(sys.argv[1]) if len(sys.argv) > 1 else 1

    total_generated = 0
    total_skipped = 0
    total_failed = 0
    start_time = time.time()

    print(f"{'='*70}")
    print(f"KEYFRAME GENERATION — {PROJECT}")
    print(f"44 scenes, 124 shots, starting from scene {start_from}")
    print(f"{'='*70}")

    for scene_num, scene_id, title, expected_shots in SCENES:
        if scene_num < start_from:
            continue

        print(f"\n[Scene {scene_num:2d}] {title} ({expected_shots} shots)")
        t0 = time.time()

        result = blitz_scene(scene_id)
        elapsed = time.time() - t0

        if "error" in result:
            print(f"  ERROR: {result['error']}")
            total_failed += expected_shots
            continue

        gen = result.get("generated", 0)
        skip = result.get("skipped", 0)
        fail = result.get("failed", 0)
        total_generated += gen
        total_skipped += skip
        total_failed += fail

        for shot in result.get("shots", []):
            status = shot["status"]
            sn = shot["shot_number"]
            if status == "generated":
                path = shot.get("source_image_path", "")
                fname = path.split("/")[-1] if path else "?"
                print(f"  Shot {sn}: GENERATED → {fname}")
            elif status == "skipped":
                print(f"  Shot {sn}: skipped (already exists)")
            else:
                err = shot.get("error", "unknown")
                print(f"  Shot {sn}: FAILED — {err}")

        print(f"  [{gen} generated, {skip} skipped, {fail} failed] ({elapsed:.1f}s)")

    total_time = time.time() - start_time
    print(f"\n{'='*70}")
    print(f"COMPLETE: {total_generated} generated, {total_skipped} skipped, {total_failed} failed")
    print(f"Total time: {total_time/60:.1f} minutes")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
