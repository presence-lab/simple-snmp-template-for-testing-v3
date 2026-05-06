"""Agent adapter framework for the snapshot orchestrator.

See spec §4.2 (Protocol) and §4.1 (registry layout). Concrete adapters
live in sibling modules (e.g., codex.py); the orchestrator discovers
them through `installed_adapters()` (Task 2.5.3) and dispatches ingest
calls through the `AgentAdapter` Protocol (Task 2.5.2).
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Protocol, runtime_checkable

from .base import AdapterMetadata, IngestResult

__all__ = ["AgentAdapter", "AdapterMetadata", "IngestResult", "installed_adapters"]


@runtime_checkable
class AgentAdapter(Protocol):
    """One agentic system capable of contributing transcripts to a capture
    snapshot. ``transcripts_dir`` is the canonical trace root for the adapter
    (for Codex, ``.ai-traces``). See orchestrator spec §4.2 for full contract.

    Two OPTIONAL methods may be implemented on top of this Protocol; both
    default to empty lists and are NOT in the runtime_checkable contract
    so adapters predating Task 2.5.10 still pass isinstance checks:

      * `force_paths() -> List[str]` — repo-relative paths that MUST be
        staged with `git add -f` even if .gitignore would exclude them.
        Defeats Attack K (gitignore evasion).
      * `unstage_after() -> List[str]` — repo-relative paths to
        `git rm --cached --ignore-unmatch` after the stage. Defeats
        Attack L (accidental .codex/auth.json staging).

    The orchestrator probes for these via getattr() and tolerates their
    absence.

    Adapters may also implement `is_present_for_repo(repo) -> bool` when
    repo-local configuration or trace artifacts are a better presence signal
    than a global install check.
    """

    name: str
    transcripts_dir: str

    def is_present(self) -> bool: ...
    def ingest(self, repo: Path, since: Optional[float]) -> IngestResult: ...
    def detect_active_session(self) -> Optional[AdapterMetadata]: ...
    def stage_paths(self) -> List[str]: ...


def installed_adapters(repo: Path) -> List[AgentAdapter]:
    """Convenience wrapper so callers can write
    `from tests._capture.agent_adapters import installed_adapters`.

    Implementation lives in `.registry` to avoid pulling concrete adapter
    classes (which import non-Protocol dependencies) into this module's
    eager import path.
    """
    from . import registry
    return registry.installed_adapters(repo)
