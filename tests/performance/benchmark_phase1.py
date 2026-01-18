#!/usr/bin/env python3
"""
Performance benchmarking for Phase 1 SSOT Bridge
"""
import time
import requests
import json

def benchmark_api_endpoints():
    """Benchmark core API endpoints"""
    base_url = "http://localhost:8328"

    # Test projects endpoint
    start = time.time()
    response = requests.get(f"{base_url}/api/projects")
    projects_time = time.time() - start

    # Test characters endpoint
    start = time.time()
    response = requests.get(f"{base_url}/api/characters")
    characters_time = time.time() - start

    # Generate performance report
    results = {
        "phase": "phase1",
        "endpoints": {
            "projects": {"response_time_ms": round(projects_time * 1000, 2)},
            "characters": {"response_time_ms": round(characters_time * 1000, 2)}
        },
        "benchmark_timestamp": time.time()
    }

    with open("performance_phase1.json", "w") as f:
        json.dump(results, f, indent=2)

    print(f"✅ Phase 1 benchmarking completed")
    print(f"Projects endpoint: {results['endpoints']['projects']['response_time_ms']}ms")
    print(f"Characters endpoint: {results['endpoints']['characters']['response_time_ms']}ms")

if __name__ == "__main__":
    benchmark_api_endpoints()