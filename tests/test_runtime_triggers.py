"""Tests for self-install bootstrap helpers."""
import sys
from pathlib import Path
from unittest import mock

from tests._capture import runtime_triggers as rt


def test_active_venv_returns_sys_prefix_when_in_venv():
    with mock.patch.object(sys, "prefix", "/fake/venv"), \
         mock.patch.object(sys, "base_prefix", "/usr"):
        assert rt.active_venv() == Path("/fake/venv")


def test_active_venv_returns_none_when_not_in_venv():
    with mock.patch.object(sys, "prefix", "/usr"), \
         mock.patch.object(sys, "base_prefix", "/usr"):
        assert rt.active_venv() is None


import sys


def test_install_sitecustomize_writes_to_windows_venv(tmp_path):
    fake_venv = tmp_path / "venv"
    site_packages = fake_venv / "Lib" / "site-packages"
    site_packages.mkdir(parents=True)
    payload = "# payload body\nimport os\n"

    rt.install_sitecustomize(fake_venv, payload)

    installed = site_packages / "sitecustomize.py"
    assert installed.exists()
    assert installed.read_text(encoding="utf-8") == payload


def test_install_sitecustomize_writes_to_posix_venv(tmp_path):
    fake_venv = tmp_path / "venv"
    sp = (
        fake_venv / "lib"
        / f"python{sys.version_info.major}.{sys.version_info.minor}"
        / "site-packages"
    )
    sp.mkdir(parents=True)

    rt.install_sitecustomize(fake_venv, "# payload\n")

    assert (sp / "sitecustomize.py").exists()


def test_install_sitecustomize_returns_none_when_no_layout(tmp_path):
    fake_venv = tmp_path / "venv"
    fake_venv.mkdir()
    # No site-packages anywhere.

    assert rt.install_sitecustomize(fake_venv, "# payload\n") is None


def test_install_sitecustomize_is_idempotent_when_unchanged(tmp_path):
    fake_venv = tmp_path / "venv"
    (fake_venv / "Lib" / "site-packages").mkdir(parents=True)
    payload = "# payload\n"

    rt.install_sitecustomize(fake_venv, payload)
    target = fake_venv / "Lib" / "site-packages" / "sitecustomize.py"
    first_mtime = target.stat().st_mtime

    # Sleep briefly so an unintended rewrite would change mtime.
    import time as _t; _t.sleep(0.05)

    rt.install_sitecustomize(fake_venv, payload)
    second_mtime = target.stat().st_mtime

    assert first_mtime == second_mtime


def test_install_sitecustomize_rewrites_when_payload_changes(tmp_path):
    fake_venv = tmp_path / "venv"
    (fake_venv / "Lib" / "site-packages").mkdir(parents=True)

    rt.install_sitecustomize(fake_venv, "# v1\n")
    rt.install_sitecustomize(fake_venv, "# v2\n")

    target = fake_venv / "Lib" / "site-packages" / "sitecustomize.py"
    assert target.read_text(encoding="utf-8") == "# v2\n"


import subprocess


def _init_repo(path):
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "x@y"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "x"], cwd=path, check=True)


