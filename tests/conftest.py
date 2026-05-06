"""
Pytest session hooks for development trace capture.

DO NOT MODIFY. This file's contents are hashed in tools/INTEGRITY_HASHES.txt
and verified by the CI integrity workflow.

If capture is misbehaving, contact your instructor rather than editing this file.
"""
import json
import subprocess
from pathlib import Path

import pytest

from tests._capture import capture

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SESSION_CTX = None
_BUNDLE_BY_NODEID: dict = {}

# Pytest exit codes (see pytest.ExitCode). Translate these into a commit
# status string so a session that never collected any tests is clearly
# distinguishable from a successful zero-test "completed" run.
_EXIT_STATUS = {
    0: "completed",
    1: "tests_failed",
    2: "interrupted",
    3: "internal_error",
    4: "usage_error",
    5: "no_tests_collected",
}


@pytest.fixture
def tmp_git_repo_with_capture(tmp_path):
    """Tmp git repo with capture_enabled=true config plus src/ and tests/.

    Used by orchestrator + integration tests to exercise the snapshot
    pipeline end-to-end. Mirrors the layout of a real student repo enough
    that `_capture_enabled` returns True and `snapshot_to_auto_track`
    finds the allowlisted directories.
    """
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"],
                   cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"],
                   cwd=tmp_path, check=True)
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / ".gitkeep").write_text("")
    (tmp_path / "tests" / ".gitkeep").write_text("")
    (tmp_path / "project-template-config.json").write_text(
        json.dumps({"distribution_mode": "student", "capture_enabled": True})
    )
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"],
                   cwd=tmp_path, check=True)
    return tmp_path


def pytest_sessionstart(session):
    """Fire once at the start of every pytest session.

    If an outer wrapper (run_tests.py) already started a capture session
    and exported its id + start time via env vars, reuse them so
    session_finish dedupe can collapse outer and inner commits.
    """
    import os
    # Block sitecustomize-triggered captures from any subprocess we spawn
    # during this pytest run. The watchdog spawned in capture.session_start()
    # inherits this env var and its sitecustomize import will see the gate
    # and skip atexit registration. Set BEFORE session_start() so the
    # watchdog subprocess inherits it. Do not pop at session end — pytest
    # teardown may also spawn subprocesses we don't want firing capture.
    os.environ["_CAPTURE_SUBPROCESS"] = "1"

    # Self-install editor-agnostic capture triggers (sitecustomize.py into
    # the venv + core.hooksPath = .githooks). Idempotent and silent;
    # see tests/_capture/runtime_triggers.py for what it installs and why.
    try:
        from tests._capture import runtime_triggers
        runtime_triggers.ensure_installed(_PROJECT_ROOT)
    except Exception:
        pass

    global _SESSION_CTX
    sid = os.environ.get("CAPTURE_SESSION_ID")
    started_at_raw = os.environ.get("CAPTURE_STARTED_AT")
    try:
        started_at = float(started_at_raw) if started_at_raw else None
    except ValueError:
        started_at = None
    _SESSION_CTX = capture.session_start(
        _PROJECT_ROOT, per_test_timeout=30.0, estimated_tests=10,
        session_id=sid, started_at=started_at,
    )


def pytest_collection_modifyitems(config, items):
    """Index each item's bundle marker by nodeid for later lookup.

    Also re-scales the session hard deadline now that we know the real test
    count. If the watchdog was already spawned with an estimated deadline,
    the real count may be larger or smaller — we leave the watchdog's
    deadline alone (accepting some imprecision) since respawning it would
    race with the existing subprocess.
    """
    _BUNDLE_BY_NODEID.clear()
    for item in items:
        for mark in item.iter_markers(name="bundle"):
            if mark.args:
                _BUNDLE_BY_NODEID[item.nodeid] = mark.args[0]
                break


def pytest_sessionfinish(session, exitstatus):
    """Fire once at the end of every pytest session. Count and commit here."""
    if _SESSION_CTX is None:
        return
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if reporter is not None:
        for outcome in ("passed", "failed", "error", "skipped"):
            for rep in reporter.stats.get(outcome, []):
                nodeid = getattr(rep, "nodeid", "") or ""
                bundle = _BUNDLE_BY_NODEID.get(nodeid, 1)
                _SESSION_CTX.record_test(outcome=outcome, bundle=bundle)
    try:
        code = int(exitstatus)
    except (TypeError, ValueError):
        code = -1
    status = _EXIT_STATUS.get(code, f"pytest_exit_{code}")
    capture.session_finish(_PROJECT_ROOT, _SESSION_CTX, status=status)
