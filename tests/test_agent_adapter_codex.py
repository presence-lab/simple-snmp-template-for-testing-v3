"""Tests for the CodexAdapter."""
import json
from pathlib import Path

from tests._capture.agent_adapters import AgentAdapter
from tests._capture.agent_adapters.codex import CodexAdapter


def test_codex_adapter_name_and_transcripts_dir():
    adapter = CodexAdapter()
    assert adapter.name == "codex"
    assert adapter.transcripts_dir == ".ai-traces"


def test_codex_adapter_satisfies_protocol():
    assert isinstance(CodexAdapter(), AgentAdapter)


def test_codex_adapter_is_present_when_codex_home_exists(tmp_path, monkeypatch):
    fake_home = tmp_path / "fake-codex"
    (fake_home / "sessions").mkdir(parents=True)
    monkeypatch.setenv("CODEX_HOME", str(fake_home))
    assert CodexAdapter().is_present()


def test_codex_adapter_is_present_false_without_codex_home(monkeypatch, tmp_path):
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)  # no ~/.codex
    assert not CodexAdapter().is_present()


def test_codex_adapter_ingest_normalizes_trace_artifacts(tmp_path, monkeypatch):
    """CodexAdapter.ingest copies raw artifacts and emits normalized events."""
    repo = tmp_path / "r"
    repo.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home"))
    called = {}

    def fake_ingest(r, ts):
        called["repo"] = r
        called["ts"] = ts
        raw = r / ".ai-traces" / "codex" / "raw" / "rollouts" / "rollout-x.jsonl"
        raw.parent.mkdir(parents=True, exist_ok=True)
        raw.write_text(
            json.dumps({
                "type": "session_meta",
                "payload": {"id": "sess-x", "cwd": str(r)},
                "timestamp": "2026-05-02T00:00:00Z",
            }) + "\n"
            + json.dumps({
                "type": "event_msg",
                "payload": {"role": "user", "text": "please help"},
            }) + "\n",
            encoding="utf-8",
        )
        return [raw]

    monkeypatch.setattr(
        "tests._capture.codex_ingest.ingest_transcripts", fake_ingest)
    adapter = CodexAdapter()
    result = adapter.ingest(repo, since=1234.5)
    assert called["repo"] == repo
    assert called["ts"] == 1234.5
    assert result.adapter_name == "codex"
    assert len(result.rollouts_copied) == 1
    assert (repo / ".ai-traces" / "codex" / "normalized" / "sess-x.jsonl").exists()
    assert (repo / ".ai-traces" / "interaction-stream.jsonl").exists()
    assert any(h["path"].endswith("interaction-stream.jsonl") for h in result.source_hashes)


def test_codex_adapter_ingest_handles_zero_since(tmp_path, monkeypatch):
    """since=None collapses to 0.0 when forwarded."""
    repo = tmp_path / "r"
    repo.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home"))
    called = {}

    def fake_ingest(r, ts):
        called["ts"] = ts
        return []

    monkeypatch.setattr(
        "tests._capture.codex_ingest.ingest_transcripts", fake_ingest)
    CodexAdapter().ingest(repo, since=None)
    assert called["ts"] == 0.0
    assert not (repo / ".ai-traces").exists()


def test_codex_adapter_ingest_skips_default_home_without_repo_config(tmp_path, monkeypatch):
    """Throwaway repos should not scan the user's real ~/.codex/sessions tree."""
    repo = tmp_path / "r"
    repo.mkdir()
    monkeypatch.delenv("CODEX_HOME", raising=False)

    def should_not_scan(r, ts):
        raise AssertionError("default Codex home should not be scanned")

    monkeypatch.setattr(
        "tests._capture.codex_ingest.ingest_transcripts", should_not_scan)
    result = CodexAdapter().ingest(repo, since=None)
    assert result.adapter_name == "codex"
    assert result.rollouts_copied == []


def test_codex_adapter_ingest_swallows_exceptions(tmp_path, monkeypatch):
    """If codex_ingest somehow raises, IngestResult.errors carries the message."""
    repo = tmp_path / "r"
    repo.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home"))

    def boom(r, ts):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "tests._capture.codex_ingest.ingest_transcripts", boom)
    result = CodexAdapter().ingest(repo, since=None)
    assert result.adapter_name == "codex"
    assert result.rollouts_copied == []
    assert any("boom" in e for e in result.errors)


def test_codex_adapter_detect_active_session_returns_none():
    assert CodexAdapter().detect_active_session() is None


def test_codex_adapter_stage_paths_includes_codex_dirs():
    paths = CodexAdapter().stage_paths()
    assert ".ai-traces" in paths
    assert ".codex" in paths


def test_codex_adapter_force_paths_and_secret_exclusion():
    adapter = CodexAdapter()
    assert adapter.force_paths() == [".ai-traces", ".codex"]
    assert adapter.unstage_after() == [".codex/auth.json", ".codex/hooks/__pycache__"]


def test_codex_adapter_metadata_from_hook_payload():
    metadata = CodexAdapter().metadata_from_hook_payload({
        "session_id": "sess-1",
        "cwd": "C:/repo",
        "turn_id": "turn-2",
        "rollout_path": "C:/tmp/rollout.jsonl",
    })
    assert metadata.adapter_name == "codex"
    assert metadata.agent_session_id == "sess-1"
    assert metadata.rollout_path == Path("C:/tmp/rollout.jsonl")
    assert metadata.extra["cwd"] == "C:/repo"
