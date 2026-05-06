"""Tests for tools/preflight.py.

The pre-flight gate decides whether `python run_tests.py` is allowed to
proceed. The function under test is :func:`tools.preflight.check_environment`,
which returns a list of failure messages — empty when the environment is
ready.

Most of the checks shell out to git, so we stand up a real tmp git repo for
the relevant cases.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tools import preflight


@pytest.fixture
def tmp_repo(tmp_path, monkeypatch):
    # Isolate from the developer's global git config -- otherwise their
    # credential.helper (set globally on dev machines) bleeds into the
    # "missing helper" tests. Apple's git ships extra config layers, so
    # belt-and-suspenders: redirect HOME and disable system config too.
    fake_home = tmp_path / "_home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(fake_home))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "_no_global"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "t@e.com"], cwd=tmp_path, check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "T"], cwd=tmp_path, check=True,
    )
    return tmp_path


@pytest.fixture
def student_repo(tmp_repo):
    """tmp_repo with capture_enabled=true so git checks engage."""
    (tmp_repo / "project-template-config.json").write_text(
        '{"capture_enabled": true}'
    )
    return tmp_repo


def _force_venv(monkeypatch):
    """Make _in_virtualenv() return True regardless of how pytest was invoked."""
    monkeypatch.setenv("VIRTUAL_ENV", "/fake/venv")


def test_clean_environment_passes(student_repo, monkeypatch):
    _force_venv(monkeypatch)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://example.com/x.git"],
        cwd=student_repo, check=True,
    )
    subprocess.run(
        ["git", "config", "credential.helper", "store"],
        cwd=student_repo, check=True,
    )
    assert preflight.check_environment(student_repo) == []


def test_missing_venv_reports_failure(student_repo, monkeypatch):
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    monkeypatch.delenv("CONDA_PREFIX", raising=False)
    # Force the sys.prefix == sys.base_prefix branch (simulate system Python).
    monkeypatch.setattr(sys, "base_prefix", sys.prefix, raising=False)
    failures = preflight.check_environment(student_repo)
    assert any("virtual environment" in f for f in failures)


def test_missing_remote_reports_failure(student_repo, monkeypatch):
    _force_venv(monkeypatch)
    subprocess.run(
        ["git", "config", "credential.helper", "store"],
        cwd=student_repo, check=True,
    )
    failures = preflight.check_environment(student_repo)
    assert any("origin" in f for f in failures)


def test_missing_credential_helper_reports_failure(student_repo, monkeypatch):
    _force_venv(monkeypatch)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://example.com/x.git"],
        cwd=student_repo, check=True,
    )
    failures = preflight.check_environment(student_repo)
    assert any("credential helper" in f for f in failures)


def test_instructor_mode_skips_git_checks(tmp_repo, monkeypatch):
    """capture_enabled=false (instructor template) — no remote/helper required."""
    _force_venv(monkeypatch)
    (tmp_repo / "project-template-config.json").write_text(
        '{"capture_enabled": false}'
    )
    # No remote, no helper -- should still be clean.
    assert preflight.check_environment(tmp_repo) == []


def test_no_config_skips_git_checks(tmp_repo, monkeypatch):
    """Missing project-template-config.json -- behave as instructor mode."""
    _force_venv(monkeypatch)
    assert preflight.check_environment(tmp_repo) == []


def test_non_git_directory_skips_git_checks(tmp_path, monkeypatch):
    _force_venv(monkeypatch)
    # No .git directory at all.
    (tmp_path / "project-template-config.json").write_text(
        '{"capture_enabled": true}'
    )
    assert preflight.check_environment(tmp_path) == []
