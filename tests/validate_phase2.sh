#!/bin/bash

# Phase 2 ComfyUI Workflow validation script
echo "🔍 Validating Phase 2: ComfyUI Workflow Persistence"

set -e

# Check for workflow persistence endpoints
echo "Testing ComfyUI workflow endpoints..."
curl -f http://localhost:8328/api/workflows || { echo "❌ Workflows endpoint failed"; exit 1; }

echo "✅ Phase 2 ComfyUI Workflow validation completed successfully"