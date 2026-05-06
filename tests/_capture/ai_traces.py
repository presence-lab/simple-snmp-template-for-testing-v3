"""Shared helpers for vendor-neutral AI interaction traces.

The capture layer treats ``.ai-traces`` as the canonical on-repo evidence
directory. Concrete adapters keep native artifacts under their own raw
subdirectory, write normalized events under ``normalized/``, and contribute
to the merged interaction stream.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, List, Mapping, Optional


AI_TRACES_DIR = ".ai-traces"
INTERACTION_STREAM = f"{AI_TRACES_DIR}/interaction-stream.jsonl"
ATTESTATION_FILE = f"{AI_TRACES_DIR}/external-attestation.txt"


def adapter_dir(repo: Path, adapter_name: str) -> Path:
    return repo / AI_TRACES_DIR / adapter_name


def raw_dir(repo: Path, adapter_name: str, kind: str) -> Path:
    return adapter_dir(repo, adapter_name) / "raw" / kind


def normalized_dir(repo: Path, adapter_name: str) -> Path:
    return adapter_dir(repo, adapter_name) / "normalized"


def repo_rel(repo: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo.resolve()).as_posix()
    except (OSError, ValueError):
        return path.as_posix()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stable_event_id(*parts: Any) -> str:
    raw = json.dumps(parts, sort_keys=True, ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def append_jsonl(path: Path, row: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def load_jsonl(path: Path) -> List[dict]:
    rows: List[dict] = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                if isinstance(obj, dict):
                    rows.append(obj)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return []
    return rows


def ensure_attestation(repo: Path) -> Path:
    path = repo / ATTESTATION_FILE
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "External AI tool disclosures\n"
            "\n"
            "Use this file to disclose web/cloud AI interactions that are not "
            "captured automatically by the local adapter hooks.\n",
            encoding="utf-8",
            newline="\n",
        )
    return path


def collect_hashes(repo: Path) -> List[dict]:
    root = repo / AI_TRACES_DIR
    if not root.exists():
        return []
    out: List[dict] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        try:
            out.append({"path": repo_rel(repo, path), "sha256": sha256_file(path)})
        except OSError:
            continue
    return out


def rebuild_interaction_stream(repo: Path) -> Path:
    root = repo / AI_TRACES_DIR
    rows: List[dict] = []
    if root.exists():
        for path in sorted(root.glob("*/normalized/*.jsonl")):
            if path.as_posix().endswith("/interaction-stream.jsonl"):
                continue
            rows.extend(load_jsonl(path))
    rows.sort(key=lambda e: (str(e.get("ts", "")), str(e.get("event_id", ""))))
    out = repo / INTERACTION_STREAM
    write_jsonl(out, rows)
    return out


def now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_event(
    *,
    adapter_name: str,
    session_id: str,
    turn_id: str,
    event_type: str,
    cwd: str,
    evidence_refs: List[str],
    ts: Optional[str] = None,
    **fields: Any,
) -> dict:
    core = {
        "adapter_name": adapter_name,
        "session_id": session_id or "unknown",
        "turn_id": turn_id or "unknown",
        "ts": ts or now_ts(),
        "event_type": event_type,
        "cwd": cwd or "",
        "evidence_refs": evidence_refs,
    }
    clean = {k: v for k, v in fields.items() if v is not None}
    core["event_id"] = stable_event_id(core, clean)
    core.update(clean)
    core.setdefault("extras", {})
    return core
