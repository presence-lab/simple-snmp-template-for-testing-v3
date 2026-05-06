"""Tests for the shared AI trace helpers and Codex normalizer."""
import json

from tests._capture import ai_traces
from tests._capture.agent_adapters import codex_normalize


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_codex_rollout_normalizes_prompts_tools_and_file_edits(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    rollout = repo / ".ai-traces" / "codex" / "raw" / "rollouts" / "rollout-one.jsonl"
    _write_jsonl(rollout, [
        {
            "timestamp": "2026-05-02T10:00:00Z",
            "type": "session_meta",
            "payload": {"id": "sess-one", "cwd": str(repo)},
        },
        {
            "timestamp": "2026-05-02T10:00:01Z",
            "type": "turn_context",
            "payload": {"turn_id": "turn-1", "cwd": str(repo)},
        },
        {
            "timestamp": "2026-05-02T10:00:02Z",
            "type": "event_msg",
            "payload": {"role": "user", "text": "write helper"},
        },
        {
            "timestamp": "2026-05-02T10:00:03Z",
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "call_id": "call-1",
                "name": "apply_patch",
                "patch": "*** Update File: src/helper.py\n",
            },
        },
        {
            "timestamp": "2026-05-02T10:00:04Z",
            "type": "response_item",
            "payload": {
                "type": "function_call_output",
                "call_id": "call-1",
                "output": "ok",
            },
        },
    ])

    built = codex_normalize.normalize_all(repo)
    assert built == [repo / ".ai-traces" / "codex" / "normalized" / "sess-one.jsonl"]
    events = ai_traces.load_jsonl(repo / ".ai-traces" / "interaction-stream.jsonl")
    event_types = [e["event_type"] for e in events]
    assert "user_prompt" in event_types
    assert "tool_result" in event_types
    tool = next(e for e in events if e["event_type"] == "tool_result")
    assert tool["files_touched"] == ["src/helper.py"]
    assert tool["adapter_name"] == "codex"
    assert tool["session_id"] == "sess-one"
    assert tool["evidence_refs"]


def test_codex_hook_logs_normalize_approvals_and_inferred_approval(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    hooks = repo / ".ai-traces" / "codex" / "raw" / "hooks" / "hooks-sess.jsonl"
    _write_jsonl(hooks, [
        {
            "hook_event_name": "PermissionRequest",
            "payload": {
                "session_id": "sess",
                "request_id": "tool-1",
                "cwd": str(repo),
                "tool_name": "shell_command",
            },
        },
        {
            "hook_event_name": "PreToolUse",
            "captured_at": "2026-05-02T10:00:01Z",
            "payload": {
                "session_id": "sess",
                "tool_use_id": "tool-1",
                "cwd": str(repo),
                "tool_name": "shell_command",
                "tool_input": {
                    "command": "*** Begin Patch\n*** Update File: src/app.py\n+print('x')\n*** End Patch\n",
                },
            },
        },
        {
            "hook_event_name": "PostToolUse",
            "captured_at": "2026-05-02T10:00:02Z",
            "payload": {
                "session_id": "sess",
                "tool_use_id": "tool-1",
                "cwd": str(repo),
                "tool_name": "shell_command",
                "tool_response": json.dumps({
                    "output": "Success. Updated the following files:\nM src/app.py\n",
                    "metadata": {"exit_code": 0},
                }),
            },
        },
    ])

    codex_normalize.normalize_all(repo)
    events = ai_traces.load_jsonl(repo / ".ai-traces" / "interaction-stream.jsonl")
    approval = next(e for e in events if e["event_type"] == "approval_request")
    assert approval["approval_outcome"] == "inferred_approved"
    result = next(e for e in events if e["event_type"] == "tool_result")
    assert result["exit_code"] == 0
    assert result["files_touched"] == ["src/app.py"]


def test_legacy_codex_transcripts_remain_readable(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    legacy = repo / ".codex-transcripts" / "rollout-old.jsonl"
    _write_jsonl(legacy, [
        {
            "type": "session_meta",
            "payload": {"id": "legacy-session", "cwd": str(repo)},
        },
        {
            "type": "event_msg",
            "payload": {"role": "user", "text": "old prompt"},
        },
    ])

    events = codex_normalize.normalize_legacy_codex_transcripts(repo)
    assert [e["event_type"] for e in events][:2] == ["session_start", "user_prompt"]
    assert events[0]["session_id"] == "legacy-session"


def test_collect_hashes_includes_raw_normalized_and_stream(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    path = repo / ".ai-traces" / "codex" / "normalized" / "s.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text("{}\n", encoding="utf-8")
    (repo / ".ai-traces" / "interaction-stream.jsonl").write_text("{}\n", encoding="utf-8")

    hashes = ai_traces.collect_hashes(repo)
    assert {h["path"] for h in hashes} == {
        ".ai-traces/codex/normalized/s.jsonl",
        ".ai-traces/interaction-stream.jsonl",
    }
