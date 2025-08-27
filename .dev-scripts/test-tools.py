#!/usr/bin/env python3
"""Simple integration test to verify development tools are working correctly."""

from pathlib import Path
import subprocess
import sys


def run_command(cmd: str, description: str) -> bool:
    """Run a command and return True if successful."""
    print(f"Testing {description}...")
    try:
        result = subprocess.run(cmd.split(), capture_output=True, text=True, cwd=Path(__file__).parent.parent)
        if result.returncode == 0:
            print(f"✅ {description} passed")
            return True
        else:
            print(f"❌ {description} failed:")
            print(f"  stdout: {result.stdout}")
            print(f"  stderr: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ {description} failed with exception: {e}")
        return False


def main():
    """Run all development tool tests."""
    print("🧪 Testing development tools integration...")

    tests = [
        ("ruff check .", "Ruff linting"),
        ("ruff format --check .", "Ruff formatting"),
        ("codespell --help", "Codespell availability"),
        ("pre-commit --version", "Pre-commit availability"),
    ]

    results = []
    for cmd, desc in tests:
        results.append(run_command(cmd, desc))

    passed = sum(results)
    total = len(results)

    print(f"\n📊 Test Results: {passed}/{total} passed")

    if passed == total:
        print("🎉 All development tools are working correctly!")
        return 0
    else:
        print("⚠️ Some tools need attention")
        return 1


if __name__ == "__main__":
    sys.exit(main())
