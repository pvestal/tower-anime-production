#!/bin/bash

# Phase 3 Echo Brain integration validation script
echo "🔍 Validating Phase 3: Echo Brain Integration"

set -e

# Check for Echo Brain integration endpoints
echo "Testing Echo Brain integration endpoints..."
curl -f http://localhost:8328/api/echo-brain/status || { echo "❌ Echo Brain status endpoint failed"; exit 1; }

echo "✅ Phase 3 Echo Brain integration validation completed successfully"