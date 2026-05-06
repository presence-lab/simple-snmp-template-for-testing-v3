#!/usr/bin/env python3
"""
GitHub Classroom Grader - Outputs bundle completion status for partial credit
This script runs the tests and exits with specific codes for GitHub Classroom
"""

import subprocess
import sys
import re
from pathlib import Path

def strip_ansi(text):
    """Remove ANSI color codes from text"""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

def run_tests_once():
    """Run tests once and parse all results"""
    try:
        # Run the test script
        result = subprocess.run(
            [sys.executable, "run_tests.py"],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        # Remove ANSI color codes for easier parsing
        output = strip_ansi(result.stdout)
        
        # Parse bundle results
        bundles = {1: False, 2: False, 3: False}
        bundle_info = {}
        
        # Look for lines like "✓ Bundle 1 (Core Requirements): 31/31 tests passed"
        for line in output.split('\n'):
            match = re.search(r'([✓✗])\s+Bundle\s+(\d+)\s+.*?:\s+(\d+)/(\d+)\s+tests\s+passed', line)
            if match:
                status = match.group(1)
                bundle_num = int(match.group(2))
                passed = int(match.group(3))
                total = int(match.group(4))
                
                bundles[bundle_num] = (status == '✓' and passed == total)
                bundle_info[bundle_num] = f"{passed}/{total} tests passed"
        
        # Also check grade level
        grade = "Not Passing"
        grade_match = re.search(r'Grade Level Achieved:\s+([A-C]|Not Passing)', output)
        if grade_match:
            grade = grade_match.group(1)
        
        # If we found bundles by parsing, trust that
        # Otherwise, fall back to grade mapping
        if not any(bundle_num in bundle_info for bundle_num in [1, 2, 3]):
            if grade == 'A':
                bundles = {1: True, 2: True, 3: True}
                bundle_info = {1: "All tests passed", 2: "All tests passed", 3: "All tests passed"}
            elif grade == 'B':
                bundles = {1: True, 2: True, 3: False}
                bundle_info = {1: "All tests passed", 2: "All tests passed", 3: "Not complete"}
            elif grade == 'C':
                bundles = {1: True, 2: False, 3: False}
                bundle_info = {1: "All tests passed", 2: "Not complete", 3: "Not complete"}
        
        return bundles, bundle_info, grade, result.returncode
        
    except subprocess.TimeoutExpired:
        return {1: False, 2: False, 3: False}, {}, "Timeout", 1
    except Exception as e:
        print(f"Error running tests: {e}")
        return {1: False, 2: False, 3: False}, {}, "Error", 1

def main(bundle_number):
    """Check if a specific bundle is complete"""
    
    # Run tests once and cache results
    bundles, bundle_info, grade, return_code = run_tests_once()
    
    # Print minimal, focused output
    print(f"🧪 Checking Bundle {bundle_number}")
    print("-" * 40)
    
    # Show bundle status
    if bundle_number in bundle_info:
        print(f"📊 Bundle {bundle_number}: {bundle_info[bundle_number]}")
    else:
        print(f"📊 Bundle {bundle_number}: Status unknown")
    
    print(f"📈 Overall Grade: {grade}")
    print("-" * 40)
    
    # Determine pass/fail based on bundle requirements
    if bundle_number == 1:
        if bundles.get(1, False):
            print(f"✅ Bundle 1 PASSED")
            sys.exit(0)
        else:
            print(f"❌ Bundle 1 FAILED")
            sys.exit(1)
            
    elif bundle_number == 2:
        # Bundle 2 requires Bundle 1
        if not bundles.get(1, False):
            print(f"❌ Bundle 2 FAILED - Requires Bundle 1")
            sys.exit(1)
        elif bundles.get(2, False):
            print(f"✅ Bundle 2 PASSED")
            sys.exit(0)
        else:
            print(f"❌ Bundle 2 FAILED")
            sys.exit(1)
            
    elif bundle_number == 3:
        # Bundle 3 requires Bundles 1 and 2
        if not bundles.get(1, False):
            print(f"❌ Bundle 3 FAILED - Requires Bundle 1")
            sys.exit(1)
        elif not bundles.get(2, False):
            print(f"❌ Bundle 3 FAILED - Requires Bundle 2")
            sys.exit(1)
        elif bundles.get(3, False):
            print(f"✅ Bundle 3 PASSED")
            sys.exit(0)
        else:
            print(f"❌ Bundle 3 FAILED")
            sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python github_grader.py <bundle_number>")
        sys.exit(1)
    
    try:
        bundle = int(sys.argv[1])
        if bundle not in [1, 2, 3]:
            print(f"Error: Bundle must be 1, 2, or 3 (got {bundle})")
            sys.exit(1)
        main(bundle)
    except ValueError:
        print("Error: Bundle number must be an integer")
        sys.exit(1)