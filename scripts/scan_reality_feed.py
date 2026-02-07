#!/usr/bin/env python3
"""
Run this on a cron schedule (e.g., every hour) to capture real events as story material.
Usage: python3 scripts/scan_reality_feed.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.story_engine.reality_feed_watcher import RealityFeedWatcher

# Echo Chamber project ID
PROJECT_ID = 43

watcher = RealityFeedWatcher(project_id=PROJECT_ID)
results = watcher.run_full_scan()

print(f"Reality feed scan complete:")
print(f"  Git commits captured: {results['git_commits']}")
print(f"  Echo Brain logs: {results['echo_logs']}")
print(f"  ComfyUI errors: {results['comfyui_errors']}")
print(f"  Total events stored: {results['total_events']}")

if results["events"]:
    print("\nSample events:")
    for event in results["events"][:3]:
        print(f"  - [{event['event_type']}] {event['content'][:80]}...")