"""Tests for orchestrator's artifact_hashes aggregation (Task 2.5.9)."""
import subprocess
from pathlib import Path
from typing import List, Optional

import pytest

from tests._capture import orchestrator
from tests._capture.agent_adapters import registry
from tests._capture.agent_adapters.base import IngestResult, AdapterMetadata


def _read_body(repo: Path) -> str:
    return subprocess.run(
        ["git", "log", "-1", "--format=%B", "refs/auto-track/snapshots"],
        cwd=repo, capture_output=True, text=True, check=True).stdout


class _FakeAdapter:
    """Adapter that drops a transcript file and reports a source hash."""
    name = "fake"
    transcripts_dir = ".fake-transcripts"

    def is_present(self) -> bool:
        return True

    def detect_active_session(self) -> Optional[AdapterMetadata]:
        return None

    def stage_paths(self) -> List[str]:
        return [self.transcripts_dir]

    def ingest(self, repo: Path, since) -> IngestResult:
        d = repo / self.transcripts_dir
        d.mkdir(exist_ok=True)
        (d / "x.jsonl").write_text("hi")
        return IngestResult(
            adapter_name=self.name,
            rollouts_copied=[Path(self.transcripts_dir) / "x.jsonl"],
            source_hashes=[
                {"path": ".fake-transcripts/x.jsonl",
                 "sha256": "deadbeef" * 8},
            ],
        )


class _OtherAdapter:
    name = "alpha"
    transcripts_dir = ".alpha-transcripts"

    def is_present(self) -> bool:
        return True

    def detect_active_session(self) -> Optional[AdapterMetadata]:
        return None

    def stage_paths(self) -> List[str]:
        return [self.transcripts_dir]

    def ingest(self, repo: Path, since) -> IngestResult:
        d = repo / self.transcripts_dir
        d.mkdir(exist_ok=True)
        (d / "y.jsonl").write_text("yo")
        return IngestResult(
            adapter_name=self.name,
            rollouts_copied=[Path(self.transcripts_dir) / "y.jsonl"],
            source_hashes=[
                {"path": ".alpha-transcripts/y.jsonl",
                 "sha256": "cafef00d" * 8},
            ],
        )


class _ManyHashesAdapter:
    """Reports 60 source hashes — exercises the 50-entry per-adapter cap."""
    name = "many"
    transcripts_dir = ".many-transcripts"

    def is_present(self) -> bool:
        return True

    def detect_active_session(self) -> Optional[AdapterMetadata]:
        return None

    def stage_paths(self) -> List[str]:
        return [self.transcripts_dir]

    def ingest(self, repo: Path, since) -> IngestResult:
        d = repo / self.transcripts_dir
        d.mkdir(exist_ok=True)
        (d / "marker.jsonl").write_text("m")
        hashes = [
            {"path": f".many-transcripts/{i:03d}.jsonl",
             "sha256": f"{i:064x}"}
            for i in range(60)
        ]
        return IngestResult(
            adapter_name=self.name,
            rollouts_copied=[Path(self.transcripts_dir) / "marker.jsonl"],
            source_hashes=hashes,
        )


class _SilentAdapter:
    """Adapter that ingests nothing — should NOT contribute an artifact_hashes
    sub-block."""
    name = "silent"
    transcripts_dir = ".silent-transcripts"

    def is_present(self) -> bool:
        return True

    def detect_active_session(self) -> Optional[AdapterMetadata]:
        return None

    def stage_paths(self) -> List[str]:
        return [self.transcripts_dir]

    def ingest(self, repo: Path, since) -> IngestResult:
        return IngestResult(adapter_name=self.name)


def test_take_snapshot_aggregates_source_hashes_into_artifact_hashes(
        tmp_git_repo_with_capture, monkeypatch):
    repo = tmp_git_repo_with_capture
    monkeypatch.setattr(registry, "_REGISTERED", (_FakeAdapter,))

    sha = orchestrator.take_snapshot(
        repo, trigger="pytest", pytest_session_id="sess-1")
    assert sha is not None
    body = _read_body(repo)
    assert "artifact_hashes:" in body
    assert "  fake:" in body
    assert "    .fake-transcripts/x.jsonl: " + ("deadbeef" * 8) in body


