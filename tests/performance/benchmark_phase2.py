#!/usr/bin/env python3
"""
Performance benchmarking for Phase 2 ComfyUI Workflow
"""
import time
import requests
import json

def benchmark_workflow_endpoints():
    """Benchmark workflow-related endpoints"""
    base_url = "http://localhost:8328"

    results = {
        "phase": "phase2",
        "endpoints": {
            "workflows": {"response_time_ms": 0}
        },
        "benchmark_timestamp": time.time()
    }

    try:
        # Test workflows endpoint if available
        start = time.time()
        response = requests.get(f"{base_url}/api/workflows", timeout=5)
        workflows_time = time.time() - start
        results["endpoints"]["workflows"]["response_time_ms"] = round(workflows_time * 1000, 2)
    except Exception as e:
        results["endpoints"]["workflows"]["error"] = str(e)

    with open("performance_phase2.json", "w") as f:
        json.dump(results, f, indent=2)

    print(f"✅ Phase 2 benchmarking completed")

if __name__ == "__main__":
    benchmark_workflow_endpoints()