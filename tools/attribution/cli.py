"""Build line-level provenance from auto-track snapshots and AI traces."""
from __future__ import annotations

import argparse
import difflib
import json
import subprocess
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from tests._capture import ai_traces
from tests._capture.agent_adapters import codex_normalize

AUTO_TRACK_REF = "refs/auto-track/snapshots"
OUTPUT_JSON = "attribution.json"
ANNOTATED_DIR = "attribution-annotated"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.attribution")
    sub = parser.add_subparsers(dest="cmd", required=True)
    build = sub.add_parser("build")
    build.add_argument("repo")
    build.add_argument("--adapter", default=None)
    build.add_argument("--output", default=OUTPUT_JSON)
    annotate = sub.add_parser("annotate")
    annotate.add_argument("repo")
    annotate.add_argument("--adapter", default=None)
    annotate.add_argument("--output", default=ANNOTATED_DIR)
    args = parser.parse_args(argv)

    repo = Path(args.repo).resolve()
    if args.cmd == "build":
        data = build_attribution(repo, adapter=args.adapter)
        out = repo / args.output
        out.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        print(out)
        return 0
    data = build_attribution(repo, adapter=args.adapter)
    out_dir = repo / args.output
    write_annotated(data, out_dir)
    print(out_dir)
    return 0


def build_attribution(repo: Path, adapter: Optional[str] = None) -> Dict[str, object]:
    commits = _snapshot_commits(repo)
    events = _load_events(repo, adapter=adapter)
    warnings: List[str] = []
    if not commits:
        warnings.append("no auto-track snapshots found")
        return _empty_output(repo, events, warnings)
    meta_by_commit = {sha: _commit_meta(repo, sha) for sha in commits}
    files = _code_files(repo, commits[-1])
    out_files = {}
    for rel in files:
        out_files[rel] = _attribute_file(repo, rel, commits, meta_by_commit, events)
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "repo": str(repo),
        "adapters": _adapter_summary(events),
        "files": out_files,
        "warnings": warnings,
    }


def write_annotated(data: Dict[str, object], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    files = data.get("files", {})
    if not isinstance(files, dict):
        return
    for rel, lines in files.items():
        if not isinstance(lines, list):
            continue
        dest = out_dir / f"{rel}.txt"
        dest.parent.mkdir(parents=True, exist_ok=True)
        rendered = []
        for row in lines:
            if not isinstance(row, dict):
                continue
            rendered.append(
                f"{row.get('line_no', 0):4} "
                f"{str(row.get('label', 'unknown')):22} "
                f"{float(row.get('confidence', 0.0)):.2f} | "
                f"{row.get('text', '')}"
            )
        dest.write_text("\n".join(rendered) + "\n", encoding="utf-8")


def _empty_output(repo: Path, events: List[Dict[str, object]], warnings: List[str]):
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "repo": str(repo),
        "adapters": _adapter_summary(events),
        "files": {},
        "warnings": warnings,
    }


def _snapshot_commits(repo: Path) -> List[str]:
    result = _git(repo, ["rev-list", "--reverse", "--first-parent", AUTO_TRACK_REF])
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _commit_meta(repo: Path, sha: str) -> Dict[str, str]:
    body = _git(repo, ["log", "-1", "--format=%B", sha]).stdout
    meta = {"_sha": sha, "_subject": body.splitlines()[0] if body else ""}
    for line in body.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip()
    return meta


def _code_files(repo: Path, commit: str) -> List[str]:
    result = _git(repo, ["ls-tree", "-r", "--name-only", commit])
    if result.returncode != 0:
        return []
    files = []
    for rel in result.stdout.splitlines():
        if rel.startswith("src/"):
            files.append(rel)
        elif rel.startswith("tests/") and not (
            rel.startswith("tests/_capture/") or rel == "tests/conftest.py"
        ):
            files.append(rel)
    return sorted(files)


def _attribute_file(
    repo: Path,
    rel: str,
    commits: List[str],
    meta_by_commit: Dict[str, Dict[str, str]],
    events: List[Dict[str, object]],
) -> List[Dict[str, object]]:
    prev_lines: List[str] = []
    origins: List[Dict[str, object]] = []
    for sha in commits:
        lines = _file_lines(repo, sha, rel)
        interval = _interval_evidence(meta_by_commit[sha], rel, events)
        if not prev_lines and lines:
            origins = [_origin_for_insert(line, interval) for line in lines]
            prev_lines = lines
            continue
        matcher = difflib.SequenceMatcher(a=prev_lines, b=lines, autojunk=False)
        next_origins: List[Dict[str, object]] = []
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                next_origins.extend(origins[i1:i2])
            elif tag == "insert":
                next_origins.extend(
                    _origin_for_insert(line, interval) for line in lines[j1:j2]
                )
            elif tag == "replace":
                prior = origins[i1:i2]
                next_origins.extend(
                    _origin_for_replace(line, interval, prior)
                    for line in lines[j1:j2]
                )
            elif tag == "delete":
                continue
        prev_lines = lines
        origins = next_origins
    return [
        {
            "line_no": idx + 1,
            "text": line,
            **_public_origin(origin),
        }
        for idx, (line, origin) in enumerate(zip(prev_lines, origins))
    ]


