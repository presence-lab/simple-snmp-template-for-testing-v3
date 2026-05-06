"""Tests for the trigger-agnostic snapshot_now() entry point."""
import json
import subprocess

from tests._capture import capture


def test_snapshot_now_creates_auto_track_commit(tmp_git_repo_with_capture):
    repo = tmp_git_repo_with_capture
    (repo / "src" / "hello.py").write_text("print('hi')\n")

    sha = capture.snapshot_now(repo, trigger_name="sitecustomize")

    assert sha is not None and len(sha) >= 7
    body = subprocess.run(
        ["git", "log", "refs/auto-track/snapshots", "--format=%B", "-n", "1"],
        cwd=repo, capture_output=True, text=True, check=True,
    )
    assert "trigger: sitecustomize" in body.stdout


def test_snapshot_now_returns_none_when_capture_disabled(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "project-template-config.json").write_text(
        json.dumps({"distribution_mode": "student", "capture_enabled": False})
    )
    assert capture.snapshot_now(tmp_path, trigger_name="sitecustomize") is None


def test_snapshot_now_returns_none_when_not_a_git_repo(tmp_path):
    (tmp_path / "project-template-config.json").write_text(
        json.dumps({"distribution_mode": "student", "capture_enabled": True})
    )
    assert capture.snapshot_now(tmp_path, trigger_name="git_post_commit") is None


def test_snapshot_now_swallows_exceptions(tmp_git_repo_with_capture, monkeypatch):
    """Force orchestrator.take_snapshot to raise; snapshot_now must return None and not propagate."""
    from tests._capture import orchestrator
    def boom(*a, **kw):
        raise RuntimeError("synthetic failure")
    monkeypatch.setattr(orchestrator, "take_snapshot", boom)

    result = capture.snapshot_now(tmp_git_repo_with_capture, trigger_name="sitecustomize")

    assert result is None
    log = (tmp_git_repo_with_capture / ".test-runs.log").read_text(encoding="utf-8")
    assert "snapshot_now" in log
