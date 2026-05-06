"""Metadata gathering for capture commits.

Designed for stable parsing. Do not reorder fields without bumping capture_version.
"""
from __future__ import annotations

import hashlib
import platform
import socket
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from tests._capture import CAPTURE_VERSION


@dataclass
class TestResult:
    total: int = 0
    passed: int = 0
    failed: int = 0
    error: int = 0
    skipped: int = 0
    duration_seconds: float = 0.0
    bundles_passing: List[int] = field(default_factory=list)
    bundles_failing: List[int] = field(default_factory=list)


def hostname_hash(project_path: str) -> str:
    """First 16 hex chars of sha256(hostname + project_path).

    Deterministic per machine per project. Not recoverable to hostname.
    64 bits of distinctness: collision-free at any realistic class scale.
    """
    try:
        host = socket.gethostname()
    except OSError:
        host = "unknown"
    digest = hashlib.sha256(f"{host}|{project_path}".encode("utf-8")).hexdigest()
    return digest[:16]


def _summary_line(
    status: str, result: TestResult, duration: float, trigger: str = "pytest",
) -> str:
    if status == "hang_watchdog_killed":
        return f"test-run: SESSION HUNG -- killed by watchdog at {int(duration)}s"
    if status == "orphaned_prior_run":
        return "test-run: recovered orphaned session from prior run"
    if status == "error":
        return "test-run: capture error -- see .test-runs.log"
    # completed
    if result.total == 0:
        # Trigger-driven snapshots (post-commit hook, sitecustomize atexit,
        # manual) never run a test session. Saying "no tests collected"
        # there reads like a failure; clarify it's a code-state snapshot.
        if not trigger.startswith("pytest"):
            return f"snapshot: code state captured (trigger={trigger}, no test run)"
        return "test-run: no tests collected"
    if result.passed == result.total and result.bundles_passing:
        return (f"test-run: {result.passed}/{result.total} passed -- "
                f"ALL BUNDLES COMPLETE")
    if result.bundles_passing:
        bundles = ",".join(str(b) for b in result.bundles_passing)
        return (f"test-run: {result.passed}/{result.total} passed -- "
                f"Bundles {bundles} complete")
    return f"test-run: {result.passed}/{result.total} passed"


def format_commit_message(
    session_id: str,
    status: str,
    result: TestResult,
    diff_added: int,
    diff_removed: int,
    files_changed: List[str],
    hostname_hash: str,
    current_head_ref: str = "main",
    current_head_sha: str = "unborn",
    git_state: str = "clean",
    trigger: str = "pytest",
    agent_name: str = "none",
    agent_session_id: str = "none",
    artifact_hashes: Optional[Dict[str, Dict[str, str]]] = None,
) -> str:
    """Assemble the stable commit message format."""
    summary = _summary_line(status, result, result.duration_seconds, trigger)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    files_str = ", ".join(files_changed[:10])  # cap; full list is in git diff
    if len(files_changed) > 10:
        files_str += f", (+{len(files_changed) - 10} more)"
    body = [
        "",
        f"session_id: {session_id}",
        f"timestamp: {now}",
        f"status: {status}",
        f"tests_total: {result.total}",
        f"tests_passed: {result.passed}",
        f"tests_failed: {result.failed}",
        f"tests_error: {result.error}",
        f"tests_skipped: {result.skipped}",
        f"duration_seconds: {result.duration_seconds:.2f}",
        f"bundles_passing: {result.bundles_passing}",
        f"bundles_failing: {result.bundles_failing}",
        f"diff_added_lines: {diff_added}",
        f"diff_removed_lines: {diff_removed}",
        f"files_changed: {files_str}",
        f"hostname_hash: {hostname_hash}",
        f"python_version: {sys.version.split()[0]}",
        f"platform: {sys.platform}",
        f"current_head_ref: {current_head_ref}",
        f"current_head_sha: {current_head_sha}",
        f"git_state: {git_state}",
        f"trigger: {trigger}",
        f"agent_name: {agent_name}",
        f"agent_session_id: {agent_session_id}",
    ]
    if artifact_hashes:
        body.append("artifact_hashes:")
        for adapter_name, files in sorted(artifact_hashes.items()):
            body.append(f"  {adapter_name}:")
            # 50-entry cap per adapter (per orchestrator spec §5)
            items = sorted(files.items())
            for path, sha in items[:50]:
                body.append(f"    {path}: {sha}")
            if len(items) > 50:
                body.append(f"    (+{len(items) - 50} more)")
    body.append(f"capture_version: {CAPTURE_VERSION}")
    return summary + "\n" + "\n".join(body) + "\n"
