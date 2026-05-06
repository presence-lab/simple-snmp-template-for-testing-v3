"""Tests for run_tests.py's venv-presence check."""
import importlib.util
import os
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _import_run_tests():
    """Import run_tests.py as a module so we can call its functions directly.

    Use a unique module name each call so we get a fresh module object;
    this insulates these tests from each other's monkeypatches.
    """
    spec = importlib.util.spec_from_file_location(
        f"run_tests_under_test_{id(object())}",
        PROJECT_ROOT / "run_tests.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_assert_in_venv_passes_when_in_local_venv(monkeypatch):
    """Pointing sys.prefix at <project>/venv must satisfy the strict check."""
    monkeypatch.delenv("CAPTURE_FORCE_NO_VENV", raising=False)
    monkeypatch.setattr(sys, "prefix", str(PROJECT_ROOT / "venv"))
    monkeypatch.setattr(sys, "base_prefix", "/usr")

    mod = _import_run_tests()
    mod.assert_in_venv()  # must not raise


def test_assert_in_venv_passes_when_in_local_dot_venv(monkeypatch):
    """The .venv/ alternative is also accepted."""
    monkeypatch.delenv("CAPTURE_FORCE_NO_VENV", raising=False)
    monkeypatch.setattr(sys, "prefix", str(PROJECT_ROOT / ".venv"))
    monkeypatch.setattr(sys, "base_prefix", "/usr")

    mod = _import_run_tests()
    mod.assert_in_venv()  # must not raise


def test_assert_in_venv_refuses_a_venv_outside_project(monkeypatch, capsys):
    """A venv elsewhere on the filesystem must be rejected even though
    sys.prefix != sys.base_prefix."""
    monkeypatch.delenv("CAPTURE_FORCE_NO_VENV", raising=False)
    monkeypatch.setattr(sys, "prefix", "/some/other/venv")
    monkeypatch.setattr(sys, "base_prefix", "/usr")

    mod = _import_run_tests()
    with pytest.raises(SystemExit) as excinfo:
        mod.assert_in_venv()
    assert excinfo.value.code == 2
    err = capsys.readouterr().err
    assert "local venv" in err.lower()


def test_assert_in_venv_refuses_a_non_canonical_venv_dir_in_project(monkeypatch):
    """Even a venv inside the project counts only if its directory name is
    'venv' or '.venv'. Anything else (e.g., 'env') is rejected."""
    monkeypatch.delenv("CAPTURE_FORCE_NO_VENV", raising=False)
    monkeypatch.setattr(sys, "prefix", str(PROJECT_ROOT / "env"))
    monkeypatch.setattr(sys, "base_prefix", "/usr")

    mod = _import_run_tests()
    with pytest.raises(SystemExit) as excinfo:
        mod.assert_in_venv()
    assert excinfo.value.code == 2


def test_assert_in_venv_exits_when_using_system_python(monkeypatch, capsys):
    """sys.prefix == sys.base_prefix means no venv at all."""
    monkeypatch.delenv("CAPTURE_FORCE_NO_VENV", raising=False)
    monkeypatch.setattr(sys, "prefix", "/usr")
    monkeypatch.setattr(sys, "base_prefix", "/usr")

    mod = _import_run_tests()
    with pytest.raises(SystemExit) as excinfo:
        mod.assert_in_venv()
    assert excinfo.value.code == 2
    err = capsys.readouterr().err
    assert "pip install -r requirements.txt" in err


def test_assert_in_venv_force_no_venv_env_overrides_real_state(monkeypatch):
    """The test-only override must trigger the refusal even when sys.prefix
    points at the project's local venv."""
    monkeypatch.setenv("CAPTURE_FORCE_NO_VENV", "1")
    monkeypatch.setattr(sys, "prefix", str(PROJECT_ROOT / "venv"))
    monkeypatch.setattr(sys, "base_prefix", "/usr")

    mod = _import_run_tests()
    with pytest.raises(SystemExit) as excinfo:
        mod.assert_in_venv()
    assert excinfo.value.code == 2


def test_main_calls_assert_in_venv_first(monkeypatch):
    """When CAPTURE_FORCE_NO_VENV is set, main() must exit before doing
    any of its own work (the assert is the first line of main)."""
    monkeypatch.setenv("CAPTURE_FORCE_NO_VENV", "1")

    mod = _import_run_tests()
    with pytest.raises(SystemExit) as excinfo:
        mod.main()
    assert excinfo.value.code == 2
