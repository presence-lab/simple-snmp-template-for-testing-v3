"""Tests for the manual CLI entrypoint (`python -m tests._capture`)."""
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


def _run_cli(repo: Path, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}
    return subprocess.run(
        [sys.executable, "-m", "tests._capture", *args],
        cwd=str(repo), env=env, capture_output=True, text=True,
        timeout=30,
    )


def test_cli_snapshot_creates_auto_track_commit(tmp_git_repo_with_capture):
    repo = tmp_git_repo_with_capture
    result = _run_cli(repo, "snapshot")
    assert result.returncode == 0, (
        f"stdout={result.stdout!r} stderr={result.stderr!r}")
    body = subprocess.run(
        ["git", "log", "-1", "--format=%B", "refs/auto-track/snapshots"],
        cwd=repo, capture_output=True, text=True, check=True,
    ).stdout
    assert "trigger: manual" in body


def test_cli_snapshot_with_reason_records_in_body(tmp_git_repo_with_capture):
    repo = tmp_git_repo_with_capture
    result = _run_cli(repo, "snapshot", "--reason", "instructor checkpoint")
    assert result.returncode == 0, (
        f"stdout={result.stdout!r} stderr={result.stderr!r}")
    body = subprocess.run(
        ["git", "log", "-1", "--format=%B", "refs/auto-track/snapshots"],
        cwd=repo, capture_output=True, text=True, check=True,
    ).stdout
    assert "manual_reason: instructor checkpoint" in body


def test_cli_snapshot_calls_orchestrator_with_manual_trigger(
        tmp_git_repo_with_capture, monkeypatch):
    """Direct unit test against the CLI dispatch — bypass subprocess."""
    repo = tmp_git_repo_with_capture
    captured = {}

    from tests._capture import __main__ as cli_main

    def fake_take_snapshot(repo_arg, **kwargs):
        captured["repo"] = repo_arg
        captured.update(kwargs)
        return "deadbeef"

    monkeypatch.setattr(
        "tests._capture.orchestrator.take_snapshot", fake_take_snapshot)
    rc = cli_main.main(["snapshot", "--reason", "x"], cwd=repo)
    assert rc == 0
    assert captured["trigger"] == "manual"
    assert captured["pytest_session_id"] is None
    assert captured["manual_reason"] == "x"
    assert Path(captured["repo"]) == repo


def test_cli_snapshot_returns_exit_code_2_when_orchestrator_returns_none(
        tmp_git_repo_with_capture, monkeypatch):
    """No snapshot → non-zero exit so callers can detect dedupe/disabled."""
    repo = tmp_git_repo_with_capture
    monkeypatch.setattr(
        "tests._capture.orchestrator.take_snapshot",
        lambda *a, **kw: None,
    )
    from tests._capture import __main__ as cli_main
    rc = cli_main.main(["snapshot"], cwd=repo)
    assert rc == 2


def test_cli_unknown_subcommand_returns_nonzero(tmp_git_repo_with_capture):
    repo = tmp_git_repo_with_capture
    result = _run_cli(repo, "nope")
    assert result.returncode != 0
