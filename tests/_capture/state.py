"""Session state markers for orphan detection.

When a pytest session starts, we drop a JSON marker. When it finishes cleanly,
we remove it. If a subsequent session finds a marker whose deadline has passed,
that's an orphan — the previous session died hard without a finish hook firing.
We record it as a commit on the next start.
"""
from __future__ import annotations

import json
import secrets
import time
from pathlib import Path
from typing import List, Dict


STATE_DIR = ".test-run-state"


def _state_dir(repo: Path) -> Path:
    d = repo / STATE_DIR
    d.mkdir(exist_ok=True)
    return d


def new_session_id() -> str:
    return secrets.token_hex(4)  # 8 hex chars


def start_session(repo: Path, hard_deadline_seconds: float) -> str:
    """Create a marker file. Returns the new session_id."""
    sid = new_session_id()
    marker = _state_dir(repo) / f"{sid}.json"
    marker.write_text(json.dumps({
        "session_id": sid,
        "started_at": time.time(),
        "hard_deadline_seconds": hard_deadline_seconds,
    }))
    return sid


def finish_session(repo: Path, session_id: str) -> None:
    """Remove the marker for a session that finished cleanly."""
    marker = _state_dir(repo) / f"{session_id}.json"
    try:
        marker.unlink()
    except FileNotFoundError:
        pass


def detect_orphans(repo: Path) -> List[Dict]:
    """Return markers whose deadlines have passed."""
    d = _state_dir(repo)
    orphans = []
    now = time.time()
    for marker in d.glob("*.json"):
        try:
            data = json.loads(marker.read_text())
            deadline = data.get("started_at", 0) + data.get("hard_deadline_seconds", 0)
            if now > deadline:
                orphans.append(data)
        except (json.JSONDecodeError, OSError):
            # Corrupted marker — treat as orphan so it gets cleaned up.
            orphans.append({"session_id": marker.stem, "corrupted": True})
    return orphans


def clear_orphans(repo: Path, orphans: List[Dict]) -> None:
    d = _state_dir(repo)
    for o in orphans:
        marker = d / f"{o['session_id']}.json"
        try:
            marker.unlink()
        except FileNotFoundError:
            pass
