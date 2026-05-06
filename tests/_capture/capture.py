"""Orchestration for the capture layer.

Called from tests/conftest.py hooks. This module is the public API:

    ctx = capture.session_start(repo_path)
    # ... tests run, hooks record outcomes via ctx.record_test ...
    capture.session_finish(repo_path, ctx, status="completed")

If session_start returns None, capture is skipped (e.g., merge in progress).
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from tests._capture import git_ops, metadata, state, orchestrator


LOG_FILENAME = ".test-runs.log"


@dataclass
class SessionContext:
    session_id: str
    repo: Path
    started_at: float
    hard_deadline: float
    result: metadata.TestResult = field(default_factory=metadata.TestResult)
    _bundle_status: dict = field(default_factory=dict)

    def record_test(self, outcome: str, bundle: int = 1, points: int = 0) -> None:
        """Record one test result into this session's tallies.

        Called from pytest_sessionfinish by iterating reporter.stats.
        outcome is one of: "passed", "failed", "error", "skipped".
        """
        self.result.total += 1
        if outcome == "passed":
            self.result.passed += 1
        elif outcome == "failed":
            self.result.failed += 1
        elif outcome == "error":
            self.result.error += 1
        elif outcome == "skipped":
            self.result.skipped += 1

        # Bundle status only counts pass/fail; skipped tests don't move a
        # bundle either direction, errored tests count as failures for bundle
        # completion.
        if outcome in ("passed", "failed", "error"):
            cur = self._bundle_status.setdefault(bundle, {"pass": 0, "fail": 0})
            if outcome == "passed":
                cur["pass"] += 1
            else:
                cur["fail"] += 1

    def finalize_bundles(self) -> None:
        for b, counts in self._bundle_status.items():
            if counts["fail"] == 0 and counts["pass"] > 0:
                self.result.bundles_passing.append(b)
            else:
                self.result.bundles_failing.append(b)
        self.result.bundles_passing.sort()
        self.result.bundles_failing.sort()


def compute_hard_deadline(per_test_timeout: float, n_tests: int) -> float:
    """Session hard deadline scales with suite size.

    Floor of 120 seconds for very small suites. Beyond that, allow 3× the
    cumulative per-test timeout budget.
    """
    return max(120.0, 3.0 * per_test_timeout * max(n_tests, 1))


def _log(repo: Path, msg: str) -> None:
    try:
        with (repo / LOG_FILENAME).open("a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%dT%H:%M:%S')}] {msg}\n")
    except OSError:
        pass


def _capture_enabled(repo: Path) -> bool:
    """Read project-template-config.json and return whether capture is on.

    Returns False if the config file is missing, unreadable, or explicitly
    disables capture. This gives instructors a clean off-switch for
    template development (where capture_enabled is false) and a clean
    on-switch for student distributions (flipped to true by
    create-assignment.sh).

    Also honors CAPTURE_DISABLED=1 in the environment so that nested pytest
    invocations (e.g., run_tests.py's --collect-only probe) can suppress
    capture for a single subprocess without touching the config file.
    """
    if os.environ.get("CAPTURE_DISABLED") == "1":
        return False
    import json
    config_path = repo / "project-template-config.json"
    if not config_path.exists():
        return False
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(data.get("capture_enabled"))


def session_start(repo: Path, per_test_timeout: float = 30.0,
                  estimated_tests: int = 10,
                  session_id: Optional[str] = None,
                  started_at: Optional[float] = None) -> Optional[SessionContext]:
    """Called by pytest_sessionstart. Returns a context, or None to skip.

    If both session_id and started_at are provided, this is an inner
    (pytest subprocess) session whose outer wrapper already created the
    state marker and spawned the watchdog. We skip marker creation,
    watchdog spawn, and orphan recovery, and return a SessionContext
    that shares the session_id so commit dedupe at session_finish works.
    """
    # Silent skip for internal probes (run_tests.py --collect-only sets this
    # to suppress recursion). Logging would falsely blame the config file.
    if os.environ.get("CAPTURE_DISABLED") == "1":
        return None
    if not _capture_enabled(repo):
        _log(repo, "session_start: capture disabled via project-template-config.json")
        return None
    if not git_ops.is_git_repo(repo):
        _log(repo, "session_start: not a git repo -- capture disabled")
        return None

    # Inner-session fast path: outer wrapper already set up marker + watchdog.
    if session_id is not None and started_at is not None:
        hard_deadline = compute_hard_deadline(per_test_timeout, estimated_tests)
        return SessionContext(
            session_id=session_id, repo=repo, started_at=started_at,
            hard_deadline=hard_deadline,
        )

    # 1. Recover orphaned prior sessions
    orphans = state.detect_orphans(repo)
    for orphan in orphans:
        _commit_orphan(repo, orphan)
    if orphans:
        state.clear_orphans(repo, orphans)

    # 2. Drop a fresh marker for this session
    hard_deadline = compute_hard_deadline(per_test_timeout, estimated_tests)
    sid = state.start_session(repo, hard_deadline)

    started_at = time.time()
    watchdog_deadline = started_at + hard_deadline

    # 3. Spawn a detached watchdog subprocess that will kill this pytest
    #    process if it hangs past the deadline. Best-effort; the capture
    #    layer must keep working even if the spawn fails.
    kwargs = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "cwd": str(repo),
    }
    if os.name == "nt":
        kwargs["creationflags"] = 0x08000000 | 0x00000008  # NO_WINDOW | DETACHED
    else:
        kwargs["start_new_session"] = True

    try:
        subprocess.Popen(
            [sys.executable, "-m", "tests._capture.watchdog",
             str(os.getpid()), sid, str(watchdog_deadline),
             str(repo), str(started_at)],
            **kwargs,
        )
    except OSError as e:
        _log(repo, f"watchdog spawn failed: {e}")

    # Best-effort fetch of remote auto-track tip so subsequent snapshots
    # can pick the right first parent across machines.
    git_ops.fetch_auto_track(repo)

    return SessionContext(
        session_id=sid, repo=repo, started_at=started_at,
        hard_deadline=hard_deadline,
    )


def session_finish(repo: Path, ctx: SessionContext, status: str = "completed") -> None:
    """Called by pytest_sessionfinish. Delegates to orchestrator.take_snapshot."""
    try:
        ctx.finalize_bundles()
        ctx.result.duration_seconds = time.time() - ctx.started_at
        orchestrator.take_snapshot(
            repo,
            trigger="pytest",
            pytest_session_id=ctx.session_id,
            test_result=ctx.result,
            status=status,
            adapter_metadata=None,
        )
    finally:
        state.finish_session(repo, ctx.session_id)


def _commit_orphan(repo: Path, orphan: dict) -> None:
    """Record a snapshot for a session that never called session_finish."""
    try:
        result = metadata.TestResult()
        if "started_at" in orphan:
            result.duration_seconds = min(time.time() - orphan["started_at"], 3600.0)
        orchestrator.take_snapshot(
            repo,
            trigger="pytest",
            pytest_session_id=orphan.get("session_id", "unknown"),
            test_result=result,
            status="orphaned_prior_run",
        )
    except Exception:
        pass  # best-effort


def snapshot_now(repo: Path, trigger_name: str) -> Optional[str]:
    """Trigger-agnostic single-shot snapshot for non-pytest callers.

    Used by sitecustomize.py (interpreter exit) and the git post-commit
    hook. Calls orchestrator.take_snapshot directly so we skip the
    pytest-specific overhead of session_start/session_finish (orphan
    recovery, watchdog spawn, state marker), which would be wasteful
    on every Python invocation in the project venv.

    Returns the snapshot SHA on success, or None when capture is
    disabled, the repo isn't a git repo, the orchestrator lock is
    contended, or any unexpected exception occurs. Never raises:
    capture must not break a student's Python script or git commit.
    """
    try:
        return orchestrator.take_snapshot(
            repo,
            trigger=trigger_name,
            pytest_session_id=None,
            test_result=metadata.TestResult(),
            status="completed",
        )
    except Exception as exc:
        _log(repo, f"snapshot_now({trigger_name}) failed: {exc!r}")
        return None
