#!/usr/bin/env python3
"""Pre-flight environment checks for run_tests.py.

Refuse to run tests until the student's environment is set up:

  1. A virtual environment (or conda env) is active.
  2. pytest is importable in the active interpreter.
  3. (Student distributions only) `origin` remote is configured.
  4. (Student distributions only) A git credential helper is configured.

Exits 0 when ready, 1 otherwise. When invoked directly, prints a short
diagnostic. run_tests.py invokes :func:`check_environment` programmatically
and aborts before the first pytest call when any check fails.

The git checks are skipped when capture is disabled (instructor mode), so
the template itself stays usable without a remote.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

# ANSI colors -- match style used by setup_credentials.py and run_tests.py.
if os.environ.get("NO_COLOR"):
    GREEN = RED = YELLOW = BOLD = RESET = ""
else:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


def _in_virtualenv() -> bool:
    """True iff the running interpreter is inside a venv/conda/pipenv env."""
    # PEP 405 venv: sys.prefix differs from sys.base_prefix.
    if getattr(sys, "base_prefix", sys.prefix) != sys.prefix:
        return True
    if os.environ.get("VIRTUAL_ENV"):
        return True
    if os.environ.get("CONDA_PREFIX"):
        return True
    return False


def _pytest_importable() -> bool:
    try:
        import pytest  # noqa: F401
    except ImportError:
        return False
    return True


def _run_git(args: List[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )


def _git_remote_url(repo: Path) -> Optional[str]:
    try:
        result = _run_git(["remote", "get-url", "origin"], cwd=repo)
    except (subprocess.SubprocessError, OSError):
        return None
    if result.returncode != 0:
        return None
    url = result.stdout.strip()
    return url or None


def _git_credential_helper(repo: Path) -> str:
    try:
        result = _run_git(["config", "--get", "credential.helper"], cwd=repo)
    except (subprocess.SubprocessError, OSError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _capture_enabled(repo: Path) -> bool:
    """Mirror tests/_capture/capture._capture_enabled, sans env override.

    The env override exists for nested pytest probes; preflight should
    apply the gate based on the project config alone.
    """
    config_path = repo / "project-template-config.json"
    if not config_path.exists():
        return False
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(data.get("capture_enabled"))


def check_environment(repo: Path) -> List[str]:
    """Return a list of human-readable failure messages.

    Empty list means the environment is ready. Each message is multi-line
    and self-contained — printed verbatim to the student.
    """
    failures: List[str] = []

    if not _in_virtualenv():
        failures.append(
            "No virtual environment is active.\n"
            "    Activate before running tests:\n"
            "        macOS/Linux:  source venv/bin/activate\n"
            "        Windows:      venv\\Scripts\\activate\n"
            "    If you don't have a venv yet, create one first:\n"
            "        python -m venv venv\n"
            "        (activate, then) pip install -r requirements.txt"
        )

    if not _pytest_importable():
        failures.append(
            "pytest is not installed in the active environment.\n"
            "    Install dependencies:  pip install -r requirements.txt"
        )

    # Git checks are only relevant when capture is enabled (student mode).
    # Instructor copies of the template don't push, so don't gate them on
    # credentials being configured.
    if (repo / ".git").exists() and _capture_enabled(repo):
        if _git_remote_url(repo) is None:
            failures.append(
                "No git remote `origin` is configured. Test snapshots can't "
                "be uploaded.\n"
                "    Run:  python tools/setup_credentials.py"
            )
        if not _git_credential_helper(repo):
            failures.append(
                "Git credential helper is not configured. Pushes will fail "
                "or hang.\n"
                "    Run:  python tools/setup_credentials.py"
            )

    return failures


def report(repo: Path, failures: List[str]) -> None:
    """Pretty-print a list of failures, with a footer pointing at the override."""
    print()
    print(f"{RED}{BOLD}Cannot run tests yet -- setup is incomplete.{RESET}")
    print()
    for index, msg in enumerate(failures, 1):
        print(f"{BOLD}{index}.{RESET} {msg}")
        print()
    print(
        f"{YELLOW}Once each item above is fixed, re-run "
        f"`python run_tests.py`.{RESET}"
    )
    print(
        f"{YELLOW}Instructors can bypass with `python run_tests.py "
        f"--skip-preflight` once they understand the consequences.{RESET}"
    )


def main() -> int:
    repo = Path(__file__).resolve().parent.parent
    failures = check_environment(repo)
    if not failures:
        print(f"{GREEN}[OK]{RESET} Environment ready.")
        return 0
    report(repo, failures)
    return 1


if __name__ == "__main__":
    sys.exit(main())