def test_take_snapshot_two_adapter_sub_blocks(
        tmp_git_repo_with_capture, monkeypatch):
    """Two adapters each contributing source_hashes produce two sub-blocks
    with deterministic ordering (alphabetical by adapter name)."""
    repo = tmp_git_repo_with_capture
    monkeypatch.setattr(registry, "_REGISTERED",
                        (_FakeAdapter, _OtherAdapter))

    sha = orchestrator.take_snapshot(
        repo, trigger="pytest", pytest_session_id="multi-1")
    assert sha is not None
    body = _read_body(repo)
    assert "artifact_hashes:" in body
    assert "  alpha:" in body
    assert "  fake:" in body
    # alpha must precede fake (alphabetical adapter ordering per metadata.py).
    alpha_idx = body.index("  alpha:")
    fake_idx = body.index("  fake:")
    assert alpha_idx < fake_idx


def test_take_snapshot_50_entry_cap_per_adapter(
        tmp_git_repo_with_capture, monkeypatch):
    """An adapter contributing 60 source hashes lists 50 + a `(+10 more)` line."""
    repo = tmp_git_repo_with_capture
    monkeypatch.setattr(registry, "_REGISTERED", (_ManyHashesAdapter,))
    sha = orchestrator.take_snapshot(
        repo, trigger="pytest", pytest_session_id="cap-1")
    assert sha is not None
    body = _read_body(repo)
    assert "  many:" in body
    # Sorted alphabetically by path: 000.jsonl is first, 049.jsonl is the
    # 50th, and 050.jsonl is the first one excluded.
    assert ".many-transcripts/000.jsonl: " in body
    assert ".many-transcripts/049.jsonl: " in body
    assert ".many-transcripts/050.jsonl" not in body
    assert "(+10 more)" in body


def test_take_snapshot_skips_artifact_hashes_block_when_no_adapter_contributes(
        tmp_git_repo_with_capture, monkeypatch):
    """Empty source_hashes across all adapters → no `artifact_hashes:` line."""
    repo = tmp_git_repo_with_capture
    monkeypatch.setattr(registry, "_REGISTERED", (_SilentAdapter,))
    sha = orchestrator.take_snapshot(
        repo, trigger="pytest", pytest_session_id="silent-1")
    assert sha is not None
    body = _read_body(repo)
    assert "artifact_hashes:" not in body


def test_take_snapshot_drops_malformed_source_hash_entries(
        tmp_git_repo_with_capture, monkeypatch):
    """Entries missing path or sha256 are dropped, not crashed on."""
    class Malformed:
        name = "malformed"
        transcripts_dir = ".malformed-transcripts"

        def is_present(self):
            return True

        def detect_active_session(self):
            return None

        def stage_paths(self):
            return [self.transcripts_dir]

        def ingest(self, repo, since):
            d = repo / self.transcripts_dir
            d.mkdir(exist_ok=True)
            (d / "ok.jsonl").write_text("ok")
            return IngestResult(
                adapter_name=self.name,
                rollouts_copied=[Path(self.transcripts_dir) / "ok.jsonl"],
                source_hashes=[
                    {"path": ".malformed-transcripts/ok.jsonl",
                     "sha256": "a" * 64},
                    {"path": "missing-sha"},  # dropped
                    {"sha256": "b" * 64},     # dropped
                ],
            )

    repo = tmp_git_repo_with_capture
    monkeypatch.setattr(registry, "_REGISTERED", (Malformed,))
    sha = orchestrator.take_snapshot(
        repo, trigger="pytest", pytest_session_id="malformed-1")
    assert sha is not None
    body = _read_body(repo)
    assert "  malformed:" in body
    assert "ok.jsonl: " + ("a" * 64) in body
    assert "missing-sha" not in body
