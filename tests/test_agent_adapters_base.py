"""Tests for agent_adapters.base — IngestResult and AdapterMetadata."""
import dataclasses
from pathlib import Path

import pytest

from tests._capture.agent_adapters.base import IngestResult, AdapterMetadata


def test_ingest_result_default_empty():
    r = IngestResult(adapter_name="codex")
    assert r.rollouts_copied == []
    assert r.rollouts_skipped == []
    assert r.summaries_built == []
    assert r.source_hashes == []
    assert r.flags == []
    assert r.errors == []


def test_ingest_result_merge_combines_lists():
    a = IngestResult(adapter_name="codex", rollouts_copied=[Path("a.jsonl")])
    b = IngestResult(adapter_name="codex", rollouts_copied=[Path("b.jsonl")])
    merged = IngestResult.merge([a, b])
    assert sorted(p.name for p in merged.rollouts_copied) == ["a.jsonl", "b.jsonl"]


def test_ingest_result_merge_combines_all_fields():
    a = IngestResult(
        adapter_name="codex",
        rollouts_copied=[Path("a.jsonl")],
        rollouts_skipped=[Path("skip-a.jsonl")],
        summaries_built=[Path("a.summary.json")],
        source_hashes=[{"path": "a", "sha256": "aaaa"}],
        flags=[Path("a.flag")],
        errors=["err-a"],
    )
    b = IngestResult(
        adapter_name="codex",
        rollouts_copied=[Path("b.jsonl")],
        rollouts_skipped=[Path("skip-b.jsonl")],
        summaries_built=[Path("b.summary.json")],
        source_hashes=[{"path": "b", "sha256": "bbbb"}],
        flags=[Path("b.flag")],
        errors=["err-b"],
    )
    merged = IngestResult.merge([a, b])
    assert merged.adapter_name == "codex"
    assert len(merged.rollouts_copied) == 2
    assert len(merged.rollouts_skipped) == 2
    assert len(merged.summaries_built) == 2
    assert len(merged.source_hashes) == 2
    assert len(merged.flags) == 2
    assert merged.errors == ["err-a", "err-b"]


def test_ingest_result_merge_empty_list_returns_blank():
    merged = IngestResult.merge([])
    assert merged.adapter_name == ""
    assert merged.rollouts_copied == []


def test_ingest_result_merge_rejects_mixed_adapters():
    a = IngestResult(adapter_name="codex")
    b = IngestResult(adapter_name="claude_code")
    with pytest.raises(ValueError):
        IngestResult.merge([a, b])


def test_adapter_metadata_is_frozen():
    m = AdapterMetadata(
        adapter_name="codex", agent_session_id="sess",
        rollout_path=None, extra={},
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        m.adapter_name = "other"  # type: ignore[misc]


def test_adapter_metadata_extra_default_empty():
    m = AdapterMetadata(
        adapter_name="codex", agent_session_id="sess",
        rollout_path=Path("rollout-x.jsonl"),
    )
    assert m.extra == {}
    assert m.rollout_path == Path("rollout-x.jsonl")
