"""Normalize Codex raw artifacts into the common AI interaction schema."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from tests._capture import ai_traces


ADAPTER = "codex"
LEGACY_TRANSCRIPTS_DIR = ".codex-transcripts"
_PATCH_FILE_RE = re.compile(r"^\*\*\* (?:Update|Add|Delete) File: (.+)$")


def normalize_all(repo: Path) -> List[Path]:
    built: List[Path] = []
    rollout_root = ai_traces.raw_dir(repo, ADAPTER, "rollouts")
    for rollout in sorted(rollout_root.glob("rollout-*.jsonl")):
        events = normalize_rollout(repo, rollout)
        if not events:
            continue
        session_id = str(events[0].get("session_id", rollout.stem))
        out = ai_traces.normalized_dir(repo, ADAPTER) / f"{session_id}.jsonl"
        ai_traces.write_jsonl(out, events)
        built.append(out)

    hook_events = normalize_hook_logs(repo)
    if hook_events:
        out = ai_traces.normalized_dir(repo, ADAPTER) / "hooks.jsonl"
        ai_traces.write_jsonl(out, hook_events)
        built.append(out)

    if built:
        ai_traces.rebuild_interaction_stream(repo)
    return built


def normalize_legacy_codex_transcripts(repo: Path) -> List[dict]:
    events: List[dict] = []
    for rollout in sorted((repo / LEGACY_TRANSCRIPTS_DIR).glob("rollout-*.jsonl")):
        events.extend(normalize_rollout(repo, rollout))
    return events


def normalize_rollout(repo: Path, rollout: Path) -> List[dict]:
    rows = _load_jsonl(rollout)
    if not rows:
        return []

    rel = ai_traces.repo_rel(repo, rollout)
    session_id = rollout.stem
    cwd = ""
    events: List[dict] = []
    turn_id = "turn-0"
    turn_num = 0
    pending_tool_files: Dict[str, List[str]] = {}

    for idx, row in enumerate(rows):
        typ = str(row.get("type", ""))
        payload = row.get("payload")
        if not isinstance(payload, dict):
            payload = {}
        ts = _timestamp(row, payload)

        if typ == "session_meta":
            session_id = str(payload.get("id") or session_id)
            cwd = str(payload.get("cwd") or cwd)
            events.append(_event(
                session_id=session_id,
                turn_id="session",
                event_type="session_start",
                cwd=cwd,
                evidence_refs=[f"{rel}:{idx + 1}"],
                ts=ts,
                extras={"raw_type": typ, "raw_payload": payload},
            ))
            continue

        if typ == "turn_context":
            turn_num += 1
            turn_id = str(payload.get("turn_id") or f"turn-{turn_num}")
            cwd = str(payload.get("cwd") or cwd)
            events.append(_event(
                session_id=session_id,
                turn_id=turn_id,
                event_type="turn_start",
                cwd=cwd,
                evidence_refs=[f"{rel}:{idx + 1}"],
                ts=ts,
                extras={"raw_type": typ, "raw_payload": payload},
            ))
            continue

        event = _normalize_known_row(
            typ=typ,
            payload=payload,
            row=row,
            session_id=session_id,
            turn_id=turn_id,
            cwd=cwd,
            evidence_ref=f"{rel}:{idx + 1}",
            ts=ts,
        )
        if event:
            tool_use_id = str(event.get("tool_use_id") or "")
            if event.get("event_type") == "tool_start" and tool_use_id:
                files = event.get("files_touched") or []
                if isinstance(files, list) and files:
                    pending_tool_files[tool_use_id] = [str(f) for f in files]
            elif event.get("event_type") == "tool_result" and tool_use_id:
                if not event.get("files_touched") and tool_use_id in pending_tool_files:
                    event["files_touched"] = pending_tool_files[tool_use_id]
            events.append(event)

    if events:
        events.append(_event(
            session_id=session_id,
            turn_id=turn_id,
            event_type="session_end",
            cwd=cwd,
            evidence_refs=[rel],
            ts=events[-1].get("ts"),
            extras={"raw_path": rel},
        ))
    return events


def normalize_hook_logs(repo: Path) -> List[dict]:
    events: List[dict] = []
    root = ai_traces.raw_dir(repo, ADAPTER, "hooks")
    seen_pre_tool: set[str] = set()
    pending_tool_files: Dict[str, List[str]] = {}
    pending_permissions: List[dict] = []
    for log in sorted(root.glob("hooks-*.jsonl")):
        rel = ai_traces.repo_rel(repo, log)
        for idx, row in enumerate(_load_jsonl(log)):
            payload = row.get("payload")
            if not isinstance(payload, dict):
                payload = {}
            hook_name = str(row.get("hook_event_name") or row.get("event_name") or "")
            session_id = str(payload.get("session_id") or row.get("session_id") or log.stem)
            turn_id = str(payload.get("turn_id") or payload.get("request_id") or "hook")
            tool_name = _first_str(payload, "tool_name", "tool")
            tool_use_id = _first_str(payload, "tool_use_id", "call_id", "request_id")
            cwd = str(payload.get("cwd") or payload.get("working_dir") or "")
            command = _extract_command(payload)
            files = _extract_files(payload)
            event_type = _hook_event_type(hook_name)

            if event_type == "tool_start" and tool_use_id:
                seen_pre_tool.add(tool_use_id)
                if files:
                    pending_tool_files[tool_use_id] = files
            approval = _approval_outcome(payload, event_type)
            event = _event(
                session_id=session_id,
                turn_id=turn_id,
                event_type=event_type,
                cwd=cwd,
                evidence_refs=[f"{rel}:{idx + 1}"],
                ts=str(row.get("ts") or row.get("captured_at") or payload.get("timestamp") or ""),
                tool_name=tool_name,
                tool_use_id=tool_use_id,
                command=command,
                exit_code=_extract_exit_code(payload),
                text=_first_str(payload, "prompt", "user_prompt", "message", "content"),
                files_touched=files or None,
                approval_outcome=approval,
                extras={"hook_event_name": hook_name, "raw_payload": payload},
            )
            if event_type == "approval_request":
                pending_permissions.append(event)
            elif event_type == "tool_result" and tool_use_id:
                if not event.get("files_touched") and tool_use_id in pending_tool_files:
                    event["files_touched"] = pending_tool_files[tool_use_id]
            events.append(event)

    for event in pending_permissions:
        if event.get("approval_outcome"):
            continue
        tool_use_id = str(event.get("tool_use_id") or "")
        event["approval_outcome"] = (
            "inferred_approved" if tool_use_id and tool_use_id in seen_pre_tool else "unknown"
        )
    return events


def _normalize_known_row(
    *,
    typ: str,
    payload: Dict[str, Any],
    row: Dict[str, Any],
    session_id: str,
    turn_id: str,
    cwd: str,
    evidence_ref: str,
    ts: str,
) -> Optional[dict]:
    role = str(payload.get("role") or row.get("role") or "")
    kind = str(payload.get("type") or row.get("kind") or "")
    text = _extract_text(payload)
    extras = {"raw_type": typ, "raw_payload": payload}

    if typ == "event_msg" and role == "user":
        return _event(session_id=session_id, turn_id=turn_id, event_type="user_prompt",
                      cwd=cwd, evidence_refs=[evidence_ref], ts=ts, text=text, extras=extras)
    if typ == "event_msg" and role in {"assistant", "agent"}:
        return _event(session_id=session_id, turn_id=turn_id, event_type="assistant_message",
                      cwd=cwd, evidence_refs=[evidence_ref], ts=ts, text=text, extras=extras)
    if typ == "event_msg" and kind in {"exec_command_end", "tool_result"}:
        return _event(
            session_id=session_id,
            turn_id=turn_id,
            event_type="tool_result",
            cwd=cwd,
            evidence_refs=[evidence_ref],
            ts=ts,
            tool_name=_first_str(payload, "tool_name", "tool"),
            tool_use_id=_first_str(payload, "call_id", "tool_use_id"),
            command=_extract_command(payload),
            exit_code=_extract_exit_code(payload),
            text=text,
            files_touched=_extract_files(payload) or None,
            extras=extras,
        )

    if typ == "response_item":
        item_type = str(payload.get("type") or payload.get("item_type") or "")
        if item_type in {"message", "assistant_message"}:
            return _event(session_id=session_id, turn_id=turn_id,
                          event_type="assistant_message", cwd=cwd,
                          evidence_refs=[evidence_ref], ts=ts, text=text, extras=extras)
        if item_type in {"function_call", "tool_call", "local_shell_call"}:
            return _event(
                session_id=session_id,
                turn_id=turn_id,
                event_type="tool_start",
                cwd=cwd,
                evidence_refs=[evidence_ref],
                ts=ts,
                tool_name=_first_str(payload, "name", "tool_name", "tool"),
                tool_use_id=_first_str(payload, "call_id", "id", "tool_use_id"),
                command=_extract_command(payload),
                files_touched=_extract_files(payload) or None,
                extras=extras,
            )
        if item_type in {"function_call_output", "tool_result"}:
            return _event(
                session_id=session_id,
                turn_id=turn_id,
                event_type="tool_result",
                cwd=cwd,
                evidence_refs=[evidence_ref],
                ts=ts,
                tool_name=_first_str(payload, "name", "tool_name", "tool"),
                tool_use_id=_first_str(payload, "call_id", "id", "tool_use_id"),
                exit_code=_extract_exit_code(payload),
                text=text,
                files_touched=_extract_files(payload) or None,
                extras=extras,
            )

    if text:
        return _event(session_id=session_id, turn_id=turn_id, event_type="assistant_message",
                      cwd=cwd, evidence_refs=[evidence_ref], ts=ts, text=text, extras=extras)
    return None


def _event(**kwargs: Any) -> dict:
    return ai_traces.make_event(adapter_name=ADAPTER, **kwargs)


def _load_jsonl(path: Path) -> List[dict]:
    return ai_traces.load_jsonl(path)


def _timestamp(row: Dict[str, Any], payload: Dict[str, Any]) -> str:
    return str(row.get("ts") or row.get("timestamp") or payload.get("timestamp") or "")


def _extract_text(payload: Dict[str, Any]) -> Optional[str]:
    for key in ("text", "message", "content", "output"):
        value = payload.get(key)
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            parts: List[str] = []
            for item in value:
                if isinstance(item, dict):
                    t = item.get("text") or item.get("content")
                    if isinstance(t, str):
                        parts.append(t)
                elif isinstance(item, str):
                    parts.append(item)
            if parts:
                return "\n".join(parts)
    return None


def _extract_command(payload: Dict[str, Any]) -> Optional[str]:
    for key in ("command", "cmd"):
        value = payload.get(key)
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return " ".join(str(v) for v in value)
    args = payload.get("arguments")
    if isinstance(args, dict):
        value = args.get("command") or args.get("cmd")
        if isinstance(value, str):
            return value
    tool_input = payload.get("tool_input")
    if isinstance(tool_input, dict):
        value = tool_input.get("command") or tool_input.get("cmd") or tool_input.get("patch")
        if isinstance(value, str):
            return value
    return None


def _extract_files(payload: Dict[str, Any]) -> List[str]:
    files: List[str] = []
    for key in ("files_touched", "files", "paths"):
        value = payload.get(key)
        if isinstance(value, list):
            files.extend(str(v) for v in value if isinstance(v, (str, Path)))
        elif isinstance(value, str):
            files.append(value)
    for text_key in ("patch", "input", "content", "text"):
        value = payload.get(text_key)
        if not isinstance(value, str):
            continue
        for line in value.splitlines():
            m = _PATCH_FILE_RE.match(line.strip())
            if m:
                files.append(m.group(1).strip())
    for nested_key in ("arguments", "tool_input"):
        nested = payload.get(nested_key)
        if not isinstance(nested, dict):
            continue
        for text_key in ("patch", "command", "cmd", "input", "content", "text"):
            value = nested.get(text_key)
            if not isinstance(value, str):
                continue
            for line in value.splitlines():
                m = _PATCH_FILE_RE.match(line.strip())
                if m:
                    files.append(m.group(1).strip())
    return sorted(set(files))


def _extract_exit_code(payload: Dict[str, Any]) -> Any:
    direct = _first_value(payload, "exit_code", "status_code")
    if direct is not None:
        return direct
    response = payload.get("tool_response")
    if isinstance(response, dict):
        metadata = response.get("metadata")
        if isinstance(metadata, dict) and "exit_code" in metadata:
            return metadata["exit_code"]
    if isinstance(response, str):
        try:
            parsed = json.loads(response)
        except (json.JSONDecodeError, TypeError, ValueError):
            return None
        if isinstance(parsed, dict):
            metadata = parsed.get("metadata")
            if isinstance(metadata, dict) and "exit_code" in metadata:
                return metadata["exit_code"]
    return None


def _hook_event_type(hook_name: str) -> str:
    return {
        "SessionStart": "session_start",
        "UserPromptSubmit": "user_prompt",
        "PreToolUse": "tool_start",
        "PermissionRequest": "approval_request",
        "PostToolUse": "tool_result",
        "Stop": "turn_end",
    }.get(hook_name, f"hook_{hook_name}" if hook_name else "hook_event")


def _approval_outcome(payload: Dict[str, Any], event_type: str) -> Optional[str]:
    if event_type != "approval_request":
        return None
    value = _first_str(payload, "approval_outcome", "outcome", "decision")
    return value


def _first_value(payload: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload:
            return payload[key]
    return None


def _first_str(payload: Dict[str, Any], *keys: str) -> Optional[str]:
    value = _first_value(payload, *keys)
    return value if isinstance(value, str) else None
