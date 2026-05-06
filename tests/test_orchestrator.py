"""Tests for the snapshot orchestrator (`tests._capture.orchestrator`)."""
import subprocess
from pathlib import Path

import pytest

from tests._capture import metadata, orchestrator
from tests._capture.agent_adapters.base import AdapterMetadata


@pytest.fixture
def tmp_git_repo(tmp_path):
    """Plain tmp git repo with no capture config — capture should be off."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@e.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, check=True)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / ".gitkeep").write_text("")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)
    return tmp_path


def _read_auto_track_body(repo: Path) -> str:
    return subprocess.run(
        ["git", "log", "-1", "--format=%B", "refs/auto-track/snapshots"],
        cwd=repo, capture_output=True, text=True, check=True,
    ).stdout


def test_take_snapshot_pytest_trigger_creates_one_snapshot(
        tmp_git_repo_with_capture):
    repo = tmp_git_repo_with_capture
    sha = orchestrator.take_snapshot(
        repo, trigger="pytest", pytest_session_id="sess-1",
        test_result=metadata.TestResult(passed=2, total=2),
    )
    assert sha is not None
    body = _read_auto_track_body(repo)
    assert "trigger: pytest" in body
    assert "agent_name: none" in body  # no adapter ingested anything
    assert "session_id: sess-1" in body


def test_take_snapshot_dedup_by_session_id(tmp_git_repo_with_capture):
    repo = tmp_git_repo_with_capture
    s1 = orchestrator.take_snapshot(
        repo, trigger="pytest", pytest_session_id="sess-1")
    s2 = orchestrator.take_snapshot(
        repo, trigger="pytest", pytest_session_id="sess-1")
    assert s1 is not None
    assert s2 is None  # dedup'd


def test_take_snapshot_manual_trigger_skips_dedup(tmp_git_repo_with_capture):
    """Manual trigger always produces a snapshot per spec decision row 6."""
    repo = tmp_git_repo_with_capture
    s1 = orchestrator.take_snapshot(
        repo, trigger="manual", pytest_session_id=None)
    s2 = orchestrator.take_snapshot(
        repo, trigger="manual", pytest_session_id=None)
    assert s1 is not None
    assert s2 is not None  # manual always snapshots
    assert s1 != s2


def test_take_snapshot_returns_none_when_capture_disabled(tmp_git_repo):
    """No project-template-config.json or capture_enabled false → None."""
    sha = orchestrator.take_snapshot(
        tmp_git_repo, trigger="pytest", pytest_session_id="x")
    assert sha is None


def test_take_snapshot_records_adapter_session(tmp_git_repo_with_capture):
    """Codex Stop trigger labels the snapshot with the agent session id."""
    repo = tmp_git_repo_with_capture
    meta = AdapterMetadata(
        adapter_name="codex",
        agent_session_id="abc-123",
        rollout_path=None, extra={},
    )
    sha = orchestrator.take_snapshot(
        repo, trigger="codex_stop", pytest_session_id=None,
        adapter_metadata=meta,
    )
    assert sha is not None
    body = _read_auto_track_body(repo)
    assert "trigger: codex_stop" in body
    assert "agent_name: codex" in body
    assert "agent_session_id: abc-123" in body


def test_take_snapshot_pytest_dedupe_by_tree_sha_when_no_session_match(
        tmp_git_repo_with_capture):
    """A second pytest call with a fresh session_id but identical tree
    is dedupe'd by tree-SHA when no adapter session is present."""
    repo = tmp_git_repo_with_capture
    s1 = orchestrator.take_snapshot(
        repo, trigger="pytest", pytest_session_id="sess-1")
    assert s1 is not None
    s2 = orchestrator.take_snapshot(
        repo, trigger="pytest", pytest_session_id="sess-2")
    assert s2 is None  # tree unchanged, no adapter session


def test_take_snapshot_writes_to_log_on_failure(
        tmp_git_repo_with_capture, monkeypatch):
    """If the snapshot fails internally, an error line is appended to
    .test-runs.log and None is returned."""
    repo = tmp_git_repo_with_capture
    monkeypatch.setattr(
        "tests._capture.git_ops.snapshot_to_auto_track",
        lambda *a, **kw: None,
    )
    sha = orchestrator.take_snapshot(
        repo, trigger="pytest", pytest_session_id="boom-1")
    assert sha is None
    log = (repo / ".test-runs.log").read_text(encoding="utf-8")
    assert "snapshot failed" in log


def test_take_snapshot_manual_reason_appended_to_body(tmp_git_repo_with_capture):
    repo = tmp_git_repo_with_capture
    sha = orchestrator.take_snapshot(
        repo, trigger="manual", pytest_session_id=None,
        manual_reason="instructor checkpoint",
    )
    assert sha is not None
    body = _read_auto_track_body(repo)
    assert "manual_reason: instructor checkpoint" in body


