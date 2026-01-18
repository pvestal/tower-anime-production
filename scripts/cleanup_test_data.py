#!/usr/bin/env python3
"""
Cleanup script for test data
"""
import os
import glob

def cleanup_test_files():
    """Remove test artifacts and temporary files"""

    # Remove performance benchmark files
    for file in glob.glob("performance_*.json"):
        try:
            os.remove(file)
            print(f"Removed {file}")
        except OSError:
            pass

    # Remove test report files
    for file in glob.glob("test_report_*.md"):
        try:
            os.remove(file)
            print(f"Removed {file}")
        except OSError:
            pass

    # Remove app PID files
    for file in glob.glob("app.pid"):
        try:
            os.remove(file)
            print(f"Removed {file}")
        except OSError:
            pass

    print("✅ Test cleanup completed")

if __name__ == "__main__":
    cleanup_test_files()