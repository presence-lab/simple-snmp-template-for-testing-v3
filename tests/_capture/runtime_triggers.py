"""Self-install bootstrap for editor-agnostic capture triggers.

ensure_installed() (added in a later task) is called from
pytest_sessionstart and is responsible for landing sitecustomize.py
inside the active venv and configuring the local repo's
core.hooksPath. Both operations are idempotent and silent — they
must never break a pytest run.

This module's helpers are also reused by stand-alone callers (e.g.,
the post-commit Python entry) that need the same primitives.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Optional


# Recognized project-local venv directory names. `venv` is the
# convention CLAUDE.md and the README prescribe; `.venv` is the
# widely-used alternative (PEP 405). Anything else — global venvs,
# conda envs, virtualenvwrapper directories, a venv inside another
# project — is rejected so capture infrastructure isn't installed
# outside the project boundary.
ACCEPTED_VENV_DIRS = ("venv", ".venv")


def active_venv() -> Optional[Path]:
    """Return the active venv prefix, or None if running outside a venv.

    A venv is identified by sys.prefix != sys.base_prefix (the Python 3.3+
    canonical check; works for venv, virtualenv, and conda env-style
    isolated prefixes).
    """
    if Path(sys.prefix) != Path(sys.base_prefix):
        return Path(sys.prefix)
    return None


def is_local_venv(venv: Path, project_root: Path) -> bool:
    """True iff `venv` is a recognized local-venv directory inside `project_root`.

    Accepted layouts: `<project_root>/venv` and `<project_root>/.venv`.
    Path comparison is done after resolve() so symlinks and
    case differences (Windows) don't cause false negatives.
    """
    try:
        venv_resolved = venv.resolve()
        root = project_root.resolve()
    except OSError:
        return False
    for name in ACCEPTED_VENV_DIRS:
        candidate = root / name
        try:
            if venv_resolved == candidate.resolve():
                return True
        except OSError:
            continue
    return False


def _venv_site_packages(venv: Path) -> Optional[Path]:
    """Return the site-packages dir for `venv`, or None if not found.

    Windows venvs use `Lib/site-packages`; POSIX venvs use
    `lib/pythonX.Y/site-packages`. Same repo runs on both, so we try
    both. Returns the first match.
    """
    candidates = [
        venv / "Lib" / "site-packages",
        venv / "lib"
            / f"python{sys.version_info.major}.{sys.version_info.minor}"
            / "site-packages",
    ]
    for c in candidates:
        if c.is_dir():
            return c
    return None


def install_sitecustomize(venv: Path, payload: str) -> Optional[Path]:
    """Drop `payload` into venv/site-packages/sitecustomize.py.

    Idempotent: if the file already exists with identical content, do
    not rewrite (preserves mtime so the integrity audit and editor file
    watchers don't see needless churn). Returns the install path on
    success, None when the venv layout is unrecognized.
    """
    site_packages = _venv_site_packages(venv)
    if site_packages is None:
        return None
    target = site_packages / "sitecustomize.py"
    if target.exists() and target.read_text(encoding="utf-8") == payload:
        return target
    target.write_text(payload, encoding="utf-8")
    return target


def configure_git_hooks(repo: Path, hooks_dir: str = ".githooks") -> bool:
    """Set core.hooksPath = hooks_dir on `repo`, scoped --local only.

    Refuses to overwrite a pre-existing user value pointing somewhere
    else (a student who customized their own hooks shouldn't be
    silently re-pointed). Returns True when the value is `hooks_dir`
    at function exit, False otherwise. Never raises.
    """
    try:
        existing = subprocess.run(
            ["git", "config", "--local", "core.hooksPath"],
            cwd=str(repo), capture_output=True, text=True,
        )
        # Exit 128 means not a git repo; exit 1 means key unset.
        if existing.returncode == 128:
            return False
        current = existing.stdout.strip() if existing.returncode == 0 else ""
        if current == hooks_dir:
            return True
        if current and current != hooks_dir:
            return False  # user customization; leave it
        subprocess.run(
            ["git", "config", "--local", "core.hooksPath", hooks_dir],
            cwd=str(repo), check=True,
        )
        return True
    except Exception:
        return False


def ensure_installed(repo: Path) -> None:
    """Idempotently install all editor-agnostic capture triggers.

    Called from pytest_sessionstart on every pytest run. Self-heals:
    if the venv layout is unrecognized, the repo isn't a git repo, or
    the payload module is missing, each piece silently no-ops rather
    than raising. The capture layer must never break the test run.
    """
    try:
        venv = active_venv()
        if venv is not None and is_local_venv(venv, repo):
            try:
                from tests._capture import sitecustomize_payload
                install_sitecustomize(venv, sitecustomize_payload.PAYLOAD)
            except Exception:
                pass
    except Exception:
        pass
    try:
        configure_git_hooks(repo)
    except Exception:
        pass
