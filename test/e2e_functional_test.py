#!/usr/bin/env python3
"""
E2E Functional Testing for Tower Anime Production System
Tests all frontend routes, API endpoints, and authentication flow
"""

import json
import time
import requests
from typing import Dict, List, Optional
from datetime import datetime
from urllib.parse import urljoin

class AnimeE2ETester:
    def __init__(self, base_url: str = "https://vestal-garcia.duckdns.org"):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.verify = False  # For self-signed cert
        self.results = []
        self.auth_token = None

    def log_result(self, test_name: str, status: str, details: str = ""):
        """Log test result."""
        result = {
            "test": test_name,
            "status": status,
            "timestamp": datetime.now().isoformat(),
            "details": details
        }
        self.results.append(result)
        emoji = "✅" if status == "PASS" else "❌"
        print(f"{emoji} {test_name}: {status} {details}")

    def test_frontend_routes(self):
        """Test all frontend routes are accessible."""
        print("\n🔍 Testing Frontend Routes...")

        routes = [
            "/anime/",
            "/anime/dashboard",
            "/anime/projects",
            "/anime/characters",
            "/anime/studio",
            "/anime/generate",
            "/anime/gallery",
            "/anime/chat"
        ]

        for route in routes:
            try:
                url = urljoin(self.base_url, route)
                response = self.session.get(url, timeout=5)

                if response.status_code == 200:
                    # Check for Vue app marker
                    if "Tower Anime Production" in response.text or "id=\"app\"" in response.text:
                        self.log_result(f"Frontend {route}", "PASS", f"Status {response.status_code}")
                    else:
                        self.log_result(f"Frontend {route}", "FAIL", "Missing Vue app markers")
                else:
                    self.log_result(f"Frontend {route}", "FAIL", f"Status {response.status_code}")
            except Exception as e:
                self.log_result(f"Frontend {route}", "FAIL", str(e))

    def test_api_endpoints(self):
        """Test API endpoints without auth."""
        print("\n🔍 Testing API Endpoints...")

        api_endpoints = [
            ("/api/anime/health", "GET"),
            ("/api/anime/projects", "GET"),
            ("/api/anime/characters", "GET"),
            ("/api/anime/models", "GET"),
            ("/api/anime/status", "GET"),
            ("/api/comfyui/models", "GET"),
            ("/api/echo/health", "GET")
        ]

        for endpoint, method in api_endpoints:
            try:
                url = urljoin(self.base_url, endpoint)

                if method == "GET":
                    response = self.session.get(url, timeout=5)
                elif method == "POST":
                    response = self.session.post(url, json={}, timeout=5)

                if response.status_code in [200, 401, 403]:  # 401/403 expected without auth
                    self.log_result(f"API {endpoint}", "PASS", f"Status {response.status_code}")
                else:
                    self.log_result(f"API {endpoint}", "FAIL", f"Status {response.status_code}")
            except Exception as e:
                self.log_result(f"API {endpoint}", "FAIL", str(e))

    def test_auth_flow(self):
        """Test authentication flow."""
        print("\n🔍 Testing Authentication...")

        # Test auth providers endpoint
        try:
            url = urljoin(self.base_url, "/api/auth/providers")
            response = self.session.get(url, timeout=5)

            if response.status_code == 200:
                data = response.json()
                providers = data.get("providers", {})

                # Check Google OAuth
                if "google" in providers and providers["google"].get("available"):
                    self.log_result("Google OAuth Config", "PASS", "Available")
                else:
                    self.log_result("Google OAuth Config", "FAIL", "Not configured")

                # Check Apple Music
                if "apple" in providers and providers["apple"].get("available"):
                    self.log_result("Apple Music Config", "PASS", "Available")
                else:
                    self.log_result("Apple Music Config", "FAIL", "Not configured")

                # Check GitHub OAuth
                if "github" in providers and providers["github"].get("available"):
                    self.log_result("GitHub OAuth Config", "PASS", "Available")
                else:
                    self.log_result("GitHub OAuth Config", "WARN", "Not configured")

            else:
                self.log_result("Auth Providers", "FAIL", f"Status {response.status_code}")

        except Exception as e:
            self.log_result("Auth Providers", "FAIL", str(e))

    def test_websocket_endpoints(self):
        """Test WebSocket connectivity."""
        print("\n🔍 Testing WebSocket Endpoints...")

        # Basic connectivity test (not actual WS connection)
        ws_endpoints = [
            "/api/anime/ws",
            "/api/coordination/ws"
        ]

        for endpoint in ws_endpoints:
            try:
                # Test if endpoint exists (will fail for WS but shows routing)
                url = urljoin(self.base_url, endpoint)
                response = self.session.get(url, timeout=5)

                # 400/426 expected for non-WS request to WS endpoint
                if response.status_code in [400, 426, 101]:
                    self.log_result(f"WebSocket {endpoint}", "PASS", "Endpoint exists")
                else:
                    self.log_result(f"WebSocket {endpoint}", "WARN", f"Status {response.status_code}")
            except Exception as e:
                self.log_result(f"WebSocket {endpoint}", "WARN", "Cannot test via HTTP")

    def test_static_assets(self):
        """Test static assets are served correctly."""
        print("\n🔍 Testing Static Assets...")

        # Test robots.txt
        try:
            response = self.session.get(urljoin(self.base_url, "/robots.txt"))
            if response.status_code == 200 and "User-agent" in response.text:
                self.log_result("robots.txt", "PASS", "Configured correctly")
            else:
                self.log_result("robots.txt", "FAIL", "Missing or misconfigured")
        except:
            self.log_result("robots.txt", "FAIL", "Not accessible")

        # Test favicon
        try:
            response = self.session.get(urljoin(self.base_url, "/anime/favicon.ico"))
            if response.status_code in [200, 304]:
                self.log_result("Favicon", "PASS", "Accessible")
            else:
                self.log_result("Favicon", "WARN", f"Status {response.status_code}")
        except:
            self.log_result("Favicon", "WARN", "Not found")

    def test_comfyui_integration(self):
        """Test ComfyUI integration."""
        print("\n🔍 Testing ComfyUI Integration...")

        try:
            # Check ComfyUI health via proxy
            response = self.session.get(
                urljoin(self.base_url, "/api/comfyui/system_stats"),
                timeout=5
            )

            if response.status_code == 200:
                data = response.json()
                if "system" in data:
                    self.log_result("ComfyUI Integration", "PASS", "Connected")
                else:
                    self.log_result("ComfyUI Integration", "WARN", "Unexpected response")
            else:
                self.log_result("ComfyUI Integration", "FAIL", f"Status {response.status_code}")
        except Exception as e:
            self.log_result("ComfyUI Integration", "FAIL", str(e))

    def test_ssl_certificate(self):
        """Test SSL certificate status."""
        print("\n🔍 Testing SSL Certificate...")

        try:
            # Test with verification enabled
            response = requests.get(self.base_url, verify=True, timeout=5)
            if response.status_code == 200:
                self.log_result("SSL Certificate", "PASS", "Valid Let's Encrypt cert")
            else:
                self.log_result("SSL Certificate", "WARN", f"Valid but status {response.status_code}")
        except requests.exceptions.SSLError:
            self.log_result("SSL Certificate", "WARN", "Self-signed or invalid")
        except Exception as e:
            self.log_result("SSL Certificate", "FAIL", str(e))

    def generate_report(self):
        """Generate test report."""
        print("\n" + "="*60)
        print("📊 E2E TEST REPORT")
        print("="*60)

        total = len(self.results)
        passed = sum(1 for r in self.results if r["status"] == "PASS")
        failed = sum(1 for r in self.results if r["status"] == "FAIL")
        warned = sum(1 for r in self.results if r["status"] == "WARN")

        print(f"\n📈 Summary:")
        print(f"  Total Tests: {total}")
        print(f"  ✅ Passed: {passed} ({passed/total*100:.1f}%)")
        print(f"  ❌ Failed: {failed} ({failed/total*100:.1f}%)")
        print(f"  ⚠️  Warnings: {warned} ({warned/total*100:.1f}%)")

        if failed > 0:
            print(f"\n❌ Failed Tests:")
            for result in self.results:
                if result["status"] == "FAIL":
                    print(f"  - {result['test']}: {result['details']}")

        # Save report to file
        report_path = f"/tmp/anime_e2e_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_path, 'w') as f:
            json.dump({
                "summary": {
                    "total": total,
                    "passed": passed,
                    "failed": failed,
                    "warned": warned,
                    "pass_rate": f"{passed/total*100:.1f}%"
                },
                "results": self.results,
                "timestamp": datetime.now().isoformat()
            }, f, indent=2)

        print(f"\n💾 Full report saved to: {report_path}")

        return passed/total >= 0.7  # 70% pass rate for success

    def run_all_tests(self):
        """Run all E2E tests."""
        print("\n🚀 Starting Tower Anime Production E2E Tests")
        print("="*60)
        print(f"Target: {self.base_url}")
        print(f"Time: {datetime.now()}")
        print("="*60)

        # Run test suites
        self.test_ssl_certificate()
        self.test_frontend_routes()
        self.test_api_endpoints()
        self.test_auth_flow()
        self.test_static_assets()
        self.test_comfyui_integration()
        self.test_websocket_endpoints()

        # Generate report
        success = self.generate_report()

        if success:
            print("\n✅ E2E TESTS COMPLETED SUCCESSFULLY!")
        else:
            print("\n⚠️  E2E TESTS COMPLETED WITH ISSUES")

        return success


if __name__ == "__main__":
    tester = AnimeE2ETester()
    success = tester.run_all_tests()
    exit(0 if success else 1)