def _origin_for_insert(line: str, interval: Dict[str, object]) -> Dict[str, object]:
    label = "ai_authored" if interval["ai_interval"] else "student_authored"
    if not line.strip():
        label = "unknown"
    return _origin(label, interval, ancestry_score=0.0)


def _origin_for_replace(
    line: str,
    interval: Dict[str, object],
    prior: List[Dict[str, object]],
) -> Dict[str, object]:
    if not line.strip():
        return _origin("unknown", interval, ancestry_score=0.0)
    prior_labels = {str(p.get("label")) for p in prior}
    prior_ai = any("ai" in label for label in prior_labels)
    prior_student = any("student" in label for label in prior_labels)
    if interval["ai_interval"] and prior_student:
        label = "ai_modified_student"
    elif not interval["ai_interval"] and prior_ai:
        label = "student_modified_ai"
    elif interval["ai_interval"]:
        label = "ai_authored"
    elif prior_ai and prior_student:
        label = "mixed"
    else:
        label = "student_authored"
    return _origin(label, interval, ancestry_score=1.0)


def _origin(
    label: str,
    interval: Dict[str, object],
    *,
    ancestry_score: float,
) -> Dict[str, object]:
    direct = bool(interval["direct_ai_file_evidence"])
    ai_interval = bool(interval["ai_interval"])
    if label in {"ai_authored", "ai_modified_student"}:
        confidence = 0.9 if direct else 0.65
    elif label in {"student_authored", "student_modified_ai"}:
        confidence = 0.8
    elif label == "mixed":
        confidence = 0.55
    else:
        confidence = 0.3
    return {
        "label": label,
        "confidence": confidence,
        "ai_edit_score": 1.0 if direct else (0.7 if ai_interval else 0.0),
        "student_interval_score": 0.0 if ai_interval else 1.0,
        "ancestry_score": ancestry_score,
        "prompt_response_influence_score": 0.2 if interval["ai_discussion_evidence"] else 0.0,
        "adapter_name": interval.get("adapter_name"),
        "session_id": interval.get("session_id"),
        "evidence_refs": interval.get("evidence_refs", []),
    }


def _public_origin(origin: Dict[str, object]) -> Dict[str, object]:
    keys = [
        "label", "confidence", "ai_edit_score", "student_interval_score",
        "ancestry_score", "prompt_response_influence_score", "adapter_name",
        "session_id", "evidence_refs",
    ]
    return {key: origin.get(key) for key in keys}


def _interval_evidence(
    meta: Dict[str, str],
    rel: str,
    events: List[Dict[str, object]],
) -> Dict[str, object]:
    agent_name = meta.get("agent_name", "none")
    session_id = meta.get("agent_session_id", "none")
    trigger = meta.get("trigger", "")
    candidate_events = [
        e for e in events
        if (not session_id or session_id == "none" or e.get("session_id") == session_id)
        and (agent_name == "none" or e.get("adapter_name") == agent_name)
    ]
    direct_events = [
        e for e in candidate_events
        if rel in [str(p) for p in (e.get("files_touched") or [])]
        and e.get("event_type") in {"tool_call", "tool_result", "file_edit"}
    ]
    discussion_events = [
        e for e in candidate_events
        if e.get("event_type") in {"user_prompt", "assistant_message"}
    ]
    ai_interval = agent_name != "none" or trigger.endswith("_stop")
    return {
        "ai_interval": ai_interval,
        "direct_ai_file_evidence": bool(direct_events),
        "ai_discussion_evidence": bool(discussion_events),
        "adapter_name": agent_name if agent_name != "none" else None,
        "session_id": session_id if session_id != "none" else None,
        "evidence_refs": _evidence_refs(direct_events or discussion_events),
    }


def _evidence_refs(events: Iterable[Dict[str, object]]) -> List[str]:
    refs: List[str] = []
    for event in events:
        raw = event.get("evidence_refs")
        if isinstance(raw, list):
            refs.extend(str(r) for r in raw)
    return refs[:5]


def _file_lines(repo: Path, commit: str, rel: str) -> List[str]:
    result = _git(repo, ["show", f"{commit}:{rel}"])
    if result.returncode != 0:
        return []
    return result.stdout.splitlines()


def _load_events(repo: Path, adapter: Optional[str] = None) -> List[Dict[str, object]]:
    events = ai_traces.load_jsonl(repo / ai_traces.INTERACTION_STREAM)
    if not events:
        events = codex_normalize.normalize_legacy_codex_transcripts(repo)
    if adapter:
        events = [e for e in events if e.get("adapter_name") == adapter]
    return events


def _adapter_summary(events: List[Dict[str, object]]) -> Dict[str, Dict[str, object]]:
    out: Dict[str, Dict[str, object]] = {}
    for event in events:
        name = str(event.get("adapter_name") or "unknown")
        row = out.setdefault(name, {"events": 0, "sessions": set()})
        row["events"] += 1
        row["sessions"].add(str(event.get("session_id") or "unknown"))
    return {
        name: {"events": row["events"], "sessions": sorted(row["sessions"])}
        for name, row in sorted(out.items())
    }


def _git(repo: Path, args: List[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
    )
