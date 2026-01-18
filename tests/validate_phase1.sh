#!/bin/bash

# Phase 1 SSOT Bridge validation script
echo "🔍 Validating Phase 1: SSOT Bridge Implementation"

set -e

# Check for required API endpoints
echo "Testing SSOT API endpoints..."
curl -f http://localhost:8328/api/projects || { echo "❌ Projects endpoint failed"; exit 1; }
curl -f http://localhost:8328/api/characters || { echo "❌ Characters endpoint failed"; exit 1; }

echo "✅ Phase 1 SSOT Bridge validation completed successfully"