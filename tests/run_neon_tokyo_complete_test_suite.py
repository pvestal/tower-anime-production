#!/usr/bin/env python3
"""
Master Test Execution Script: Neon Tokyo Nights Complete Testing Suite
Orchestrates all testing phases and generates comprehensive reports
"""

import os
import sys
import subprocess
import json
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import test suites
from tests.integration.test_neon_tokyo_nights_lifecycle import NeonTokyoNightsTestSuite
from tests.integration.test_frontend_e2e_neon_tokyo import FrontendE2ETestSuite
from tests.performance.test_neon_tokyo_performance import PerformanceTestSuite

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MasterTestOrchestrator:
    """Master orchestrator for all Neon Tokyo Nights testing"""

    def __init__(self):
        self.start_time = datetime.now()
        self.test_results = {}
        self.reports_dir = Path("/tmp/claude/neon_tokyo_tests")
        self.reports_dir.mkdir(parents=True, exist_ok=True)

        # Test configuration
        self.test_config = {
            "project_name": "Neon Tokyo Nights",
            "test_environment": "tower_anime_production",
            "services_required": [
                {"name": "anime_production", "port": 8328},
                {"name": "echo_brain", "port": 8309},
                {"name": "comfyui", "port": 8188},
                {"name": "postgresql", "port": 5432}
            ],
            "test_phases": [
                {"name": "system_readiness", "critical": True},
                {"name": "integration_tests", "critical": True},
                {"name": "frontend_e2e", "critical": False},
                {"name": "performance_tests", "critical": False},
                {"name": "cleanup_and_reporting", "critical": True}
            ]
        }

    def check_system_readiness(self):
        """Verify all required services are accessible"""
        logger.info("Phase 1: Checking system readiness...")

        readiness_results = {
            "services_checked": [],
            "all_services_ready": True,
            "critical_services_ready": True,
            "warnings": []
        }

        for service in self.test_config["services_required"]:
            service_ready = self._check_service_health(service["name"], service["port"])
            readiness_results["services_checked"].append({
                "name": service["name"],
                "port": service["port"],
                "ready": service_ready
            })

            if not service_ready:
                readiness_results["all_services_ready"] = False
                if service["name"] in ["anime_production", "postgresql"]:
                    readiness_results["critical_services_ready"] = False
                else:
                    readiness_results["warnings"].append(f"{service['name']} not available - tests will include fallback scenarios")

        self.test_results["system_readiness"] = readiness_results

        if not readiness_results["critical_services_ready"]:
            raise Exception("Critical services not available - cannot proceed with testing")

        logger.info(f"✓ System readiness check completed. Ready: {readiness_results['all_services_ready']}")
        return readiness_results

    def _check_service_health(self, service_name: str, port: int):
        """Check if a service is healthy"""
        try:
            if service_name == "anime_production":
                import requests
                response = requests.get(f"http://192.168.50.135:{port}/api/anime/health", timeout=5)
                return response.status_code == 200

            elif service_name == "echo_brain":
                import requests
                response = requests.get(f"http://192.168.50.135:{port}/api/echo/health", timeout=5)
                return response.status_code == 200

            elif service_name == "comfyui":
                import requests
                response = requests.get(f"http://192.168.50.135:{port}/", timeout=5)
                return response.status_code == 200

            elif service_name == "postgresql":
                import psycopg2
                conn = psycopg2.connect(
                    host="192.168.50.135",
                    port=port,
                    database="anime_production",
                    user="patrick",
                    password="tower_echo_brain_secret_key_2025"
                )
                conn.close()
                return True

        except Exception as e:
            logger.warning(f"Service {service_name} health check failed: {e}")
            return False

    def run_integration_tests(self):
        """Run the complete integration test suite"""
        logger.info("Phase 2: Running integration tests...")

        try:
            integration_suite = NeonTokyoNightsTestSuite()
            integration_results = integration_suite.run_complete_test_suite()
            integration_report = integration_suite.generate_test_report()

            self.test_results["integration_tests"] = {
                "status": "completed",
                "results": integration_results,
                "report": integration_report,
                "timestamp": datetime.now().isoformat()
            }

            # Save detailed integration report
            integration_report_path = self.reports_dir / f"integration_report_{int(time.time())}.json"
            with open(integration_report_path, "w") as f:
                json.dump(integration_report, f, indent=2)

            logger.info("✓ Integration tests completed successfully")

        except Exception as e:
            logger.error(f"Integration tests failed: {e}")
            self.test_results["integration_tests"] = {
                "status": "failed",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    def run_frontend_e2e_tests(self):
        """Run frontend end-to-end tests"""
        logger.info("Phase 3: Running frontend E2E tests...")

        try:
            # Check if selenium is available
            selenium_available = self._check_selenium_availability()

            if not selenium_available:
                logger.warning("Selenium not available - skipping E2E tests")
                self.test_results["frontend_e2e"] = {
                    "status": "skipped",
                    "reason": "Selenium WebDriver not available",
                    "timestamp": datetime.now().isoformat()
                }
                return

            e2e_suite = FrontendE2ETestSuite()
            e2e_results = e2e_suite.run_e2e_test_suite()
            e2e_report = e2e_suite.generate_e2e_report()

            self.test_results["frontend_e2e"] = {
                "status": "completed",
                "results": e2e_results,
                "report": e2e_report,
                "timestamp": datetime.now().isoformat()
            }

            # Save E2E report
            e2e_report_path = self.reports_dir / f"e2e_report_{int(time.time())}.json"
            with open(e2e_report_path, "w") as f:
                json.dump(e2e_report, f, indent=2)

            logger.info("✓ Frontend E2E tests completed")

        except Exception as e:
            logger.error(f"Frontend E2E tests failed: {e}")
            self.test_results["frontend_e2e"] = {
                "status": "failed",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    def _check_selenium_availability(self):
        """Check if Selenium WebDriver is available"""
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options

            chrome_options = Options()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")

            # Try to create a webdriver instance
            driver = webdriver.Chrome(options=chrome_options)
            driver.quit()
            return True

        except Exception:
            return False

    def run_performance_tests(self):
        """Run performance testing suite"""
        logger.info("Phase 4: Running performance tests...")

        try:
            perf_suite = PerformanceTestSuite()
            perf_results = perf_suite.run_performance_test_suite()
            perf_report = perf_suite.generate_performance_report()

            self.test_results["performance_tests"] = {
                "status": "completed",
                "results": perf_results,
                "report": perf_report,
                "timestamp": datetime.now().isoformat()
            }

            # Save performance report
            perf_report_path = self.reports_dir / f"performance_report_{int(time.time())}.json"
            with open(perf_report_path, "w") as f:
                json.dump(perf_report, f, indent=2)

            logger.info("✓ Performance tests completed")

        except Exception as e:
            logger.error(f"Performance tests failed: {e}")
            self.test_results["performance_tests"] = {
                "status": "failed",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    def generate_master_report(self):
        """Generate comprehensive master test report"""
        logger.info("Phase 5: Generating master test report...")

        end_time = datetime.now()
        duration = end_time - self.start_time

        # Calculate overall statistics
        total_phases = len(self.test_config["test_phases"])
        completed_phases = sum(1 for phase_name in [p["name"] for p in self.test_config["test_phases"]]
                             if self.test_results.get(phase_name, {}).get("status") == "completed")

        # Extract key metrics
        integration_summary = self.test_results.get("integration_tests", {}).get("report", {}).get("summary", {})
        e2e_summary = self.test_results.get("frontend_e2e", {}).get("report", {}).get("summary", {})
        perf_summary = self.test_results.get("performance_tests", {}).get("report", {}).get("summary", {})

        master_report = {
            "test_suite": "Neon Tokyo Nights Master Test Suite",
            "project": self.test_config["project_name"],
            "execution_summary": {
                "start_time": self.start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "duration_minutes": duration.total_seconds() / 60,
                "total_phases": total_phases,
                "completed_phases": completed_phases,
                "success_rate": (completed_phases / total_phases) * 100 if total_phases > 0 else 0
            },
            "system_readiness": self.test_results.get("system_readiness", {}),
            "test_results_summary": {
                "integration_tests": {
                    "status": self.test_results.get("integration_tests", {}).get("status", "not_run"),
                    "summary": integration_summary
                },
                "frontend_e2e": {
                    "status": self.test_results.get("frontend_e2e", {}).get("status", "not_run"),
                    "summary": e2e_summary
                },
                "performance_tests": {
                    "status": self.test_results.get("performance_tests", {}).get("status", "not_run"),
                    "summary": perf_summary
                }
            },
            "detailed_results": self.test_results,
            "recommendations": self._generate_master_recommendations(),
            "next_steps": self._generate_next_steps()
        }

        # Save master report
        master_report_path = self.reports_dir / f"master_report_{int(time.time())}.json"
        with open(master_report_path, "w") as f:
            json.dump(master_report, f, indent=2)

        # Generate human-readable summary
        summary_path = self.reports_dir / f"test_summary_{int(time.time())}.txt"
        with open(summary_path, "w") as f:
            f.write(self._generate_human_readable_summary(master_report))

        logger.info(f"✓ Master report generated: {master_report_path}")
        logger.info(f"✓ Summary report generated: {summary_path}")

        return master_report

    def _generate_master_recommendations(self):
        """Generate master recommendations based on all test results"""
        recommendations = []

        # System readiness recommendations
        readiness = self.test_results.get("system_readiness", {})
        if not readiness.get("all_services_ready", True):
            recommendations.append({
                "category": "Infrastructure",
                "priority": "high",
                "issue": "Not all services are available",
                "recommendation": "Ensure all Tower services are running before production deployment"
            })

        # Integration test recommendations
        integration_results = self.test_results.get("integration_tests", {})
        if integration_results.get("status") == "failed":
            recommendations.append({
                "category": "Integration",
                "priority": "critical",
                "issue": "Integration tests failed",
                "recommendation": "Review integration test failures before proceeding with development"
            })

        # Performance recommendations
        perf_report = self.test_results.get("performance_tests", {}).get("report", {})
        if perf_report.get("summary", {}).get("overall_status") == "critical":
            recommendations.append({
                "category": "Performance",
                "priority": "high",
                "issue": "Performance issues detected",
                "recommendation": "Address performance bottlenecks identified in testing"
            })

        return recommendations

    def _generate_next_steps(self):
        """Generate recommended next steps based on test results"""
        next_steps = []

        # Check if all critical tests passed
        critical_failures = []
        if self.test_results.get("integration_tests", {}).get("status") == "failed":
            critical_failures.append("integration_tests")

        if critical_failures:
            next_steps.extend([
                "Fix critical test failures before continuing development",
                "Review error logs for failed test components",
                "Re-run tests after implementing fixes"
            ])
        else:
            next_steps.extend([
                "Proceed with Neon Tokyo Nights project development",
                "Monitor performance metrics identified in testing",
                "Set up continuous testing pipeline for future changes"
            ])

        return next_steps

    def _generate_human_readable_summary(self, master_report):
        """Generate human-readable test summary"""
        summary_lines = [
            "=" * 80,
            "NEON TOKYO NIGHTS - COMPLETE TEST SUITE RESULTS",
            "=" * 80,
            "",
            f"Project: {master_report['project']}",
            f"Execution Time: {master_report['execution_summary']['duration_minutes']:.2f} minutes",
            f"Success Rate: {master_report['execution_summary']['success_rate']:.1f}%",
            "",
            "PHASE RESULTS:",
            "=" * 40
        ]

        # Add phase results
        for phase_name, phase_data in master_report["test_results_summary"].items():
            status = phase_data["status"]
            status_icon = "✓" if status == "completed" else "✗" if status == "failed" else "⚠"
            summary_lines.append(f"{status_icon} {phase_name.replace('_', ' ').title()}: {status}")

        summary_lines.extend([
            "",
            "KEY METRICS:",
            "=" * 40
        ])

        # Add integration test metrics if available
        integration_summary = master_report["test_results_summary"]["integration_tests"].get("summary", {})
        if integration_summary:
            summary_lines.append(f"Integration Tests - Total: {integration_summary.get('total_tests', 'N/A')}, "
                                f"Passed: {integration_summary.get('passed_tests', 'N/A')}")

        # Add performance metrics if available
        perf_summary = master_report["test_results_summary"]["performance_tests"].get("summary", {})
        if perf_summary:
            summary_lines.append(f"Performance Status: {perf_summary.get('overall_status', 'N/A')}")

        # Add recommendations
        if master_report["recommendations"]:
            summary_lines.extend([
                "",
                "RECOMMENDATIONS:",
                "=" * 40
            ])
            for rec in master_report["recommendations"]:
                summary_lines.append(f"• [{rec['priority'].upper()}] {rec['recommendation']}")

        # Add next steps
        if master_report["next_steps"]:
            summary_lines.extend([
                "",
                "NEXT STEPS:",
                "=" * 40
            ])
            for step in master_report["next_steps"]:
                summary_lines.append(f"• {step}")

        summary_lines.extend([
            "",
            "=" * 80,
            f"Report generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "=" * 80
        ])

        return "\n".join(summary_lines)

    def run_complete_test_suite(self):
        """Run the complete test suite"""
        logger.info(f"Starting complete test suite for {self.test_config['project_name']}...")

        try:
            # Phase 1: System readiness
            self.check_system_readiness()

            # Phase 2: Integration tests
            self.run_integration_tests()

            # Phase 3: Frontend E2E tests (if available)
            self.run_frontend_e2e_tests()

            # Phase 4: Performance tests
            self.run_performance_tests()

            # Phase 5: Generate master report
            master_report = self.generate_master_report()

            logger.info("✓ Complete test suite finished successfully")
            return master_report

        except Exception as e:
            logger.error(f"Test suite execution failed: {e}")
            self.test_results["execution_error"] = str(e)

            # Still try to generate a report
            try:
                return self.generate_master_report()
            except:
                return {"error": "Test suite failed and report generation failed", "details": str(e)}

def main():
    """Main execution function"""
    print(f"Starting Neon Tokyo Nights Complete Test Suite...")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    orchestrator = MasterTestOrchestrator()
    master_report = orchestrator.run_complete_test_suite()

    # Print summary
    print("\n" + "=" * 80)
    print("EXECUTION COMPLETED")
    print("=" * 80)
    print(f"Duration: {master_report.get('execution_summary', {}).get('duration_minutes', 'N/A'):.2f} minutes")
    print(f"Success Rate: {master_report.get('execution_summary', {}).get('success_rate', 'N/A'):.1f}%")
    print(f"Reports saved to: {orchestrator.reports_dir}")

    return 0 if master_report.get("execution_summary", {}).get("success_rate", 0) > 80 else 1

if __name__ == "__main__":
    sys.exit(main())