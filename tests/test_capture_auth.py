"""Tests for the auth-hint diagnoser.

The diagnoser is intentionally narrow: it only looks at .test-runs.log and
returns a hint string. The tricky property is windowing — once a successful
push has been observed, prior auth failures must stop appearing in the hint
or students see "Git push could not complete" forever after fixing their
credentials.
"""
from __future__ import annotations

from pathlib import Path

from tests._capture import auth


def _write(log_path: Path, text: str) -> Path:
    log_path.write_text(text, encoding="utf-8")
    return log_path


def test_returns_empty_when_log_missing(tmp_path):
    assert auth.diagnose_push_log(tmp_path / "missing.log") == ""


def test_returns_empty_on_clean_log(tmp_path):
    log = _write(tmp_path / "log", "[2026-01-01T00:00:00] session_start\n")
    assert auth.diagnose_push_log(log) == ""


def test_detects_authentication_failure(tmp_path):
    log = _write(
        tmp_path / "log",
        "remote: Authentication failed for 'https://github.com/x/y.git'\n",
    )
    out = auth.diagnose_push_log(log)
    assert auth.AUTH_HINT_HEADER in out
    assert "Personal Access Token" in out


def test_detects_could_not_read_username(tmp_path):
    log = _write(tmp_path / "log", "fatal: could not read Username for 'github.com'\n")
    out = auth.diagnose_push_log(log)
    assert auth.AUTH_HINT_HEADER in out
    assert "credentials to push" in out


def test_stale_auth_failure_suppressed_after_successful_push(tmp_path):
    """The headline regression: after a successful push, the previous
    auth-failure window should be ignored.
    """
    log = _write(
        tmp_path / "log",
        # Old failed push
        "remote: Authentication failed for 'https://github.com/x/y.git'\n"
        "fatal: Authentication failed\n"
        # Student ran setup_credentials.py and pushed successfully
        "To https://github.com/x/y.git\n"
        "   abcdef..123456  HEAD -> main\n"
        # A later harmless capture-layer log line
        "[2026-01-02T00:00:00] session_start\n",
    )
    assert auth.diagnose_push_log(log) == ""


def test_everything_up_to_date_also_clears_old_failure(tmp_path):
    log = _write(
        tmp_path / "log",
        "fatal: Authentication failed\n"
        "Everything up-to-date\n",
    )
    assert auth.diagnose_push_log(log) == ""


def test_failure_after_success_is_still_reported(tmp_path):
    """A new failure that happens AFTER a previous success must still surface."""
    log = _write(
        tmp_path / "log",
        "To https://github.com/x/y.git\n"
        "   abc..def  HEAD -> main\n"
        # Token expired later
        "remote: Authentication failed\n",
    )
    out = auth.diagnose_push_log(log)
    assert auth.AUTH_HINT_HEADER in out
    assert "rejected" in out or "Personal Access Token" in out


def test_window_uses_last_success_not_first(tmp_path):
    """Multiple successful pushes — only output after the most recent matters."""
    log = _write(
        tmp_path / "log",
        # First success
        "To https://github.com/x/y.git\n"
        "   aaa..bbb  HEAD -> main\n"
        # Then a failure
        "fatal: Authentication failed\n"
        # Then another success that should clear the failure above
        "To https://github.com/x/y.git\n"
        "   bbb..ccc  HEAD -> main\n",
    )
    assert auth.diagnose_push_log(log) == ""
