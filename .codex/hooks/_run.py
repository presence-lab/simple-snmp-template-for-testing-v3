#!/usr/bin/env python3
"""Cross-platform Codex hook launcher.

Codex invokes this with the hook script basename as the only argument:

    python3 .codex/hooks/_run.py stop

We resolve the project's venv interpreter for the current OS and, if we
are not already running under it, re-exec there before dispatching to
the requested hook. The capture machinery's site-customize lives only
in the venv, so running hooks outside it would silently no-op.

Bootstrap interpreter expectations:
- macOS: ``python3`` ships with the Xcode Command Line Tools.
- Linux: ``python3`` is universal on every modern distro.
- Windows: ``python3`` is registered by the python.org installer and
  the Microsoft Store package. If a student has only ``python``,
  change the bootstrap in .codex/config.toml or add a ``python3`` alias.
"""
from __future__ import annotations

import os
import runpy
import subprocess
import sys
from pathlib import Path


HOOK_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = HOOK_DIR.parent.parent


def _venv_python() -> Path | None:
    if os.name == "nt":
        candidate = PROJECT_ROOT / "venv" / "Scripts" / "python.exe"
    else:
        candidate = PROJECT_ROOT / "venv" / "bin" / "python"
    return candidate if candidate.is_file() else None


def _running_in_venv() -> bool:
    return sys.prefix != getattr(sys, "base_prefix", sys.prefix)


def _reexec_under_venv(venv: Path, hook_name: str) -> int:
    argv = [str(venv), str(Path(__file__).resolve()), hook_name]
    if os.name == "nt":
        return subprocess.call(argv, stdin=sys.stdin)
    os.execv(str(venv), argv)
    return 0  # unreachable on POSIX


def main() -> int:
    if len(sys.argv) < 2:
        return 0
    hook_name = sys.argv[1]
    hook_script = HOOK_DIR / f"{hook_name}.py"
    if not hook_script.is_file():
        return 0

    venv = _venv_python()
    if venv is not None and not _running_in_venv():
        return _reexec_under_venv(venv, hook_name)

    sys.argv = [str(hook_script)]
    runpy.run_path(str(hook_script), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