def test_configure_git_hooks_sets_hookspath_when_unset(tmp_path):
    _init_repo(tmp_path)

    result = rt.configure_git_hooks(tmp_path)

    assert result is True
    cfg = subprocess.run(
        ["git", "config", "--local", "core.hooksPath"],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert cfg.stdout.strip() == ".githooks"


def test_configure_git_hooks_does_not_overwrite_user_value(tmp_path):
    _init_repo(tmp_path)
    subprocess.run(
        ["git", "config", "--local", "core.hooksPath", ".my-hooks"],
        cwd=tmp_path, check=True,
    )

    result = rt.configure_git_hooks(tmp_path)

    assert result is False
    cfg = subprocess.run(
        ["git", "config", "--local", "core.hooksPath"],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert cfg.stdout.strip() == ".my-hooks"


def test_configure_git_hooks_idempotent_when_already_correct(tmp_path):
    _init_repo(tmp_path)
    subprocess.run(
        ["git", "config", "--local", "core.hooksPath", ".githooks"],
        cwd=tmp_path, check=True,
    )

    result = rt.configure_git_hooks(tmp_path)

    assert result is True


def test_configure_git_hooks_returns_false_outside_repo(tmp_path):
    # tmp_path is not a git repo at all.
    assert rt.configure_git_hooks(tmp_path) is False


import sys
import types


def test_ensure_installed_installs_both_when_in_venv_and_repo(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    fake_venv = tmp_path / "venv"
    (fake_venv / "Lib" / "site-packages").mkdir(parents=True)

    # Stub the payload module so install_sitecustomize has something to copy.
    fake_payload = types.SimpleNamespace(PAYLOAD="# fake payload\n")
    monkeypatch.setitem(sys.modules, "tests._capture.sitecustomize_payload", fake_payload)
    monkeypatch.setattr(rt, "active_venv", lambda: fake_venv)

    rt.ensure_installed(repo=tmp_path)

    assert (fake_venv / "Lib" / "site-packages" / "sitecustomize.py").exists()
    cfg = subprocess.run(
        ["git", "config", "--local", "core.hooksPath"],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert cfg.stdout.strip() == ".githooks"


def test_ensure_installed_configures_hooks_even_without_venv(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    monkeypatch.setattr(rt, "active_venv", lambda: None)

    rt.ensure_installed(repo=tmp_path)

    cfg = subprocess.run(
        ["git", "config", "--local", "core.hooksPath"],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert cfg.stdout.strip() == ".githooks"


def test_ensure_installed_does_not_raise_when_payload_module_missing(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    fake_venv = tmp_path / "venv"
    (fake_venv / "Lib" / "site-packages").mkdir(parents=True)
    monkeypatch.setattr(rt, "active_venv", lambda: fake_venv)
    # Force the payload import to fail by ensuring the real module is absent.
    monkeypatch.setitem(sys.modules, "tests._capture.sitecustomize_payload",
                        None)

    # Must not raise.
    rt.ensure_installed(repo=tmp_path)


def test_ensure_installed_silent_when_repo_is_not_git(tmp_path, monkeypatch):
    # Not a git repo; not a venv.
    monkeypatch.setattr(rt, "active_venv", lambda: None)

    # Must not raise.
    rt.ensure_installed(repo=tmp_path)


def test_is_local_venv_accepts_venv_under_project(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    venv = project / "venv"
    venv.mkdir()
    assert rt.is_local_venv(venv, project) is True


def test_is_local_venv_accepts_dot_venv_under_project(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    venv = project / ".venv"
    venv.mkdir()
    assert rt.is_local_venv(venv, project) is True


def test_is_local_venv_rejects_venv_outside_project(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    assert rt.is_local_venv(elsewhere, project) is False


def test_is_local_venv_rejects_non_canonical_venv_name(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    venv = project / "env"  # not 'venv' or '.venv'
    venv.mkdir()
    assert rt.is_local_venv(venv, project) is False


def test_is_local_venv_resolves_symlinks_and_relative_paths(tmp_path):
    """A relative-path venv that points at <project>/venv must still match."""
    project = tmp_path / "project"
    project.mkdir()
    (project / "venv").mkdir()
    # Pass an unresolved version of the same path (e.g., includes ..).
    relative = project / "src" / ".." / "venv"
    assert rt.is_local_venv(relative, project) is True


def test_ensure_installed_skips_sitecustomize_when_venv_is_not_local(tmp_path, monkeypatch):
    """A venv outside the project root must not get sitecustomize installed."""
    import subprocess
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "x@y"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "x"], cwd=tmp_path, check=True)
    nonlocal_venv = tmp_path / "elsewhere" / "venv"
    (nonlocal_venv / "Lib" / "site-packages").mkdir(parents=True)
    monkeypatch.setattr(rt, "active_venv", lambda: nonlocal_venv)

    rt.ensure_installed(repo=tmp_path)

    # sitecustomize must NOT be in the non-local venv.
    assert not (nonlocal_venv / "Lib" / "site-packages" / "sitecustomize.py").exists()
    # core.hooksPath should still be configured (orthogonal to venv check).
    cfg = subprocess.run(
        ["git", "config", "--local", "core.hooksPath"],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert cfg.stdout.strip() == ".githooks"
