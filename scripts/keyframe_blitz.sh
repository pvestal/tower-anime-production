#!/bin/bash
# Keyframe Blitz — generate keyframe images for all shots in a scene (~18s each)
# Usage: ./scripts/keyframe_blitz.sh <scene_id> [--all]
#   --all: Re-generate even for shots that already have source images

set -euo pipefail

SCENE_ID="${1:?Usage: $0 <scene_id> [--all]}"
SKIP="true"
if [[ "${2:-}" == "--all" ]]; then
  SKIP="false"
fi

echo "Keyframe blitz for scene $SCENE_ID (skip_existing=$SKIP)..."
curl -s -X POST "http://localhost:8401/api/scenes/${SCENE_ID}/keyframe-blitz?skip_existing=${SKIP}" | jq .
