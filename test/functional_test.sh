#!/bin/bash
# Real functional test for Tower Anime Production System

echo "========================================="
echo "Tower Anime Production - REAL TEST"
echo "========================================="

BASE_URL="https://vestal-garcia.duckdns.org"

echo -e "\n✅ 1. REAL PROJECTS (Should be 2):"
PGPASSWORD=tower_echo_brain_secret_key_2025 psql -h localhost -U patrick -d anime_production -t -c "SELECT name FROM projects;" | sed 's/^/  - /'

echo -e "\n✅ 2. REAL CHARACTERS (Should be 8):"
PGPASSWORD=tower_echo_brain_secret_key_2025 psql -h localhost -U patrick -d anime_production -t -c "SELECT DISTINCT name FROM characters;" | sed 's/^/  - /'

echo -e "\n✅ 3. AUTH PROVIDERS (Real status):"
curl -s http://localhost:8088/api/auth/providers | jq -r '.providers | to_entries[] | "  - \(.key): \(.value.available)"'

echo -e "\n✅ 4. COMFYUI STATUS:"
if curl -s http://localhost:8188/system_stats > /dev/null 2>&1; then
    echo "  - ComfyUI: ONLINE"
    QUEUE=$(curl -s http://localhost:8188/queue)
    echo "  - Queue: $(echo $QUEUE | jq -r '.queue_running | length') running, $(echo $QUEUE | jq -r '.queue_pending | length') pending"
else
    echo "  - ComfyUI: OFFLINE"
fi

echo -e "\n✅ 5. SSOT TRACKING:"
COUNT=$(PGPASSWORD=tower_echo_brain_secret_key_2025 psql -h localhost -U patrick -d anime_production -t -c "SELECT COUNT(*) FROM ssot_tracking;")
echo "  - Total records: $COUNT"
RECENT=$(PGPASSWORD=tower_echo_brain_secret_key_2025 psql -h localhost -U patrick -d anime_production -t -c "SELECT COUNT(*) FROM ssot_tracking WHERE timestamp > NOW() - INTERVAL '1 hour';")
echo "  - Last hour: $RECENT"

echo -e "\n✅ 6. GENERATION TEST:"
RESPONSE=$(curl -s -X POST $BASE_URL/api/anime/generate \
  -H "Content-Type: application/json" \
  -d '{
    "project": "Tokyo Debt Desire",
    "character": "Mei",
    "type": "image",
    "prompt": "test generation"
  }')

if echo "$RESPONSE" | grep -q "success"; then
    echo "  - Generation API: WORKING"
    TRACKING_ID=$(echo "$RESPONSE" | jq -r '.ssot_tracking_id')
    echo "  - Tracking ID: $TRACKING_ID"
else
    echo "  - Generation API: FAILED"
    echo "$RESPONSE"
fi

echo -e "\n✅ 7. RECENT OUTPUTS:"
ls -la /mnt/1TB-storage/ComfyUI/output/*.png 2>/dev/null | wc -l | xargs -I {} echo "  - Total PNG files: {}"
RECENT_FILES=$(find /mnt/1TB-storage/ComfyUI/output -name "*.png" -mtime -1 2>/dev/null | wc -l)
echo "  - Generated in last 24h: $RECENT_FILES"

echo -e "\n========================================="
echo "TEST COMPLETE - All values are REAL"
echo "========================================="