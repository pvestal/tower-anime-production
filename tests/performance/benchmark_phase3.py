#!/usr/bin/env python3
"""
Performance benchmarking for Phase 3 Echo Brain Integration
"""
import time
import requests
import json

def benchmark_echo_brain_endpoints():
    """Benchmark Echo Brain integration endpoints"""
    base_url = "http://localhost:8328"

    results = {
        "phase": "phase3",
        "endpoints": {
            "echo_brain_status": {"response_time_ms": 0}
        },
        "benchmark_timestamp": time.time()
    }

    try:
        # Test Echo Brain status endpoint if available
        start = time.time()
        response = requests.get(f"{base_url}/api/echo-brain/status", timeout=5)
        echo_time = time.time() - start
        results["endpoints"]["echo_brain_status"]["response_time_ms"] = round(echo_time * 1000, 2)
    except Exception as e:
        results["endpoints"]["echo_brain_status"]["error"] = str(e)

    with open("performance_phase3.json", "w") as f:
        json.dump(results, f, indent=2)

    print(f"✅ Phase 3 benchmarking completed")

if __name__ == "__main__":
    benchmark_echo_brain_endpoints()