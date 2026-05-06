"""Tests for repo-local Codex hook entrypoints."""
import importlib.util
import json
import subprocess
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
HOOK_DIR = ROOT / ".codex" / "hooks"


def _load_hook_module(name: str):
    path = HOOK_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"codex_hook_{name}", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_codex_config_declares_six_hooks():
    data = tomllib.loads((ROOT / ".codex" / "config.toml").read_text(encoding="utf-8"))
    hooks = data["hooks"]
    assert set(hooks) == {
        "SessionStart",
        "UserPromptSubmit",
        "PreToolUse",
        "PermissionRequest",
        "PostToolUse",
        "Stop",
    }


def test_hook_common_appends_event_to_ai_traces(tmp_path, monkeypatch):
    common = _load_hook_module("_common")
    monkeypatch.setattr(common, "project_repo_root", lambda: tmp_path)

    common.append_hook_event("UserPromptSubmit", {
        "session_id": "sess-1",
        "cwd": str(tmp_path),
        "prompt": "hello",
    })

    log = tmp_path / ".ai-traces" / "codex" / "raw" / "hooks" / "hooks-sess-1.jsonl"
    row = json.loads(log.read_text(encoding="utf-8").strip())
    assert row["hook_event_name"] == "UserPromptSubmit"
    assert row["payload"]["prompt"] == "hello"


def test_hook_common_ignores_payloads_outside_project(tmp_path, monkeypatch):
    common = _load_hook_module("_common")
    monkeypatch.setattr(common, "project_repo_root", lambda: tmp_path / "repo")
    (tmp_path / "repo").mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()

    common.append_hook_event("UserPromptSubmit", {
        "session_id": "sess-1",
        "cwd": str(outside),
        "prompt": "ignore",
    })

    assert not (tmp_path / "repo" / ".ai-traces").exists()


def test_stop_hook_creates_codex_stop_snapshot_metadata(monkeypatch):
    sys.path.insert(0, str(HOOK_DIR))
    try:
        stop = _load_hook_module("stop")
    finally:
        sys.path.remove(str(HOOK_DIR))

    captured = {}

    def fake_take_snapshot(repo, **kwargs):
        captured["repo"] = repo
        captured.update(kwargs)
        return "abc123"

    monkeypatch.setattr("tests._capture.orchestrator.take_snapshot", fake_take_snapshot)
    stop._snapshot({"session_id": "sess-stop", "cwd": str(ROOT), "turn_id": "turn-9"})

    assert captured["trigger"] == "codex_stop"
    assert captured["pytest_session_id"] is None
    assert captured["adapter_metadata"].adapter_name == "codex"
    assert captured["adapter_metadata"].agent_session_id == "sess-stop"


def test_hook_entrypoint_runs_via_runpy_without_import_failure():
    payload = json.dumps({"session_id": "outside", "cwd": str(ROOT.parent)})
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import runpy; runpy.run_path('.codex/hooks/session_start.py', run_name='__main__')",
        ],
        cwd=ROOT,
        input=payload,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr


def test_hook_safe_main_never_blocks_on_callback_failure(tmp_path, monkeypatch):
    common = _load_hook_module("_common")
    monkeypatch.setattr(common, "project_repo_root", lambda: tmp_path)
    monkeypatch.setattr(common, "read_payload", lambda: {"session_id": "s"})

    def boom(payload):
        raise RuntimeError("boom")

    assert common.safe_main("Stop", boom) == 0
