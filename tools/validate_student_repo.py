#!/usr/bin/env python3
"""Validate that a distributed assignment repo is in a student-safe state."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    config_path = root / "project-template-config.json"

    errors = []
    warnings = []

    if not config_path.exists():
        errors.append("Missing project-template-config.json")
        config = {}
    else:
        config = json.loads(config_path.read_text(encoding="utf-8"))

    if config.get("distribution_mode") != "student":
        errors.append("distribution_mode must be 'student' before distributing the repo")

    if config.get("capture_enabled") not in {False, None}:
        warnings.append("capture_enabled is set to true; confirm that tracking files are intentionally shipped")

    solution_dir = root / "solution"
    if solution_dir.exists():
        solution_files = sorted(path.name for path in solution_dir.glob("*.py") if path.is_file())
        if solution_files:
            errors.append(f"solution/ still contains Python files: {', '.join(solution_files)}")

    removed_marker = root / ".removed-for-students"
    if removed_marker.exists():
        warnings.append(".removed-for-students is still present")

    readme_path = root / "README.md"
    if not readme_path.exists():
        errors.append("README.md is missing")
    else:
        readme_text = readme_path.read_text(encoding="utf-8", errors="replace")
        if "This is a template repository" in readme_text:
            warnings.append("README.md still looks like the template README")

    tests_dir = root / "tests"
    if not tests_dir.exists():
        errors.append("tests/ directory is missing")

    run_tests_path = root / "run_tests.py"
    if not run_tests_path.exists():
        errors.append("run_tests.py is missing")

    # Capture-layer checks (only when capture is enabled).
    if config.get("capture_enabled") is True:
        required_capture_files = [
            "tests/conftest.py",
            "tests/__init__.py",
            "tests/_capture/__init__.py",
            "tests/_capture/__main__.py",
            "tests/_capture/ai_traces.py",
            "tests/_capture/agent_adapters/__init__.py",
            "tests/_capture/agent_adapters/base.py",
            "tests/_capture/agent_adapters/codex.py",
            "tests/_capture/agent_adapters/codex_normalize.py",
            "tests/_capture/agent_adapters/registry.py",
            "tests/_capture/audit.py",
            "tests/_capture/auth.py",
            "tests/_capture/capture.py",
            "tests/_capture/codex_ingest.py",
            "tests/_capture/git_ops.py",
            "tests/_capture/metadata.py",
            "tests/_capture/post_commit_entry.py",
            "tests/_capture/runtime_triggers.py",
            "tests/_capture/sitecustomize_payload.py",
            "tests/_capture/state.py",
            "tests/_capture/watchdog.py",
            "tests/_capture/platform_compat.py",
            ".githooks/post-commit",
            "tools/verify_integrity.py",
            "tools/INTEGRITY_HASHES.txt",
            ".github/workflows/integrity.yml",
            "PROCESS_TRACKING.md",
            ".codex/config.toml",
            ".codex/hooks/_common.py",
            ".codex/hooks/stop.py",
        ]
        for rel in required_capture_files:
            if not (root / rel).exists():
                errors.append(f"Capture is enabled but {rel} is missing")

        # If verify_integrity exists, run it and surface failures.
        integrity_tool = root / "tools" / "verify_integrity.py"
        if integrity_tool.exists():
            result = subprocess.run(
                [sys.executable, str(integrity_tool)],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                errors.append(
                    "Integrity check failed:\n"
                    + "\n".join("    " + ln for ln in result.stdout.splitlines())
                )
    elif config.get("distribution_mode") == "student":
        # Student mode with capture disabled is legal but worth flagging.
        warnings.append(
            "distribution_mode is 'student' but capture_enabled is false -- "
            "no development trace will be recorded"
        )

    if errors:
        print("[FAIL] Student repo validation failed:")
        for error in errors:
            print(f"  - {error}")
    else:
        print("[PASS] Student repo validation passed.")

    if warnings:
        print("\nWarnings:")
        for warning in warnings:
            print(f"  - {warning}")

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
