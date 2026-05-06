"""Shared dataclasses for the agent adapter framework.

See orchestrator spec §4.2. IngestResult carries everything the
orchestrator needs to compose a commit (rollouts, summaries, hashes,
flags, errors); AdapterMetadata carries identity for snapshot labeling.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass(frozen=True)
class AdapterMetadata:
    """Identity + provenance for an adapter's active session.

    Used by triggers that fire mid-session (agent Stop hooks) to label the
    snapshot with the agent's session id. None-valued for pytest triggers
    where the orchestrator runs after the agent has already exited.
    """
    adapter_name: str
    agent_session_id: str
    rollout_path: Optional[Path] = None
    extra: Dict[str, str] = field(default_factory=dict)


@dataclass
class IngestResult:
    """What an adapter's ingest() pass produced. The orchestrator merges
    one of these per adapter into a snapshot-wide IngestBundle."""
    adapter_name: str
    rollouts_copied: List[Path] = field(default_factory=list)
    rollouts_skipped: List[Path] = field(default_factory=list)
    summaries_built: List[Path] = field(default_factory=list)
    source_hashes: List[Dict[str, str]] = field(default_factory=list)
    flags: List[Path] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @classmethod
    def merge(cls, results: List["IngestResult"]) -> "IngestResult":
        """Combine same-adapter IngestResults. Raises ValueError if mixed adapters."""
        if not results:
            return cls(adapter_name="")
        names = {r.adapter_name for r in results}
        if len(names) > 1:
            raise ValueError(f"cannot merge across adapters: {names}")
        out = cls(adapter_name=results[0].adapter_name)
        for r in results:
            out.rollouts_copied.extend(r.rollouts_copied)
            out.rollouts_skipped.extend(r.rollouts_skipped)
            out.summaries_built.extend(r.summaries_built)
            out.source_hashes.extend(r.source_hashes)
            out.flags.extend(r.flags)
            out.errors.extend(r.errors)
        return out
