"""Tests for the AgentAdapter Protocol contract."""
from pathlib import Path
from typing import List, Optional

from tests._capture.agent_adapters import AgentAdapter
from tests._capture.agent_adapters.base import AdapterMetadata, IngestResult


class _MockAdapter:
    name = "mock"
    transcripts_dir = ".mock-transcripts"

    def is_present(self) -> bool:
        return True

    def ingest(self, repo: Path, since: Optional[float]) -> IngestResult:
        return IngestResult(adapter_name="mock")

    def detect_active_session(self) -> Optional[AdapterMetadata]:
        return None

    def stage_paths(self) -> List[str]:
        return [self.transcripts_dir]


def test_mock_adapter_satisfies_protocol():
    adapter = _MockAdapter()
    assert isinstance(adapter, AgentAdapter)


def test_incomplete_adapter_fails_isinstance():
    class Broken:
        name = "broken"
        # missing transcripts_dir + methods
    assert not isinstance(Broken(), AgentAdapter)


def test_partial_adapter_missing_method_fails():
    class PartialAdapter:
        name = "partial"
        transcripts_dir = ".partial"

        def is_present(self) -> bool:
            return True

        def ingest(self, repo, since):
            return IngestResult(adapter_name="partial")
        # missing detect_active_session and stage_paths

    assert not isinstance(PartialAdapter(), AgentAdapter)
