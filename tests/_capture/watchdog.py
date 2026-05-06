"""Watchdog subprocess -- kills a hanging pytest session after the hard deadline.

Invocation:
    python -m tests._capture.watchdog <target_pid> <session_id> <deadline_epoch> <repo_path> <started_at_epoch>

Design notes:
  * Runs as a detached child. If the parent pytest process exits cleanly,
    it polls and exits quickly without doing anything.
  * If the deadline passes and the parent is still alive, it:
      1. Commits a "hang_watchdog_killed" record via git_ops + metadata.
      2. Terminates the parent.
  * Never blocks the main test session -- it's a separate process.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

POLL_INTERVAL = 1.0


def main() -> int:
    if len(sys.argv) != 6:
        print("usage: watchdog <pid> <session_id> <deadline_epoch> <repo_path> <started_at_epoch>",
              file=sys.stderr)
        return 2
    target_pid = int(sys.argv[1])
    session_id = sys.argv[2]
    deadline = float(sys.argv[3])
    repo = Path(sys.argv[4])
    started_at = float(sys.argv[5])

    # Import heavy modules AFTER arg parse, so --help failures are fast.
    from tests._capture import platform_compat, git_ops, metadata, capture

    # Refuse to run against a repo where capture is disabled. The normal spawn
    # path (capture.session_start) already enforces this, but a manual
    # `python -m tests._capture.watchdog ...` invocation would otherwise
    # bypass the config gate and write a hang commit to an instructor repo.
    if not capture._capture_enabled(repo):
        return 0

    # Poll until deadline or parent exits
    while time.time() < deadline:
        if not platform_compat.is_process_alive(target_pid):
            return 0  # parent finished cleanly; our job is done
        time.sleep(POLL_INTERVAL)

    # Deadline passed. Is parent still alive?
    if not platform_compat.is_process_alive(target_pid):
        return 0

    # Record a hang snapshot via the v2 pipeline. NOTE: we deliberately
    # bypass the orchestrator here -- the orchestrator acquires a repo-scoped
    # advisory lock, and the hung parent process may still hold it. Routing
    # the hang path through the orchestrator would deadlock or time out,
    # defeating the watchdog's purpose. See orchestrator spec section 11
    # and the auto-track plan Phase 4 intro.
    try:
        result = metadata.TestResult()
        result.duration_seconds = time.time() - started_at
        head_ref, head_sha = git_ops.current_head_info(repo)
        git_state = git_ops.detect_git_state(repo)
        msg = metadata.format_commit_message(
            session_id=session_id,
            status="hang_watchdog_killed",
            result=result,
            diff_added=0, diff_removed=0, files_changed=[],
            hostname_hash=metadata.hostname_hash(str(repo)),
            current_head_ref=head_ref,
            current_head_sha=head_sha if head_sha else "unborn",
            git_state=git_state,
            trigger="pytest_watchdog",
        )
        existing = [p for p in ["src", "tests", ".ai-traces", ".codex",
                                "AGENTS.md", "AI_POLICY.md"]
                    if (repo / p).exists()]
        git_ops.snapshot_to_auto_track(repo, msg, existing, head_ref, head_sha)
        git_ops.push_auto_track_background(repo, repo / ".test-runs.log")
    except Exception:
        pass  # even if recording fails, we still kill

    # Terminate parent. Give it a small grace period first.
    platform_compat.terminate_process(target_pid, timeout=3.0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
