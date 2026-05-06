"""Codex CLI adapter for the vendor-neutral AI trace layer."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from tests._capture import ai_traces, codex_ingest
from tests._capture.agent_adapters import codex_normalize
from tests._capture.agent_adapters.base import AdapterMetadata, IngestResult


class CodexAdapter:
    """Codex CLI adapter. Codex is one adapter behind the common boundary."""

    name = "codex"
    transcripts_dir = ai_traces.AI_TRACES_DIR

    def is_present(self) -> bool:
        try:
            home = os.environ.get("CODEX_HOME")
            if home:
                return (Path(home) / "sessions").is_dir()
            return (Path.home() / ".codex" / "sessions").is_dir()
        except (OSError, RuntimeError):
            return False

    def is_present_for_repo(self, repo: Path) -> bool:
        return (
            (repo / ".codex").exists()
            or ai_traces.adapter_dir(repo, self.name).exists()
            or self.is_present()
        )

    def ingest(self, repo: Path, since: Optional[float]) -> IngestResult:
        try:
            evidence_root = ai_traces.adapter_dir(repo, self.name)
            repo_has_codex_config = (repo / ".codex").exists()
            explicit_codex_home = bool(os.environ.get("CODEX_HOME"))
            if (
                not repo_has_codex_config
                and not explicit_codex_home
                and not evidence_root.exists()
            ):
                return IngestResult(adapter_name=self.name)

            copied = codex_ingest.ingest_transcripts(repo, since or 0.0)
            if not copied and not evidence_root.exists():
                return IngestResult(adapter_name=self.name)

            ai_traces.ensure_attestation(repo)
            built = codex_normalize.normalize_all(repo)
            return IngestResult(
                adapter_name=self.name,
                rollouts_copied=list(copied),
                summaries_built=list(built),
                source_hashes=ai_traces.collect_hashes(repo),
            )
        except Exception as e:  # belt-and-suspenders; adapter capture is best-effort
            return IngestResult(adapter_name=self.name, errors=[str(e)])

    def metadata_from_hook_payload(self, payload: Dict[str, Any]) -> AdapterMetadata:
        session_id = str(
            payload.get("session_id")
            or payload.get("conversation_id")
            or payload.get("id")
            or "unknown"
        )
        rollout = payload.get("rollout_path")
        rollout_path = Path(rollout) if isinstance(rollout, str) and rollout else None
        extra = {
            str(k): str(v)
            for k, v in payload.items()
            if k in {"cwd", "turn_id", "request_id", "tool_name"}
            and v is not None
        }
        return AdapterMetadata(
            adapter_name=self.name,
            agent_session_id=session_id,
            rollout_path=rollout_path,
            extra=extra,
        )

    def detect_active_session(self) -> Optional[AdapterMetadata]:
        # Stop hooks pass payload metadata directly through
        # metadata_from_hook_payload(); pytest-trigger snapshots do not have
        # an active Codex hook payload to inspect.
        return None

    def stage_paths(self) -> List[str]:
        return [self.transcripts_dir, ".codex"]

    def force_paths(self) -> List[str]:
        return [self.transcripts_dir, ".codex"]

    def unstage_after(self) -> List[str]:
        return [".codex/auth.json", ".codex/hooks/__pycache__"]
