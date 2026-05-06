"""Tests for the orchestrator's advisory lock (`_orchestrator_lock`)."""
import os
import subprocess
import sys
import textwrap
import time

import pytest

from tests._capture import orchestrator


def test_lock_acquires_when_uncontended(tmp_path):
    """Single-process: the lock acquires immediately and yields True."""
    (tmp_path / ".git").mkdir()
    with orchestrator._orchestrator_lock(tmp_path) as locked:
        assert locked is True


def test_lock_releases_so_second_call_can_acquire(tmp_path):
    """Sequential same-process acquire/release succeeds twice."""
    (tmp_path / ".git").mkdir()
    with orchestrator._orchestrator_lock(tmp_path) as locked1:
        assert locked1 is True
    with orchestrator._orchestrator_lock(tmp_path) as locked2:
        assert locked2 is True


def test_lock_creates_git_dir_if_missing(tmp_path):
    """Hook a missing .git/ — lock should create it (no crash)."""
    # No .git directory yet.
    with orchestrator._orchestrator_lock(tmp_path) as locked:
        assert locked is True
    assert (tmp_path / ".git").is_dir()


def _holder_script(repo: str, hold_seconds: float) -> str:
    """Subprocess script that grabs the lock and holds it for `hold_seconds`."""
    return textwrap.dedent(f"""\
        import sys, time
        sys.path.insert(0, r"{os.getcwd()}")
        from tests._capture import orchestrator
        from pathlib import Path
        with orchestrator._orchestrator_lock(Path(r"{repo}")) as locked:
            print("LOCKED" if locked else "NOLOCK", flush=True)
            time.sleep({hold_seconds})
        """)


@pytest.mark.timeout(orchestrator.LOCK_TIMEOUT_SECONDS + 30)
def test_lock_returns_false_under_contention(tmp_path):
    """Spawn a holder subprocess that grabs and holds the lock for longer
    than the orchestrator's timeout. The main-process call must return
    False instead of waiting forever or crashing."""
    (tmp_path / ".git").mkdir()
    hold_seconds = orchestrator.LOCK_TIMEOUT_SECONDS + 5.0
    proc = subprocess.Popen(
        [sys.executable, "-c", _holder_script(str(tmp_path), hold_seconds)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        # Wait until the holder confirms it has the lock.
        line = proc.stdout.readline().strip()
        assert line == "LOCKED", f"holder did not lock: {line!r}"
        # Now the lock is held; orchestrator's call should give up after
        # LOCK_TIMEOUT_SECONDS and yield False.
        start = time.monotonic()
        with orchestrator._orchestrator_lock(tmp_path) as locked:
            elapsed = time.monotonic() - start
            assert locked is False
            # Should have given up close to LOCK_TIMEOUT_SECONDS, not waited
            # the full hold duration.
            assert elapsed < orchestrator.LOCK_TIMEOUT_SECONDS + 2.5, (
                f"lock waited too long: {elapsed:.2f}s")
    finally:
        try:
            proc.wait(timeout=hold_seconds + 10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def test_lock_acquires_after_holder_releases(tmp_path):
    """After the holder exits and releases, a fresh call must acquire cleanly."""
    (tmp_path / ".git").mkdir()
    proc = subprocess.Popen(
        [sys.executable, "-c", _holder_script(str(tmp_path), 0.5)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        line = proc.stdout.readline().strip()
        assert line == "LOCKED"
        proc.wait(timeout=10)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
    # Holder gone — we should acquire instantly.
    with orchestrator._orchestrator_lock(tmp_path) as locked:
        assert locked is True
