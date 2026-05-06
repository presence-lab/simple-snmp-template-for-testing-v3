"""Tests for the friendly local audit module (`tests._capture.audit`)."""
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent


def _run_audit(repo, *args):
    """Invoke `python -m tests._capture.audit` with PYTHONPATH set to REPO_ROOT.

    The audit module lives under tests/_capture/, so the cwd of the subprocess
    (a tmp git repo) cannot resolve the import. Following the same pattern as
    test_orchestrator_cli.py.
    """
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}
    return subprocess.run(
        [sys.executable, "-m", "tests._capture.audit", *args],
        cwd=str(repo), env=env, capture_output=True, text=True, timeout=30,
    )


@pytest.fixture
def tmp_git_repo(tmp_path):
    """Plain tmp git repo with no auto-track ref -- audit prints empty message."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@e.com"],
                   cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "T"],
                   cwd=tmp_path, check=True)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / ".gitkeep").write_text("")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"],
                   cwd=tmp_path, check=True)
    return tmp_path


@pytest.fixture
def tmp_git_repo_with_one_snapshot(tmp_git_repo_with_capture):
    """Snapshot a single pytest-style session into refs/auto-track/snapshots."""
    from tests._capture import capture
    repo = tmp_git_repo_with_capture
    ctx = capture.session_start(repo)
    ctx.record_test(outcome="passed", bundle=1, points=10)
    capture.session_finish(repo, ctx, status="completed")
    return repo


def test_audit_empty_repo_prints_friendly_message(tmp_git_repo):
    result = _run_audit(tmp_git_repo)
    assert result.returncode == 0
    assert result.stdout == (
        "No snapshots recorded yet. "
        "Run `python run_tests.py` to create the first one.\n"
    )


def test_audit_single_snapshot_columns(tmp_git_repo_with_one_snapshot):
    repo = tmp_git_repo_with_one_snapshot
    result = _run_audit(repo)
    assert result.returncode == 0, (
        f"stdout={result.stdout!r} stderr={result.stderr!r}")
    lines = result.stdout.strip().splitlines()
    # The first-parent walk reaches the original `init` commit (which has no
    # v3 metadata) because the very first snapshot's only parent is HEAD/init.
    # That row gets the [v1 capture] annotation per spec section 5. The newest-first
    # ordering puts the v3 snapshot row first.
    assert len(lines) >= 1
    line = lines[0]
    # Columns: short_sha, iso_timestamp, head_ref, head_sha7, git_state, passed/total, subject
    parts = line.split()
    # short_sha is 7 chars
    assert len(parts[0]) == 7
    # iso_timestamp contains 'T' and 'Z'
    assert "T" in parts[1] and parts[1].endswith("Z"), (
        f"timestamp not in UTC-Z form: {parts[1]!r}")
    # head_ref
    assert parts[2] in ("main", "master")
    # head_sha7 is 7 hex chars
    assert len(parts[3]) == 7 and all(c in "0123456789abcdef" for c in parts[3])
    # git_state
    assert parts[4] == "clean"
    # passed/total
    assert "/" in parts[5]
    # subject (everything after) starts with "test-run:"
    assert "test-run:" in line


def _make_n_snapshots(repo: Path, n: int) -> None:
    """Make n snapshots cheaply via the inner-session fast path.

    Bypasses the watchdog spawn (60 detached processes would balloon test time)
    AND mutates the working tree between snapshots so tree-SHA dedupe doesn't
    collapse them.
    """
    from tests._capture import capture
    for i in range(n):
        (repo / "src" / f"f{i}.py").write_text(f"# {i}\n")
        ctx = capture.session_start(
            repo, session_id=f"sess{i:04d}", started_at=time.time(),
        )
        capture.session_finish(repo, ctx, status="completed")


@pytest.mark.timeout(600)
def test_audit_default_cap_is_50(tmp_git_repo_with_capture):
    repo = tmp_git_repo_with_capture
    _make_n_snapshots(repo, 60)
    result = _run_audit(repo)
    assert result.returncode == 0, (
        f"stdout={result.stdout!r} stderr={result.stderr!r}")
    assert len(result.stdout.strip().splitlines()) == 50


@pytest.mark.timeout(600)
def test_audit_all_flag_removes_cap(tmp_git_repo_with_capture):
    repo = tmp_git_repo_with_capture
    _make_n_snapshots(repo, 60)
    result = _run_audit(repo, "--all")
    assert result.returncode == 0, (
        f"stdout={result.stdout!r} stderr={result.stderr!r}")
    # 60 snapshots plus the original `init` commit reachable via first-parent
    # from the very first snapshot. The init line is annotated [v1 capture].
    lines = result.stdout.strip().splitlines()
    assert len(lines) == 61
    assert sum(1 for ln in lines if "[v1 capture]" in ln) == 1


def test_audit_sanitizes_control_characters_in_subject(capsys):
    """A determined student can write arbitrary commit bodies and force-push
    refs/auto-track/snapshots. The audit must not let ANSI escapes /
    cursor-control sequences from a student-crafted body reach the
    instructor's terminal verbatim. _safe() replaces C0/C1 controls with '?'.
    """
    from tests._capture import audit
    # Subject contains: ESC[2J (clear screen), ESC[H (cursor home), ESC[31m (red).
    nasty_subject = "test-run: \x1b[2J\x1b[H\x1b[31mFAKE OK\x1b[0m"
    audit.print_v1_line("0123456789abcdef", "2026-01-01T00:00:00Z", nasty_subject)
    out = capsys.readouterr().out
    # ESC bytes must not survive into the rendered output
    assert "\x1b" not in out, "ESC bytes leaked into audit output"
    # The placeholder for stripped controls should appear in lieu of them
    assert "?" in out
    # Non-control characters of the subject pass through
    assert "test-run:" in out


def test_audit_annotates_v1_in_migrated_history(capsys):
    """Migrated repo: first v3 snapshot has no first parent, only second-parent
    pointing at a v1 capture commit. The --first-parent walk on the snapshot
    will not descend into the v1 commit (because second parents are skipped),
    so this test specifically asserts the v1 annotation works when v1 commits
    DO appear (via a future flag or via direct invocation of print_v1_line).
    """
    from tests._capture import audit
    audit.print_v1_line("abcdef1234567890", "2026-01-01T00:00:00Z",
                        "test-run: 0/0 passed")
    captured = capsys.readouterr()
    assert "[v1 capture]" in captured.out
    # Sanity: short_sha rendered, subject preserved.
    assert "abcdef1" in captured.out
    assert "test-run: 0/0 passed" in captured.out


def test_audit_output_column_order_is_stable(tmp_git_repo_with_one_snapshot):
    """Pin column order so instructor scripts can grep/awk against it."""
    result = _run_audit(tmp_git_repo_with_one_snapshot)
    assert result.returncode == 0, (
        f"stdout={result.stdout!r} stderr={result.stderr!r}")
    # Newest-first ordering: the v3 snapshot row is first; the migrated `init`
    # commit reachable via --first-parent appears below it with [v1 capture].
    line = result.stdout.strip().splitlines()[0]
    parts = line.split(None, 6)
    # Exactly 7 columns
    assert len(parts) == 7
    short_sha, iso_ts, head_ref, head_sha7, git_state, passed_total, subject = parts
    # Order check
    assert len(short_sha) == 7
    assert "T" in iso_ts and iso_ts.endswith("Z")
    assert head_ref in ("main", "master")
    assert len(head_sha7) == 7
    assert git_state == "clean"
    assert "/" in passed_total
    assert subject.startswith("test-run:")


def test_audit_local_only_does_not_fetch(tmp_git_repo_with_one_snapshot):
    """Audit must succeed even with no remote configured."""
    repo = tmp_git_repo_with_one_snapshot
    # Repo has no origin remote -- audit should still print the local snapshot.
    # It must not call `git fetch`; if it did, git would emit a non-fatal
    # warning to stderr but shouldn't fail. We assert the stdout output is
    # non-empty and stderr is clean (no `fatal:` line).
    result = _run_audit(repo)
    assert result.returncode == 0
    assert result.stdout.strip()  # non-empty
    assert "fatal:" not in result.stderr.lower()


def test_audit_handles_dangling_second_parent(tmp_git_repo_with_capture):
    """After a student rewrite that removes the SHA from main, the SHA is
    still reachable from refs/auto-track/snapshots so audit must succeed."""
    repo = tmp_git_repo_with_capture
    from tests._capture import capture
    (repo / "src" / "x.py").write_text("a = 1\n")
    ctx = capture.session_start(repo)
    ctx.record_test(outcome="passed", bundle=1, points=10)
    capture.session_finish(repo, ctx, status="completed")
    # Stage another change so the amend has something to write, then amend
    # HEAD to change its SHA. The pre-amend SHA was the snapshot's
    # second-parent; after amend it is no longer reachable from main but
    # remains reachable from refs/auto-track/snapshots.
    (repo / "src" / "x.py").write_text("a = 2\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "--amend", "-q", "-m", "amended"],
                   cwd=repo, check=True)
    # Audit must still work -- no traceback.
    result = _run_audit(repo)
    assert result.returncode == 0, (
        f"stdout={result.stdout!r} stderr={result.stderr!r}")
    assert result.stdout.strip()
    assert "Traceback" not in result.stderr
