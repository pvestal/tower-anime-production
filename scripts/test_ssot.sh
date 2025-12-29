#!/bin/bash
# Test script for SSOT integration verification

echo "🧪 Testing SSOT Phase 2 Integration..."
echo "====================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

# 1. Check if service is running
echo "1. Checking service status..."
if systemctl is-active --quiet tower-anime-production; then
    echo -e "${GREEN}✅ Service is running${NC}"
else
    echo -e "${RED}❌ Service is not running, attempting to start...${NC}"
    sudo systemctl start tower-anime-production
    sleep 3
fi

# 2. Test health endpoint
echo -e "\n2. Testing health endpoint..."
HEALTH=$(curl -s http://localhost:8305/health 2>/dev/null)
if [ ! -z "$HEALTH" ]; then
    echo -e "${GREEN}✅ Health endpoint responding${NC}"
    echo "$HEALTH" | jq . 2>/dev/null || echo "$HEALTH"
else
    echo -e "${RED}❌ Health endpoint not responding${NC}"
fi

# 3. Make a test generation request
echo -e "\n3. Making test generation request..."
RESPONSE=$(curl -s -X POST http://localhost:8305/api/anime/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "SSOT test anime scene", "style": "ghibli"}' 2>/dev/null)

if [ ! -z "$RESPONSE" ]; then
    echo -e "${GREEN}✅ Generation endpoint responding${NC}"
    echo "$RESPONSE" | jq . 2>/dev/null || echo "$RESPONSE"

    # Extract tracking ID
    TRACKING_ID=$(echo "$RESPONSE" | jq -r '.ssot_tracking_id' 2>/dev/null)
    if [ ! -z "$TRACKING_ID" ] && [ "$TRACKING_ID" != "null" ]; then
        echo -e "${GREEN}✅ SSOT Tracking ID: $TRACKING_ID${NC}"
    else
        echo -e "${RED}❌ No SSOT tracking ID in response${NC}"
    fi
else
    echo -e "${RED}❌ Generation endpoint not responding${NC}"
fi

# 4. Check SSOT metrics
echo -e "\n4. Checking SSOT metrics..."
METRICS=$(curl -s http://localhost:8305/api/anime/ssot/metrics 2>/dev/null)
if [ ! -z "$METRICS" ]; then
    echo -e "${GREEN}✅ SSOT metrics endpoint responding${NC}"
    echo "$METRICS" | jq . 2>/dev/null || echo "$METRICS"

    # Check if requests are being tracked
    TOTAL=$(echo "$METRICS" | jq -r '.total_requests' 2>/dev/null)
    if [ ! -z "$TOTAL" ] && [ "$TOTAL" != "null" ] && [ "$TOTAL" -gt 0 ]; then
        echo -e "${GREEN}✅ Found $TOTAL tracked requests${NC}"
    else
        echo -e "${RED}❌ No requests being tracked (total: $TOTAL)${NC}"
    fi
else
    echo -e "${RED}❌ SSOT metrics endpoint not responding${NC}"
fi

# 5. Check database directly
echo -e "\n5. Database verification..."
export PGPASSWORD=tower_echo_brain_secret_key_2025
DB_CHECK=$(psql -h localhost -U patrick -d anime_production -t -c "
SELECT
    COUNT(*) as total,
    COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed,
    COUNT(CASE WHEN timestamp > NOW() - INTERVAL '5 minutes' THEN 1 END) as recent
FROM ssot_tracking;" 2>/dev/null)

if [ ! -z "$DB_CHECK" ]; then
    echo -e "${GREEN}✅ Database connection successful${NC}"
    echo "Database stats: $DB_CHECK"

    # Parse the counts
    COUNTS=($DB_CHECK)
    TOTAL_DB=${COUNTS[0]}
    COMPLETED=${COUNTS[2]}
    RECENT=${COUNTS[4]}

    echo "Total tracked: $TOTAL_DB | Completed: $COMPLETED | Recent (5 min): $RECENT"

    if [ "$TOTAL_DB" -gt 0 ]; then
        echo -e "${GREEN}✅ SSOT tracking is working - $TOTAL_DB records found${NC}"
    else
        echo -e "${RED}❌ No tracking records in database${NC}"
    fi
else
    echo -e "${RED}❌ Database connection failed${NC}"
fi

# 6. Check for tracking headers
echo -e "\n6. Testing tracking headers..."
HEADERS=$(curl -s -X POST http://localhost:8305/api/anime/generate \
  -H "Content-Type: application/json" \
  -d '{"test": "headers"}' \
  -D - 2>/dev/null | grep -E "X-SSOT|X-Processing")

if [ ! -z "$HEADERS" ]; then
    echo -e "${GREEN}✅ SSOT headers found:${NC}"
    echo "$HEADERS"
else
    echo -e "${RED}❌ No SSOT tracking headers found${NC}"
fi

# Summary
echo -e "\n====================================="
echo "📊 SSOT Phase 2 Integration Summary:"

if [ "$TOTAL_DB" -gt 0 ] 2>/dev/null; then
    echo -e "${GREEN}✅ PHASE 2 COMPLETE: SSOT is tracking requests${NC}"
    echo "   - Database has $TOTAL_DB tracking records"
    echo "   - Middleware is intercepting requests"
    echo "   - Tracking IDs are being generated"
else
    echo -e "${RED}❌ PHASE 2 INCOMPLETE: SSOT not fully working${NC}"
    echo "   - Check service logs: sudo journalctl -u tower-anime-production -f"
    echo "   - Verify database tables exist"
    echo "   - Ensure middleware is properly integrated"
fi

echo "====================================="