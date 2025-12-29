#!/bin/bash

# Phase 2: SSOT Middleware Integration Deployment Script
# This script deploys the SSOT tracking middleware to capture all generation requests

echo "🚀 Starting Phase 2: SSOT Middleware Integration"
echo "=============================================="
echo "Timestamp: $(date)"
echo ""

# Color codes for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Set environment variables
export DATABASE_PASSWORD="tower_echo_brain_secret_key_2025"
export DB_USER="patrick"
export DB_NAME="anime_production"

# Function to check command success
check_status() {
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ $1 completed successfully${NC}"
    else
        echo -e "${RED}❌ $1 failed${NC}"
        exit 1
    fi
}

# 1. Verify database connection
echo "1. Verifying database connection..."
PGPASSWORD=$DATABASE_PASSWORD psql -h localhost -U $DB_USER -d $DB_NAME -c "SELECT 1" > /dev/null 2>&1
check_status "Database connection verification"

# 2. Check if SSOT tables exist
echo "2. Checking SSOT tables..."
TABLES_EXIST=$(PGPASSWORD=$DATABASE_PASSWORD psql -h localhost -U $DB_USER -d $DB_NAME -t -c "
    SELECT COUNT(*)
    FROM information_schema.tables
    WHERE table_schema = 'public'
        AND table_name IN ('ssot_tracking', 'generation_workflow_decisions')
")

if [ "$TABLES_EXIST" -eq "2" ]; then
    echo -e "${GREEN}✅ SSOT tables already exist${NC}"
else
    echo -e "${YELLOW}⚠️  Some SSOT tables missing, running migration...${NC}"
    PGPASSWORD=$DATABASE_PASSWORD psql -h localhost -U $DB_USER -d $DB_NAME -f /opt/tower-anime-production/sql/migrations/002_ssot_tracking.sql
    check_status "Database migration"
fi

# 3. Install Python dependencies
echo "3. Installing Python dependencies..."
cd /opt/tower-anime-production
source venv/bin/activate

pip install asyncpg redis aiohttp --quiet
check_status "Python dependency installation"

# 4. Update main API to include SSOT middleware
echo "4. Integrating SSOT middleware into main API..."

# Check if middleware is already integrated
if grep -q "ssot_tracker" /opt/tower-anime-production/api/main.py; then
    echo -e "${GREEN}✅ SSOT middleware already integrated${NC}"
else
    echo "Adding SSOT middleware to main API..."

    # Create a backup
    cp /opt/tower-anime-production/api/main.py /opt/tower-anime-production/api/main.py.backup

    # Add middleware import and initialization
    cat << 'EOF' > /tmp/middleware_integration.py
import sys
import os

# Read the main.py file
with open('/opt/tower-anime-production/api/main.py', 'r') as f:
    lines = f.readlines()

# Find where to add imports (after other imports)
import_index = 0
for i, line in enumerate(lines):
    if 'from fastapi import' in line:
        import_index = i + 1
        break

# Add SSOT tracker import
middleware_import = """
# SSOT Middleware Integration
sys.path.append('/opt/tower-anime-production/middleware')
from ssot_tracker import SSOTTracker
from dashboard.ssot.ssot_monitor import router as ssot_router

"""

# Find where to add middleware (after app initialization)
app_index = 0
for i, line in enumerate(lines):
    if 'app = FastAPI(' in line:
        # Find the closing parenthesis
        for j in range(i, len(lines)):
            if ')' in lines[j] and not '(' in lines[j][lines[j].index(')'):]:
                app_index = j + 1
                break
        break

# Add middleware initialization
middleware_init = """
# Initialize SSOT tracking
ssot_tracker = SSOTTracker(
    f"postgresql://patrick:{os.getenv('DATABASE_PASSWORD', 'tower_echo_brain_secret_key_2025')}@localhost/anime_production"
)

@app.on_event("startup")
async def startup_event():
    await ssot_tracker.initialize()
    logger.info("SSOT tracking initialized")

@app.on_event("shutdown")
async def shutdown_event():
    await ssot_tracker.close()
    logger.info("SSOT tracking shut down")

# Add SSOT middleware
app.add_middleware(
    lambda app: ssot_tracker
)

# Include SSOT monitoring dashboard
app.include_router(ssot_router, prefix="/api/anime")

"""

# Insert the imports
lines.insert(import_index, middleware_import)

# Insert the middleware initialization
lines.insert(app_index + 1, middleware_init)

# Write the updated file
with open('/opt/tower-anime-production/api/main.py', 'w') as f:
    f.writelines(lines)

print("✅ Middleware integration complete")
EOF

    python3 /tmp/middleware_integration.py
    check_status "Middleware integration"
fi

# 5. Test SSOT tracking endpoint
echo "5. Testing SSOT monitoring endpoints..."

# Restart the service first
sudo systemctl restart tower-anime-production
sleep 5

# Test health endpoint
HEALTH_RESPONSE=$(curl -s http://localhost:8305/api/anime/ssot/health 2>/dev/null | head -1)
if echo "$HEALTH_RESPONSE" | grep -q "status"; then
    echo -e "${GREEN}✅ SSOT health endpoint responding${NC}"
else
    echo -e "${YELLOW}⚠️  SSOT health endpoint not responding (may need manual integration)${NC}"
fi

# 6. Create verification script
echo "6. Creating verification script..."
cat << 'EOF' > /opt/tower-anime-production/scripts/verify-ssot-integration.sh
#!/bin/bash

echo "🔍 Verifying SSOT Integration"
echo "=============================="

# Test tracking
TEST_ID="test_$(date +%s)"
echo "Testing generation endpoint with tracking..."

# Make a test request
RESPONSE=$(curl -s -X POST http://localhost:8305/api/anime/generate \
    -H "Content-Type: application/json" \
    -d '{"prompt": "test", "test_id": "'$TEST_ID'"}' 2>/dev/null)

# Check for SSOT tracking ID in response headers
if curl -s -I -X POST http://localhost:8305/api/anime/generate \
    -H "Content-Type: application/json" \
    -d '{"prompt": "test"}' 2>/dev/null | grep -q "X-SSOT-Tracking-ID"; then
    echo "✅ SSOT tracking ID found in response headers"
else
    echo "⚠️  No SSOT tracking ID in response headers"
fi

# Check database for tracking record
TRACKING_COUNT=$(PGPASSWORD=tower_echo_brain_secret_key_2025 psql -h localhost -U patrick -d anime_production -t -c "
    SELECT COUNT(*) FROM ssot_tracking WHERE timestamp > NOW() - INTERVAL '1 minute'
")

if [ "$TRACKING_COUNT" -gt "0" ]; then
    echo "✅ Found $TRACKING_COUNT tracking records in database"
else
    echo "❌ No tracking records found in database"
fi

# Get metrics
echo ""
echo "📊 Current SSOT Metrics:"
curl -s http://localhost:8305/api/anime/ssot/metrics 2>/dev/null | python3 -m json.tool | head -20

echo ""
echo "✅ SSOT verification complete"
EOF

chmod +x /opt/tower-anime-production/scripts/verify-ssot-integration.sh
check_status "Verification script creation"

# 7. Run verification
echo "7. Running verification..."
/opt/tower-anime-production/scripts/verify-ssot-integration.sh

# 8. Summary
echo ""
echo "=========================================="
echo -e "${GREEN}✅ Phase 2 SSOT Integration Deployment Complete!${NC}"
echo ""
echo "📊 Dashboard Access:"
echo "  - Metrics: http://localhost:8305/api/anime/ssot/metrics"
echo "  - Live Feed: http://localhost:8305/api/anime/ssot/live-feed"
echo "  - Health: http://localhost:8305/api/anime/ssot/health"
echo ""
echo "📝 Next Steps:"
echo "  1. Monitor the dashboard for tracking data"
echo "  2. Verify all generation endpoints are being tracked"
echo "  3. Check for any errors in: sudo journalctl -u tower-anime-production -f"
echo "  4. Once validated, proceed to Phase 3: Event-Driven Architecture"
echo ""
echo "🔄 To rollback if needed:"
echo "  cp /opt/tower-anime-production/api/main.py.backup /opt/tower-anime-production/api/main.py"
echo "  sudo systemctl restart tower-anime-production"
echo "=========================================="