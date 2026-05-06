"""Hard-coded adapter registry.

Per orchestrator spec decision row 1, this is a tuple of class objects
rather than a dynamic plugin loader. Future adapters add themselves
here directly. Tests can monkeypatch `_REGISTERED` to substitute
stubs without touching the import system.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List

from . import AgentAdapter
from .codex import CodexAdapter

# Class objects, NOT instances. installed_adapters() instantiates each
# one and runs is_present() before yielding it.
_REGISTERED = (CodexAdapter,)


def installed_adapters(repo: Path) -> List[AgentAdapter]:
    """Return concrete adapter instances that are enabled in config AND
    present on this machine. Order matches `_REGISTERED`.

    See orchestrator spec §7. Adapters whose constructor raises, that
    fail isinstance(AgentAdapter), or whose is_present() returns False
    are skipped silently.
    """
    config_path = repo / "project-template-config.json"
    enabled_map: dict = {}
    if config_path.exists():
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            enabled_map = data.get("agent_adapters", {}) or {}
        except (OSError, json.JSONDecodeError):
            # Treat unreadable config as "no adapter overrides" — spec row 7
            # says adapters default to all-enabled when the block is missing.
            pass
    out: List[AgentAdapter] = []
    for cls in _REGISTERED:
        cfg = enabled_map.get(getattr(cls, "name", ""), {})
        if cfg.get("enabled", True) is False:
            continue
        try:
            inst = cls()
        except Exception:
            continue
        if not isinstance(inst, AgentAdapter):
            continue
        try:
            present_for_repo = getattr(inst, "is_present_for_repo", None)
            present = (
                present_for_repo(repo)
                if callable(present_for_repo)
                else inst.is_present()
            )
            if not present:
                continue
        except Exception:
            continue
        out.append(inst)
    return out