def test_take_snapshot_lock_contention_returns_none_when_held(
        tmp_git_repo_with_capture, monkeypatch):
    """If the lock can't be acquired (simulated), return None cleanly."""
    import contextlib

    @contextlib.contextmanager
    def fake_lock(repo):
        yield False  # signal contention

    monkeypatch.setattr(orchestrator, "_orchestrator_lock", fake_lock)
    sha = orchestrator.take_snapshot(
        tmp_git_repo_with_capture, trigger="pytest",
        pytest_session_id="contended")
    assert sha is None


def test_take_snapshot_swallows_top_level_exception(
        tmp_git_repo_with_capture, monkeypatch):
    """Never raise — even on unexpected internal errors."""
    monkeypatch.setattr(
        "tests._capture.git_ops.is_git_repo",
        lambda repo: (_ for _ in ()).throw(RuntimeError("kaboom")),
    )
    sha = orchestrator.take_snapshot(
        tmp_git_repo_with_capture, trigger="pytest", pytest_session_id="x")
    assert sha is None


# --- Task 2.5.8 end-to-end integration ------------------------------------

def test_three_triggers_each_produce_correctly_labeled_snapshots(
        tmp_git_repo_with_capture):
    """pytest, codex_stop, and manual triggers each produce a snapshot
    whose body fields match the trigger when the tree changes between
    each call."""
    repo = tmp_git_repo_with_capture

    # 1. pytest trigger
    (repo / "src" / "a.py").write_text("a = 1\n")
    s_pytest = orchestrator.take_snapshot(
        repo, trigger="pytest", pytest_session_id="p1",
        test_result=metadata.TestResult(passed=1, total=1),
    )
    assert s_pytest is not None
    body_p = subprocess.run(
        ["git", "log", "-1", "--format=%B", s_pytest],
        cwd=repo, capture_output=True, text=True, check=True).stdout
    assert "trigger: pytest" in body_p
    assert "agent_name: none" in body_p

    # 2. codex_stop trigger with adapter metadata
    (repo / "src" / "b.py").write_text("b = 2\n")
    meta = AdapterMetadata(
        adapter_name="codex", agent_session_id="codex-1",
        rollout_path=None, extra={},
    )
    s_codex = orchestrator.take_snapshot(
        repo, trigger="codex_stop", pytest_session_id=None,
        adapter_metadata=meta,
    )
    assert s_codex is not None
    body_c = subprocess.run(
        ["git", "log", "-1", "--format=%B", s_codex],
        cwd=repo, capture_output=True, text=True, check=True).stdout
    assert "trigger: codex_stop" in body_c
    assert "agent_name: codex" in body_c
    assert "agent_session_id: codex-1" in body_c

    # 3. manual trigger
    s_manual = orchestrator.take_snapshot(
        repo, trigger="manual", pytest_session_id=None,
        manual_reason="hand checkpoint",
    )
    assert s_manual is not None
    body_m = subprocess.run(
        ["git", "log", "-1", "--format=%B", s_manual],
        cwd=repo, capture_output=True, text=True, check=True).stdout
    assert "trigger: manual" in body_m
    assert "manual_reason: hand checkpoint" in body_m

    # All three SHAs are distinct.
    assert len({s_pytest, s_codex, s_manual}) == 3


def test_multi_trigger_collapse_when_tree_unchanged(
        tmp_git_repo_with_capture):
    """Fire pytest then codex_stop in rapid succession against the same
    tree. The codex_stop carries an adapter session and therefore is NOT
    tree-SHA-deduped (the agent attribution is new information). But a
    second pytest call on top of that — with no adapter context and an
    unchanged tree — must dedupe."""
    repo = tmp_git_repo_with_capture
    (repo / "src" / "x.py").write_text("x = 1\n")

    s1 = orchestrator.take_snapshot(
        repo, trigger="pytest", pytest_session_id="p-1")
    assert s1 is not None

    # codex_stop on unchanged tree but new agent session — DOES snapshot.
    meta = AdapterMetadata(
        adapter_name="codex", agent_session_id="cx-1",
        rollout_path=None, extra={},
    )
    s2 = orchestrator.take_snapshot(
        repo, trigger="codex_stop", pytest_session_id=None,
        adapter_metadata=meta,
    )
    assert s2 is not None
    assert s2 != s1

    # Another pytest call on still-unchanged tree, no adapter — DEDUPES.
    s3 = orchestrator.take_snapshot(
        repo, trigger="pytest", pytest_session_id="p-2")
    assert s3 is None


def test_tree_changes_between_triggers_produce_distinct_snapshots(
        tmp_git_repo_with_capture):
    """Sanity: each tree change yields a distinct snapshot SHA."""
    repo = tmp_git_repo_with_capture
    (repo / "src" / "a.py").write_text("a = 1\n")
    s1 = orchestrator.take_snapshot(
        repo, trigger="pytest", pytest_session_id="p1")
    (repo / "src" / "a.py").write_text("a = 2\n")
    s2 = orchestrator.take_snapshot(
        repo, trigger="pytest", pytest_session_id="p2")
    (repo / "src" / "a.py").write_text("a = 3\n")
    s3 = orchestrator.take_snapshot(
        repo, trigger="pytest", pytest_session_id="p3")
    assert s1 is not None and s2 is not None and s3 is not None
    assert len({s1, s2, s3}) == 3
