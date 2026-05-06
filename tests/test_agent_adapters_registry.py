"""Tests for the agent adapter registry."""
from pathlib import Path
from typing import List, Optional

from tests._capture.agent_adapters import registry
from tests._capture.agent_adapters.base import IngestResult, AdapterMetadata


# --- Stub adapters used across tests --------------------------------------

class _PresentAdapter:
    name = "a"
    transcripts_dir = ".a"

    def is_present(self) -> bool:
        return True

    def ingest(self, repo, since) -> IngestResult:
        return IngestResult(adapter_name="a")

    def detect_active_session(self) -> Optional[AdapterMetadata]:
        return None

    def stage_paths(self) -> List[str]:
        return [".a"]


class _AbsentAdapter:
    name = "b"
    transcripts_dir = ".b"

    def is_present(self) -> bool:
        return False  # not installed on this machine

    def ingest(self, repo, since) -> IngestResult:
        return IngestResult(adapter_name="b")

    def detect_active_session(self) -> Optional[AdapterMetadata]:
        return None

    def stage_paths(self) -> List[str]:
        return [".b"]


class _RepoPresentAdapter(_AbsentAdapter):
    name = "repo-present"

    def is_present_for_repo(self, repo: Path) -> bool:
        return (repo / ".repo-present").exists()


class _CrashOnInit:
    name = "c"
    transcripts_dir = ".c"

    def __init__(self):
        raise RuntimeError("oops")


def _write_config(tmp_path: Path, payload: dict) -> None:
    import json
    (tmp_path / "project-template-config.json").write_text(json.dumps(payload))


# --- Tests ----------------------------------------------------------------

def test_installed_adapters_returns_configured_subset(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "_REGISTERED",
                        (_PresentAdapter, _AbsentAdapter))
    _write_config(tmp_path, {
        "capture_enabled": True,
        "agent_adapters": {"a": {"enabled": True}, "b": {"enabled": True}},
    })
    adapters = registry.installed_adapters(tmp_path)
    assert [a.name for a in adapters] == ["a"]  # B filtered by is_present


def test_installed_adapters_respects_disabled(tmp_path, monkeypatch):
    """An enabled-by-default adapter is filtered out when config disables it."""
    monkeypatch.setattr(registry, "_REGISTERED", (_PresentAdapter,))
    _write_config(tmp_path, {
        "capture_enabled": True,
        "agent_adapters": {"a": {"enabled": False}},
    })
    adapters = registry.installed_adapters(tmp_path)
    assert adapters == []


def test_installed_adapters_default_all_enabled_when_no_block(tmp_path, monkeypatch):
    """Config exists, capture_enabled true, but no agent_adapters block."""
    monkeypatch.setattr(registry, "_REGISTERED", (_PresentAdapter,))
    _write_config(tmp_path, {"capture_enabled": True})
    adapters = registry.installed_adapters(tmp_path)
    assert [a.name for a in adapters] == ["a"]


def test_installed_adapters_default_when_no_config(tmp_path, monkeypatch):
    """No config file at all → every present adapter is included."""
    monkeypatch.setattr(registry, "_REGISTERED", (_PresentAdapter,))
    adapters = registry.installed_adapters(tmp_path)
    assert [a.name for a in adapters] == ["a"]


def test_installed_adapters_supports_repo_presence_hook(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "_REGISTERED", (_RepoPresentAdapter,))
    _write_config(tmp_path, {"capture_enabled": True})
    assert registry.installed_adapters(tmp_path) == []

    (tmp_path / ".repo-present").mkdir()
    adapters = registry.installed_adapters(tmp_path)
    assert [a.name for a in adapters] == ["repo-present"]


def test_installed_adapters_skips_crashing_constructor(tmp_path, monkeypatch):
    """Adapter classes whose __init__ raises are skipped, not propagated."""
    monkeypatch.setattr(registry, "_REGISTERED",
                        (_CrashOnInit, _PresentAdapter))
    _write_config(tmp_path, {"capture_enabled": True})
    adapters = registry.installed_adapters(tmp_path)
    assert [a.name for a in adapters] == ["a"]


def test_installed_adapters_skips_non_protocol_instances(tmp_path, monkeypatch):
    """Adapter that fails isinstance(_, AgentAdapter) is filtered."""

    class Broken:  # missing methods entirely
        name = "broken"
        transcripts_dir = ".broken"

    monkeypatch.setattr(registry, "_REGISTERED", (Broken, _PresentAdapter))
    _write_config(tmp_path, {"capture_enabled": True})
    adapters = registry.installed_adapters(tmp_path)
    assert [a.name for a in adapters] == ["a"]


def test_installed_adapters_handles_unreadable_config(tmp_path, monkeypatch):
    """Malformed JSON → defaults to all-enabled (matches spec row 7)."""
    monkeypatch.setattr(registry, "_REGISTERED", (_PresentAdapter,))
    (tmp_path / "project-template-config.json").write_text("not json{{{")
    adapters = registry.installed_adapters(tmp_path)
    assert [a.name for a in adapters] == ["a"]


def test_installed_adapters_default_registry_includes_codex(tmp_path):
    """Sanity: the real _REGISTERED tuple ships CodexAdapter."""
    from tests._capture.agent_adapters.codex import CodexAdapter
    assert CodexAdapter in registry._REGISTERED
