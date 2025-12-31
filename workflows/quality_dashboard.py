#!/usr/bin/env python3
"""
Quality Dashboard - View and analyze quality verification results
"""

import psycopg2
from datetime import datetime
from pathlib import Path
import json

class QualityDashboard:
    """Dashboard for quality verification results"""

    def __init__(self):
        self.conn = psycopg2.connect(
            host="localhost",
            database="anime_production",
            user="patrick",
            password="tower_echo_brain_secret_key_2025"
        )

    def generate_dashboard(self):
        """Generate comprehensive quality dashboard"""
        cur = self.conn.cursor()

        print("=" * 80)
        print(" " * 20 + "QUALITY VERIFICATION DASHBOARD")
        print("=" * 80)
        print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()

        # Overall statistics
        cur.execute("""
            SELECT
                COUNT(*) as total_tests,
                AVG(similarity_score) as avg_score,
                MAX(similarity_score) as max_score,
                MIN(similarity_score) as min_score,
                COUNT(CASE WHEN similarity_score > 0.70 THEN 1 END) as passed,
                COUNT(CASE WHEN similarity_score <= 0.70 THEN 1 END) as failed
            FROM quality_verifications
        """)

        stats = cur.fetchone()
        total, avg, max_score, min_score, passed, failed = stats

        print("📊 OVERALL STATISTICS")
        print("-" * 80)
        print(f"  Total Tests Run:     {total}")
        print(f"  Tests Passed (>70%): {passed} ({passed/total*100:.0f}%)")
        print(f"  Tests Failed:        {failed} ({failed/total*100:.0f}%)")
        print(f"  Average Similarity:  {avg:.1%}")
        print(f"  Best Score:          {max_score:.1%}")
        print(f"  Worst Score:         {min_score:.1%}")
        print()

        # Best performers
        print("🏆 TOP PERFORMING POSES")
        print("-" * 80)
        cur.execute("""
            SELECT DISTINCT ON (pose_description)
                pose_description,
                similarity_score,
                test_name,
                created_at
            FROM quality_verifications
            ORDER BY pose_description, similarity_score DESC
            LIMIT 5
        """)

        for i, (pose, score, test, created) in enumerate(cur.fetchall(), 1):
            status = "✅" if score > 0.70 else "❌"
            print(f"  {i}. {status} {pose[:40]:<40} {score:.1%}")

        print()

        # Pose analysis
        print("📈 POSE PERFORMANCE ANALYSIS")
        print("-" * 80)
        cur.execute("""
            SELECT
                CASE
                    WHEN pose_description LIKE '%frontal%' THEN 'Frontal'
                    WHEN pose_description LIKE '%smile%' THEN 'Smile'
                    WHEN pose_description LIKE '%profile%' THEN 'Profile'
                    WHEN pose_description LIKE '%confident%' THEN 'Confident'
                    WHEN pose_description LIKE '%professional%' THEN 'Professional'
                    ELSE 'Other'
                END as pose_type,
                COUNT(*) as attempts,
                AVG(similarity_score) as avg_score,
                MAX(similarity_score) as best_score
            FROM quality_verifications
            GROUP BY pose_type
            ORDER BY avg_score DESC
        """)

        print(f"  {'Pose Type':<15} {'Attempts':<10} {'Avg Score':<12} {'Best Score':<12} Status")
        print(f"  {'-'*15} {'-'*10} {'-'*12} {'-'*12} {'-'*10}")

        for pose_type, attempts, avg_score, best_score in cur.fetchall():
            status = "EXCELLENT" if avg_score > 0.75 else "GOOD" if avg_score > 0.70 else "NEEDS WORK"
            print(f"  {pose_type:<15} {attempts:<10} {avg_score:<12.1%} {best_score:<12.1%} {status}")

        print()

        # Time series
        print("📅 QUALITY TREND (Last 10 Tests)")
        print("-" * 80)
        cur.execute("""
            SELECT
                test_name,
                similarity_score,
                created_at
            FROM quality_verifications
            ORDER BY created_at DESC
            LIMIT 10
        """)

        for test, score, created in cur.fetchall():
            bar_length = int(score * 50)
            bar = "█" * bar_length + "░" * (50 - bar_length)
            time_str = created.strftime("%H:%M:%S")
            print(f"  {time_str} [{bar}] {score:.1%}")

        print()

        # Recommendations
        print("💡 RECOMMENDATIONS")
        print("-" * 80)

        if avg < 0.70:
            print("  ⚠️  Average similarity below 70% threshold")
            print("  • Consider adjusting LoRA strength")
            print("  • Review ControlNet strength settings")
            print("  • Ensure reference image quality is high")
        elif avg < 0.80:
            print("  ✅ Good quality overall, room for improvement")
            print("  • Focus on poses with <70% scores")
            print("  • Fine-tune sampler settings")
            print("  • Consider pose-specific prompts")
        else:
            print("  🌟 Excellent quality achieved!")
            print("  • Current settings are optimal")
            print("  • Ready for production deployment")

        # Profile status
        cur.execute("""
            SELECT name, quality_score
            FROM generation_profiles
            WHERE quality_score IS NOT NULL
            ORDER BY quality_score DESC
            LIMIT 5
        """)

        profiles = cur.fetchall()
        if profiles:
            print()
            print("🎯 GENERATION PROFILES")
            print("-" * 80)
            for name, score in profiles:
                print(f"  {name:<30} Quality: {score:.1%}")

        print()
        print("=" * 80)

        # Export to JSON
        dashboard_data = {
            'generated': datetime.now().isoformat(),
            'statistics': {
                'total_tests': total,
                'passed': passed,
                'failed': failed,
                'average_similarity': float(avg) if avg else 0,
                'max_score': float(max_score) if max_score else 0,
                'min_score': float(min_score) if min_score else 0
            },
            'recommendation': 'PRODUCTION_READY' if avg > 0.70 else 'NEEDS_IMPROVEMENT'
        }

        output_path = Path("/opt/tower-anime-production/quality_dashboard.json")
        with open(output_path, 'w') as f:
            json.dump(dashboard_data, f, indent=2)

        print(f"📄 Dashboard data exported to: {output_path}")

        # Create HTML dashboard
        self.create_html_dashboard(dashboard_data)

    def create_html_dashboard(self, data):
        """Create HTML dashboard for web viewing"""
        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Quality Verification Dashboard</title>
    <style>
        body {{ font-family: Arial, sans-serif; background: #1a1a1a; color: #fff; padding: 20px; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        .header {{ text-align: center; padding: 20px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 10px; }}
        .stats {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; margin: 30px 0; }}
        .stat-card {{ background: #2a2a2a; padding: 20px; border-radius: 10px; text-align: center; }}
        .stat-value {{ font-size: 2em; font-weight: bold; color: #667eea; }}
        .stat-label {{ color: #888; margin-top: 10px; }}
        .status {{ padding: 20px; background: #2a2a2a; border-radius: 10px; margin: 20px 0; }}
        .passed {{ color: #4caf50; }}
        .failed {{ color: #f44336; }}
        .recommendation {{ background: #764ba2; padding: 15px; border-radius: 10px; margin-top: 20px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Quality Verification Dashboard</h1>
            <p>Generated: {data['generated']}</p>
        </div>

        <div class="stats">
            <div class="stat-card">
                <div class="stat-value">{data['statistics']['total_tests']}</div>
                <div class="stat-label">Total Tests</div>
            </div>
            <div class="stat-card">
                <div class="stat-value passed">{data['statistics']['passed']}</div>
                <div class="stat-label">Passed</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{data['statistics']['average_similarity']:.1%}</div>
                <div class="stat-label">Average Score</div>
            </div>
        </div>

        <div class="status">
            <h2>System Status</h2>
            <p>Quality Threshold: 70%</p>
            <p>Pass Rate: {data['statistics']['passed'] / data['statistics']['total_tests'] * 100:.0f}%</p>
            <p>Best Score: {data['statistics']['max_score']:.1%}</p>
        </div>

        <div class="recommendation">
            <h2>Recommendation</h2>
            <p>{data['recommendation']}</p>
        </div>
    </div>
</body>
</html>"""

        html_path = Path("/opt/tower-anime-production/frontend/quality_dashboard.html")
        html_path.parent.mkdir(exist_ok=True)
        with open(html_path, 'w') as f:
            f.write(html)

        print(f"🌐 HTML dashboard created: {html_path}")

if __name__ == "__main__":
    dashboard = QualityDashboard()
    dashboard.generate_dashboard()