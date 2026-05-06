"""Tests for the attribution report CLI."""
import json
import os
import subprocess
import sys
from pathlib import Path

from tests._capture import ai_traces, git_ops
from tests._capture import metadata
from tools.attribution import cli


def _init_repo(repo):
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Teacher"], cwd=repo, check=True)
    (repo / "src").mkdir()
    (repo / "tests").mkdir()
    (repo / "src" / ".gitkeep").write_text("", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True)


def _snapshot(repo, *, trigger="pytest", agent_name="none", agent_session_id="none"):
    head_ref, head_sha = git_ops.current_head_info(repo)
    msg = metadata.format_commit_message(
        session_id=f"{trigger}-{agent_session_id}",
        status="completed",
        result=metadata.TestResult(total=1, passed=1),
        diff_added=0,
        diff_removed=0,
        files_changed=[],
        hostname_hash="h",
        current_head_ref=head_ref,
        current_head_sha=head_sha or "unborn",
        trigger=trigger,
        agent_name=agent_name,
        agent_session_id=agent_session_id,
    )
    sha = git_ops.snapshot_to_auto_track(
        repo,
        msg,
        ["src", "tests", ".ai-traces"],
        head_ref,
        head_sha,
        force_paths=[".ai-traces"],
    )
    assert sha is not None
    return sha


def test_attribution_labels_student_ai_and_student_modified_ai(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    (repo / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")
    _snapshot(repo)

    ai_traces.write_jsonl(repo / ai_traces.INTERACTION_STREAM, [
        {
            "event_id": "e1",
            "adapter_name": "codex",
            "session_id": "sess-ai",
            "turn_id": "t1",
            "ts": "2026-05-02T10:00:00Z",
            "event_type": "tool_result",
            "cwd": str(repo),
            "files_touched": ["src/app.py"],
            "evidence_refs": [".ai-traces/codex/raw/rollouts/r.jsonl:4"],
            "extras": {},
        },
        {
            "event_id": "e2",
            "adapter_name": "codex",
            "session_id": "sess-ai",
            "turn_id": "t1",
            "ts": "2026-05-02T10:00:01Z",
            "event_type": "approval_request",
            "cwd": str(repo),
            "files_touched": ["src/app.py"],
            "approval_outcome": "approved",
            "evidence_refs": [".ai-traces/codex/raw/hooks/hooks-sess-ai.jsonl:1"],
            "extras": {},
        },
    ])
    (repo / "src" / "app.py").write_text("x = 1\ny = 2\n", encoding="utf-8")
    _snapshot(repo, trigger="codex_stop", agent_name="codex", agent_session_id="sess-ai")

    (repo / "src" / "app.py").write_text("x = 1\ny = 3\n", encoding="utf-8")
    _snapshot(repo)

    data = cli.build_attribution(repo)
    lines = data["files"]["src/app.py"]
    assert lines[0]["label"] == "student_authored"
    assert lines[1]["label"] == "student_modified_ai"
    assert lines[1]["adapter_name"] is None
    assert lines[1]["confidence"] == 0.8


def test_attribution_labels_ai_modified_student(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    (repo / "src" / "app.py").write_text("name = 'student'\n", encoding="utf-8")
    _snapshot(repo)
    ai_traces.write_jsonl(repo / ai_traces.INTERACTION_STREAM, [
        {
            "event_id": "e1",
            "adapter_name": "codex",
            "session_id": "sess-ai",
            "turn_id": "t1",
            "ts": "2026-05-02T10:00:00Z",
            "event_type": "tool_result",
            "cwd": str(repo),
            "files_touched": ["src/app.py"],
            "evidence_refs": ["raw:1"],
            "extras": {},
        }
    ])
    (repo / "src" / "app.py").write_text("name = 'ai'\n", encoding="utf-8")
    _snapshot(repo, trigger="codex_stop", agent_name="codex", agent_session_id="sess-ai")

    row = cli.build_attribution(repo)["files"]["src/app.py"][0]
    assert row["label"] == "ai_modified_student"
    assert row["adapter_name"] == "codex"
    assert row["session_id"] == "sess-ai"


def test_attribution_uses_legacy_codex_transcripts_when_stream_missing(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    (repo / ".codex-transcripts").mkdir()
    (repo / ".codex-transcripts" / "rollout-old.jsonl").write_text(
        json.dumps({"type": "session_meta", "payload": {"id": "old", "cwd": str(repo)}})
        + "\n"
        + json.dumps({"type": "event_msg", "payload": {"role": "user", "text": "help"}})
        + "\n",
        encoding="utf-8",
    )
    (repo / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")
    _snapshot(repo, trigger="codex_stop", agent_name="codex", agent_session_id="old")

    data = cli.build_attribution(repo)
    assert "codex" in data["adapters"]
    assert data["files"]["src/app.py"][0]["label"] == "ai_authored"


def test_attribution_cli_writes_json_and_annotations(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    (repo / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")
    _snapshot(repo)

    assert cli.main(["build", str(repo), "--output", "out.json"]) == 0
    assert (repo / "out.json").exists()
    assert cli.main(["annotate", str(repo), "--output", "ann"]) == 0
    assert (repo / "ann" / "src" / "app.py.txt").exists()


def test_attribution_module_invocation_from_repo_root(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    (repo / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")
    _snapshot(repo)

    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parent.parent)}
    result = subprocess.run(
        [sys.executable, "-m", "tools.attribution", "build", str(repo)],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert (repo / "attribution.json").exists()
