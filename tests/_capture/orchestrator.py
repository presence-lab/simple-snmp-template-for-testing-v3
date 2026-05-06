"""Single entry point for creating a capture snapshot.

Called by:
    - tests/_capture/capture.py::session_finish (pytest trigger)        [Phase 3]
    - .codex/hooks/stop.py (codex_stop trigger)                         [Plan 2]
    - .claude/hooks/stop.py (claude_code_stop trigger)                  [Plan 3]
    - python -m tests._capture snapshot (manual trigger)                [Task 2.5.7]

See orchestrator spec §4.3 for step ordering. Never raises.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Iterator, List, Optional

from tests._capture import auth, git_ops, metadata
from tests._capture.agent_adapters import installed_adapters
from tests._capture.agent_adapters.base import AdapterMetadata, IngestResult

LOCK_FILENAME = "auto-track.lock"
# 30s absorbs paired triggers from a single pytest exit (pytest plugin's
# session_finish and sitecustomize's atexit both call the orchestrator
# within ~100ms) plus typical git op latency. Push is already detached,
# so the lock holder only does local work — there's no deadlock risk.
LOCK_TIMEOUT_SECONDS = 30.0
LOG_FILENAME = ".test-runs.log"


def take_snapshot(
    repo: Path,
    *,
    trigger: str,
    pytest_session_id: Optional[str],
    test_result: Optional[metadata.TestResult] = None,
    status: str = "completed",
    adapter_metadata: Optional[AdapterMetadata] = None,
    manual_reason: Optional[str] = None,
) -> Optional[str]:
    """See module docstring + spec §4.3. Returns snapshot SHA or None."""
    try:
        if not _capture_enabled(repo):
            return None
        if not git_ops.is_git_repo(repo):
            return None

        with _orchestrator_lock(repo) as locked:
            if not locked:
                _log(repo, f"orchestrator: lock contention, trigger={trigger} -- skipped")
                return None

            # Session-id dedupe (skip for manual trigger per spec row 6).
            # Match the body's `session_id:` line exactly: substring match
            # would false-positive against the `agent_session_id:` line if
            # a pytest session_id (8 hex chars from secrets.token_hex(4))
            # happened to equal an agent session id. Match per-line so the
            # `session_id` key isn't confused with `agent_session_id`.
            if trigger != "manual" and pytest_session_id is not None:
                last = git_ops.run_git(
                    ["log", "-1", "--format=%B", git_ops.AUTO_TRACK_REF],
                    cwd=repo, timeout=5.0,
                )
                if last.returncode == 0:
                    target = f"session_id: {pytest_session_id}"
                    if any(line.strip() == target
                           for line in last.stdout.splitlines()):
                        return None

            # Run each installed adapter's ingest pass.
            since = _last_snapshot_time(repo)
            installed = installed_adapters(repo)
            adapter_results: List[IngestResult] = []
            adapter_paths: List[str] = []
            for adapter in installed:
                try:
                    result = adapter.ingest(repo, since=since)
                    adapter_results.append(result)
                    adapter_paths.extend(adapter.stage_paths())
                    for err in result.errors:
                        _log(repo, f"orchestrator: adapter={adapter.name} err={err}")
                except Exception as e:
                    _log(repo, f"orchestrator: adapter={adapter.name} crashed: {e}")
                    # Per spec §12: one bad adapter cannot block snapshots.
                    continue

            head_ref, head_sha = git_ops.current_head_info(repo)
            git_state = git_ops.detect_git_state(repo)

            base_paths = ["src", "tests", "AGENTS.md", "AI_POLICY.md"]
            all_paths = base_paths + sorted(set(adapter_paths))
            existing = [p for p in all_paths if (repo / p).exists()]

            new_tree = git_ops.preview_tree(repo, existing)

            # Tree-SHA dedupe (skip for manual; skip when adapter session is new).
            if (trigger != "manual" and adapter_metadata is None
                    and new_tree is not None):
                prev_tip = git_ops.read_auto_track_tip(repo)
                if prev_tip:
                    prev_tree_sha = git_ops.run_git(
                        ["rev-parse", f"{prev_tip}^{{tree}}"],
                        cwd=repo, timeout=5.0,
                    ).stdout.strip()
                    if prev_tree_sha == new_tree:
                        return None

            prev_tip = git_ops.read_auto_track_tip(repo)
            prev_tree_sha = (
                git_ops.run_git(
                    ["rev-parse", f"{prev_tip}^{{tree}}"],
                    cwd=repo, timeout=5.0,
                ).stdout.strip()
                if prev_tip else git_ops.EMPTY_TREE_SHA
            )
            stats = git_ops.diff_stats_trees(
                repo, prev_tree_sha, new_tree or git_ops.EMPTY_TREE_SHA)

            agent_name = (
                adapter_metadata.adapter_name if adapter_metadata else "none")
            agent_session_id = (
                adapter_metadata.agent_session_id if adapter_metadata else "none")
            session_id_for_msg = (
                pytest_session_id or f"{trigger}-{int(time.time() * 1000)}")

            # Aggregate per-adapter source_hashes into the
            # {adapter_name: {repo_relative_path: sha256_hex}} shape that
            # format_commit_message renders. Order + 50-entry cap live in
            # metadata.py — the orchestrator only assembles the dict.
            artifact_hashes: dict = {}
            for result in adapter_results:
                if not result.source_hashes:
                    continue
                files = {
                    entry["path"]: entry["sha256"]
                    for entry in result.source_hashes
                    if isinstance(entry, dict)
                    and "path" in entry and "sha256" in entry
                }
                if files:
                    artifact_hashes[result.adapter_name] = files

            msg = metadata.format_commit_message(
                session_id=session_id_for_msg,
                status=status,
                result=test_result or metadata.TestResult(),
                diff_added=stats.added, diff_removed=stats.removed,
                files_changed=stats.files,
                hostname_hash=metadata.hostname_hash(str(repo)),
                current_head_ref=head_ref,
                current_head_sha=head_sha if head_sha else "unborn",
                git_state=git_state,
                trigger=trigger,
                agent_name=agent_name,
                agent_session_id=agent_session_id,
                artifact_hashes=artifact_hashes or None,
            )
            if manual_reason:
                msg = msg.rstrip("\n") + f"\nmanual_reason: {manual_reason}\n"

            # Collect force_paths + unstage_after across adapters. We probe
            # via getattr so adapters predating Task 2.5.10 (no override)
            # cleanly inherit empty defaults.
            force_set: set = set()
            unstage_set: set = set()
            for adapter in installed:
                try:
                    fp = getattr(adapter, "force_paths", lambda: [])()
                    force_set.update(fp or [])
                except Exception:
                    pass
                try:
                    ua = getattr(adapter, "unstage_after", lambda: [])()
                    unstage_set.update(ua or [])
                except Exception:
                    pass

            new_sha = git_ops.snapshot_to_auto_track(
                repo, msg, existing, head_ref, head_sha,
                force_paths=sorted(force_set),
                unstage_after=sorted(unstage_set),
            )
            if new_sha is None:
                _log(repo, f"orchestrator: snapshot failed trigger={trigger}")
                return None

            log_path = repo / LOG_FILENAME
            git_ops.push_auto_track_background(repo, log_path)
            hint = auth.diagnose_push_log(log_path)
            if hint:
                print(hint, file=sys.stderr)
            return new_sha
    except Exception as e:
        _log(repo, f"orchestrator: top-level exception {type(e).__name__}: {e}")
        return None


# --- helpers --------------------------------------------------------------

def _capture_enabled(repo: Path) -> bool:
    """Same gate as capture.py — read project-template-config.json + env.

    Lifted verbatim from capture.py to avoid an import cycle. If the gate
    logic ever changes, change it in both places.
    """
    if os.environ.get("CAPTURE_DISABLED") == "1":
        return False
    config_path = repo / "project-template-config.json"
    if not config_path.exists():
        return False
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(data.get("capture_enabled"))


_TIMESTAMP_RE = re.compile(r"^timestamp:\s*(\S+)\s*$", re.MULTILINE)


def _last_snapshot_time(repo: Path) -> Optional[float]:
    """Read the latest auto-track snapshot's commit body, parse the
    `timestamp:` field, return as Unix epoch float; on any failure
    return None.

    Adapters use this as `since` — a None value means "ingest everything
    not already captured" (matching codex_ingest's existing behavior).
    """
    last = git_ops.run_git(
        ["log", "-1", "--format=%B", git_ops.AUTO_TRACK_REF],
        cwd=repo, timeout=5.0,
    )
    if last.returncode != 0:
        return None
    m = _TIMESTAMP_RE.search(last.stdout)
    if not m:
        return None
    raw = m.group(1)
    try:
        # format_commit_message emits ISO-8601 ending in Z (UTC).
        if raw.endswith("Z"):
            dt = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%SZ")
            from datetime import timezone
            return dt.replace(tzinfo=timezone.utc).timestamp()
        return datetime.fromisoformat(raw).timestamp()
    except (ValueError, OSError):
        return None


def _log(repo: Path, msg: str) -> None:
    try:
        with (repo / LOG_FILENAME).open("a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%dT%H:%M:%S')}] {msg}\n")
    except OSError:
        pass


@contextlib.contextmanager
def _orchestrator_lock(repo: Path) -> Iterator[bool]:
    """Repo-scoped advisory lock at `<repo>/.git/auto-track.lock`.

    Yields True if the lock was acquired within LOCK_TIMEOUT_SECONDS,
    False otherwise. Cross-platform:
      - POSIX: `fcntl.flock(LOCK_EX | LOCK_NB)` with retry loop
      - Windows: `msvcrt.locking(LK_NBLCK, 1)` with retry loop

    Always closes the lock file in finally; releases the lock first
    when it was acquired. Never raises — the orchestrator is gated
    on the boolean yield.
    """
    lock_path = repo / ".git" / LOCK_FILENAME
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        # Can't even create .git/ — yield False so orchestrator falls through.
        yield False
        return

    deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
    try:
        f = open(lock_path, "a+b")
    except OSError:
        yield False
        return

    locked = False
    try:
        if os.name == "nt":
            import msvcrt
            while time.monotonic() < deadline:
                try:
                    f.seek(0)
                    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                    locked = True
                    break
                except OSError:
                    time.sleep(0.1)
            try:
                yield locked
            finally:
                if locked:
                    try:
                        f.seek(0)
                        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
                    except OSError:
                        pass
        else:
            import fcntl
            while time.monotonic() < deadline:
                try:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    locked = True
                    break
                except OSError:
                    time.sleep(0.1)
            try:
                yield locked
            finally:
                if locked:
                    try:
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                    except OSError:
                        pass
    finally:
        try:
            f.close()
        except OSError:
            pass
