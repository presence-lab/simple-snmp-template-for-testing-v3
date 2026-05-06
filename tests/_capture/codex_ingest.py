"""Copy Codex rollout transcripts for this repo into .ai-traces/.

Called from CodexAdapter.ingest (orchestrator-driven). We pull matching
rollouts out of $CODEX_HOME/sessions/, filter by cwd == repo, and copy them
into .ai-traces/codex/raw/rollouts so the adapter can normalize them.

We intentionally do NOT filter by mtime against the pytest session start.
The realistic workflow is: student runs Codex (rollout mtime fixed), then
LATER runs pytest. An mtime >= session_start filter would exclude every
such rollout because the rollout was finalized before pytest started. The
right semantic — "capture all Codex rollouts for this repo that aren't
already captured" — is achieved by the cwd match plus the idempotency
check below (destination file exists → skip). The session_started_at
parameter is kept for API stability but is currently unused.

Contract: never raises. Returns the list of copied destination paths (possibly
empty). Any error is swallowed and results in an empty list (or a shorter
list of successfully-copied paths), matching capture.py's best-effort error
policy.

Rollout shape (as of Codex CLI 0.119.x, see Task 1 discovery notes):
    Path:    $CODEX_HOME/sessions/YYYY/MM/DD/rollout-<ts>-<uuid>.jsonl
    Line 1:  {"type": "session_meta",
              "payload": {"id": ..., "cwd": "C:\\...", ...}, ...}
Drive-letter casing in payload.cwd varies by producer (``codex exec`` emits
``C:\\`` while the VS Code extension emits ``c:\\``), so both candidate cwd
and target repo are normalized via ``Path.resolve()`` before comparison.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import List, Optional

from tests._capture import ai_traces

TRANSCRIPTS_DIR = ai_traces.AI_TRACES_DIR
CODEX_ROLLOUTS_DIR = Path(ai_traces.AI_TRACES_DIR) / "codex" / "raw" / "rollouts"
ROLLOUT_GLOB = "rollout-*.jsonl"


def _codex_sessions_dir() -> Optional[Path]:
    """Return the sessions directory, or None if $CODEX_HOME is unusable."""
    home = os.environ.get("CODEX_HOME")
    if home:
        return Path(home) / "sessions"
    # Fall back to the default Codex CLI location when the env var is unset.
    try:
        return Path.home() / ".codex" / "sessions"
    except (OSError, RuntimeError):
        return None


def _rollout_cwd(path: Path) -> str:
    """Return payload.cwd from the first JSONL line, or "" on any error.

    Guards on ``type == "session_meta"`` so that a future schema change
    (different first-record type) fails cleanly rather than matching garbage.
    """
    try:
        with path.open("r", encoding="utf-8") as f:
            first = f.readline()
        if not first:
            return ""
        obj = json.loads(first)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return ""
    if not isinstance(obj, dict):
        return ""
    if obj.get("type") != "session_meta":
        return ""
    payload = obj.get("payload")
    if not isinstance(payload, dict):
        return ""
    cwd = payload.get("cwd", "")
    return cwd if isinstance(cwd, str) else ""


def _same_path(candidate: str, repo: Path) -> bool:
    """True if candidate and repo resolve to the same filesystem location.

    Handles Windows drive-letter case insensitivity via ``Path.resolve()``.
    """
    if not candidate:
        return False
    try:
        return Path(candidate).resolve() == repo.resolve()
    except (OSError, ValueError):
        return False


def ingest_transcripts(repo: Path, session_started_at: float) -> List[Path]:
    """Copy matching rollouts into repo/.ai-traces/codex/raw/rollouts/. Never raises.

    Selection criteria:
      * rollout payload.cwd resolves to the same path as ``repo``

    Idempotent: if a destination file already exists (from a prior run) it
    is skipped and not re-reported as newly copied. Combined with the cwd
    match, this gives "capture everything new since last pytest" without
    needing to track mtimes across sessions.

    ``session_started_at`` is accepted for API stability but unused — see
    the module docstring for why mtime-based filtering was removed.
    """
    del session_started_at  # intentionally unused; see module docstring
    try:
        sessions_dir = _codex_sessions_dir()
        if sessions_dir is None or not sessions_dir.is_dir():
            return []

        copied: List[Path] = []
        try:
            candidates = list(sessions_dir.rglob(ROLLOUT_GLOB))
        except OSError:
            return []

        for src in candidates:
            try:
                if not src.is_file():
                    continue
            except OSError:
                continue
            if not _same_path(_rollout_cwd(src), repo):
                continue
            dest_dir = repo / CODEX_ROLLOUTS_DIR
            try:
                dest_dir.mkdir(parents=True, exist_ok=True)
            except OSError:
                return copied
            dest = dest_dir / src.name
            if dest.exists():
                continue
            try:
                shutil.copy2(src, dest)
                copied.append(dest)
            except OSError:
                continue
        return copied
    except Exception:
        # Absolute belt-and-suspenders: the capture layer must never propagate
        # an exception into pytest's session_finish. If anything above slips
        # past the narrower except clauses, swallow it here.
        return []
