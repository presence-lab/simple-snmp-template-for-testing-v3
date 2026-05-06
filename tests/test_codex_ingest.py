"""Unit tests for codex_ingest — fake $CODEX_HOME, no real Codex binary needed.

The module under test scans ``$CODEX_HOME/sessions/`` recursively for Codex
rollout JSONL files, filters them by cwd match, and copies matches into
``<repo>/.ai-traces/codex/raw/rollouts/``. Dedup is handled by the idempotency check
(destination file exists → skip) rather than an mtime cutoff, because the
realistic workflow writes the rollout BEFORE the pytest session starts.

All fixture rollouts use the actual session-meta shape discovered in Task 1:
``{"type": "session_meta", "payload": {"id": sid, "cwd": cwd, ...}}``.
"""
import json
import os
import time
from pathlib import Path

import pytest

from tests._capture import codex_ingest


@pytest.fixture
def fake_codex_home(tmp_path, monkeypatch):
    """Create a fake $CODEX_HOME with an empty sessions/ tree."""
    home = tmp_path / "codex_home"
    (home / "sessions").mkdir(parents=True)
    monkeypatch.setenv("CODEX_HOME", str(home))
    return home


def _write_rollout(home: Path, sid: str, cwd: str, mtime: float,
                   date_subdir: str = "2026/04/22") -> Path:
    """Write a minimally-valid rollout JSONL file under sessions/YYYY/MM/DD/.

    The first line is a session_meta record with payload.cwd, matching the
    real shape discovered in Task 1. Sets the file's mtime so the filter
    can be exercised.
    """
    sessions_root = home / "sessions"
    subdir = sessions_root / date_subdir
    subdir.mkdir(parents=True, exist_ok=True)
    path = subdir / f"rollout-{sid}.jsonl"
    header = {
        "timestamp": "2026-04-22T13:28:53.120Z",
        "type": "session_meta",
        "payload": {
            "id": sid,
            "timestamp": "2026-04-22T13:28:46.061Z",
            "cwd": cwd,
            "originator": "codex_exec",
            "cli_version": "0.119.0-alpha.28",
        },
    }
    second = {"type": "response_item", "payload": {"role": "user"}}
    path.write_text(
        json.dumps(header) + "\n" + json.dumps(second) + "\n",
        encoding="utf-8",
    )
    os.utime(path, (mtime, mtime))
    return path


def test_ingest_copies_rollouts_whose_cwd_matches_repo(tmp_path, fake_codex_home):
    repo = tmp_path / "repo"
    repo.mkdir()
    session_started_at = time.time() - 60

    matching = _write_rollout(
        fake_codex_home, sid="aaa", cwd=str(repo), mtime=time.time() - 30,
    )
    _write_rollout(
        fake_codex_home, sid="bbb", cwd=str(tmp_path / "elsewhere"),
        mtime=time.time() - 30,
    )

    copied = codex_ingest.ingest_transcripts(repo, session_started_at)

    assert len(copied) == 1
    assert copied[0].name == matching.name
    dest = repo / ".ai-traces" / "codex" / "raw" / "rollouts"
    assert (dest / matching.name).exists()
    assert not (dest / "rollout-bbb.jsonl").exists()


def test_ingest_captures_rollouts_created_before_session_start(tmp_path, fake_codex_home):
    """Regression guard for the smoke-test design flaw: a rollout written
    BEFORE the pytest session started (the common case — student uses Codex,
    then runs pytest) MUST still be captured. The previous mtime-based filter
    silently dropped every such rollout.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    session_started_at = time.time()

    _write_rollout(
        fake_codex_home, sid="earlier", cwd=str(repo),
        mtime=session_started_at - 3600,  # one hour before pytest started
    )

    copied = codex_ingest.ingest_transcripts(repo, session_started_at)

    assert len(copied) == 1, (
        "Rollouts finalized before pytest session start must still be captured "
        "— that's the typical workflow. The cwd match + idempotency are the "
        "canonical selection criteria; an mtime cutoff would defeat the point."
    )


def test_ingest_ignores_rollouts_with_different_cwd(tmp_path, fake_codex_home):
    repo = tmp_path / "repo"
    repo.mkdir()
    other = tmp_path / "other_project"
    other.mkdir()
    session_started_at = time.time() - 60

    _write_rollout(
        fake_codex_home, sid="other", cwd=str(other),
        mtime=time.time() - 30,
    )

    copied = codex_ingest.ingest_transcripts(repo, session_started_at)

    assert copied == []
    assert not (repo / ".ai-traces").exists()


def test_ingest_is_idempotent_when_destination_exists(tmp_path, fake_codex_home):
    repo = tmp_path / "repo"
    repo.mkdir()
    session_started_at = time.time() - 60

    _write_rollout(
        fake_codex_home, sid="dup", cwd=str(repo), mtime=time.time() - 30,
    )

    first = codex_ingest.ingest_transcripts(repo, session_started_at)
    second = codex_ingest.ingest_transcripts(repo, session_started_at)

    assert len(first) == 1
    assert second == []  # second call sees dest already exists, skips


def test_ingest_returns_empty_when_codex_home_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "nonexistent"))
    repo = tmp_path / "repo"
    repo.mkdir()

    assert codex_ingest.ingest_transcripts(repo, time.time()) == []
    assert not (repo / ".ai-traces").exists()


def test_ingest_swallows_errors_on_malformed_jsonl(tmp_path, fake_codex_home):
    """Capture layer MUST never raise — matches capture.py's error contract."""
    # Create a rollout with unreadable content under a date subdir so rglob finds it.
    bad_subdir = fake_codex_home / "sessions" / "2026" / "04" / "22"
    bad_subdir.mkdir(parents=True, exist_ok=True)
    bad = bad_subdir / "rollout-bad.jsonl"
    bad.write_bytes(b"\xff\xfenot-utf8-not-json\n")
    os.utime(bad, (time.time() - 30, time.time() - 30))
    repo = tmp_path / "repo"
    repo.mkdir()

    # Must not raise even though the rollout is garbage; malformed rollouts
    # are silently skipped because their cwd can't be extracted.
    result = codex_ingest.ingest_transcripts(repo, time.time() - 60)
    assert result == []


def test_ingest_matches_cwd_with_mismatched_drive_case(tmp_path, fake_codex_home):
    """Windows drive-letter casing varies by Codex source: ``codex exec`` emits
    ``C:\\...`` but the VS Code extension emits ``c:\\...``. Path normalization
    must treat these as equal, otherwise half of all student rollouts silently
    fail to match.

    On non-Windows platforms this test still runs; ``Path.resolve()`` is a
    no-op for casing there so the assertion reduces to "identical path strings
    match", which is trivially true and does not hurt anything.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    session_started_at = time.time() - 60

    repo_str = str(repo.resolve())
    # Flip the casing of the drive letter if one exists (Windows); otherwise
    # just use the path as-is (POSIX — this branch is effectively a no-op
    # since resolve() already canonicalizes case-sensitive paths).
    if len(repo_str) >= 2 and repo_str[1] == ":":
        drive = repo_str[0]
        flipped = (drive.lower() if drive.isupper() else drive.upper()) + repo_str[1:]
    else:
        flipped = repo_str

    _write_rollout(
        fake_codex_home, sid="case", cwd=flipped, mtime=time.time() - 30,
    )

    copied = codex_ingest.ingest_transcripts(repo, session_started_at)

    assert len(copied) == 1, (
        f"Expected cwd with flipped drive case {flipped!r} to match "
        f"repo {repo_str!r} after normalization; got copied={copied}."
    )
