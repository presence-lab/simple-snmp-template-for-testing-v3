"""Shared helpers for repo-local Codex hooks.

Hooks are evidence capture only. They must never block a Codex turn because
the course harness should fail open and leave a visible log/flag later.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Callable, Dict


def project_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def read_payload() -> Dict[str, object]:
    try:
        raw = sys.stdin.read()
        if not raw:
            return {}
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def session_cwd_inside_project(payload: Dict[str, object]) -> bool:
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        return True
    try:
        Path(cwd).resolve().relative_to(project_repo_root().resolve())
        return True
    except (OSError, ValueError):
        return False


def append_hook_event(event_name: str, payload: Dict[str, object]) -> None:
    if not session_cwd_inside_project(payload):
        return
    repo = project_repo_root()
    session_id = payload.get("session_id") or payload.get("agent_id") or "unknown"
    if not isinstance(session_id, str) or not session_id:
        session_id = "unknown"
    out = repo / ".ai-traces" / "codex" / "raw" / "hooks" / f"hooks-{session_id}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "adapter_name": "codex",
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "hook_event_name": event_name,
        "payload": payload,
    }
    with out.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def safe_main(
    event_name: str,
    callback: Callable[[Dict[str, object]], None] | None = None,
    *,
    emit_continue_json: bool = False,
) -> int:
    try:
        payload = read_payload()
        append_hook_event(event_name, payload)
        if callback is not None and session_cwd_inside_project(payload):
            callback(payload)
    except Exception:
        pass
    if emit_continue_json:
        sys.stdout.write(json.dumps({"continue": True}))
    return 0
