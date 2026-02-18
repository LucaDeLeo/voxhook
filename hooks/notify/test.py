#!/usr/bin/env python3
"""
Test script for Voxhook Push Notification System
=================================================

Tests various hook event scenarios to ensure push notifications work correctly.

Usage:
  python test.py --topic=test-notifications
  python test.py --topic=test-notifications --debug
"""

import json
import sys
import argparse
import subprocess
from pathlib import Path

def run_test_case(test_name: str, test_data: dict, topic: str, debug: bool = False) -> bool:
    """Run a single test case for push notifications."""
    print(f"\nTesting: {test_name}")

    json_input = json.dumps(test_data)

    script_path = Path(__file__).parent / "handler.py"
    cmd = ["uv", "run", str(script_path), "--topic", topic]

    if debug:
        cmd.append("--debug")

    try:
        result = subprocess.run(
            cmd,
            input=json_input,
            text=True,
            capture_output=True,
            timeout=30
        )

        if result.returncode == 0:
            print(f"  PASS: {test_name}")
            if debug:
                print(f"  stdout: {result.stdout}")
            return True
        else:
            print(f"  FAIL: {test_name}")
            print(f"  stderr: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        print(f"  TIMEOUT: {test_name}")
        return False
    except Exception as e:
        print(f"  ERROR: {test_name} - {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description='Test Voxhook push notification system')
    parser.add_argument('--topic', default='test-notifications', help='ntfy.sh topic for testing')
    parser.add_argument('--debug', action='store_true', help='Enable debug output')

    args = parser.parse_args()
    topic = args.topic
    debug = args.debug

    print(f"Testing Voxhook Push Notification System")
    print(f"Topic: {topic}")
    print(f"Debug: {debug}")

    test_cases = [
        ("Stop Hook", {
            "hook_event_name": "Stop"
        }),
        ("SubagentStop Hook", {
            "hook_event_name": "SubagentStop",
            "stop_hook_active": False
        }),
        ("Permission Request", {
            "hook_event_name": "Notification",
            "message": "Claude Code is requesting permission to use the Bash tool"
        }),
        ("Idle Timeout", {
            "hook_event_name": "Notification",
            "message": "Claude Code is waiting for your input"
        }),
        ("General Notification", {
            "hook_event_name": "Notification",
            "message": "General system notification"
        }),
        ("Python File Read", {
            "hook_event_name": "PreToolUse",
            "tool_name": "Read",
            "tool_input": {"file_path": "/path/to/script.py"}
        }),
        ("Git Status", {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "git status"}
        }),
        ("Task Complete", {
            "hook_event_name": "PostToolUse",
            "tool_name": "Edit",
            "tool_input": {"file_path": "/path/to/file.js"}
        }),
        ("Unknown Hook", {
            "hook_event_name": "UnknownEvent",
            "tool_name": "UnknownTool"
        }),
    ]

    passed = 0
    total = len(test_cases)

    for test_name, test_data in test_cases:
        if run_test_case(test_name, test_data, topic, debug):
            passed += 1

    print(f"\nTest Results:")
    print(f"  Passed: {passed}/{total}")
    print(f"  Failed: {total - passed}/{total}")

    if passed == total:
        print(f"All tests passed!")
        sys.exit(0)
    else:
        print(f"Some tests failed")
        sys.exit(1)

if __name__ == "__main__":
    main()
