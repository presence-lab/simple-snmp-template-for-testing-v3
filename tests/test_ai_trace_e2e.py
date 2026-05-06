"""Manual-style E2E coverage for AI traces, snapshots, and attribution.

This test builds a disposable student repo, copies the real capture stack into
it, invokes the repo-local Codex hook scripts as subprocesses, and verifies the
observable artifacts an instructor would inspect by hand.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent


def _run(repo: Path, args: list[str], *, env: dict[str, str], input_text: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        cwd=repo,
        env=env,
        input=input_text,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    ).stdout.strip()


def _copy_runtime_stack(repo: Path) -> None:
    shutil.copy2(ROOT / ".gitignore", repo / ".gitignore")

    tests_dir = repo / "tests"
    tests_dir.mkdir(exist_ok=True)
    shutil.copy2(ROOT / "tests" / "__init__.py", tests_dir / "__init__.py")
    shutil.copytree(ROOT / "tests" / "_capture", tests_dir / "_capture")
    shutil.copy2(ROOT / "tests" / "conftest.py", tests_dir / "conftest.py")

    codex_dir = repo / ".codex"
    codex_dir.mkdir(exist_ok=True)
    shutil.copy2(ROOT / ".codex" / "config.toml", codex_dir / "config.toml")
    shutil.copytree(ROOT / ".codex" / "hooks", codex_dir / "hooks")

    tools_dir = repo / "tools"
    tools_dir.mkdir(exist_ok=True)
    shutil.copytree(ROOT / "tools" / "attribution", tools_dir / "attribution")


def _init_student_repo(tmp_path: Path) -> tuple[Path, Path, dict[str, str]]:
    repo = tmp_path / "work"
    bare = tmp_path / "remote.git"
    codex_home = tmp_path / "codex-home"

    subprocess.run(["git", "init", "--bare", "-q", str(bare)], check=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "config", "user.email", "e2e@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "E2E Tester"], cwd=repo, check=True)
    subprocess.run(["git", "remote", "add", "origin", str(bare)], cwd=repo, check=True)

    (repo / "src").mkdir()
    (repo / "tests").mkdir()
    (repo / "project-template-config.json").write_text(
        json.dumps({"distribution_mode": "student", "capture_enabled": True}),
        encoding="utf-8",
    )
    _copy_runtime_stack(repo)
    (codex_home / "sessions").mkdir(parents=True)

    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True)
    subprocess.run(["git", "push", "-u", "origin", "HEAD:main", "-q"], cwd=repo, check=True)

    env = {**os.environ, "PYTHONPATH": str(repo), "CODEX_HOME": str(codex_home)}
    env.pop("CAPTURE_DISABLED", None)
    return repo, bare, env


def _hook(repo: Path, env: dict[str, str], script: str, payload: dict) -> subprocess.CompletedProcess:
    return _run(
        repo,
        [sys.executable, str(repo / ".codex" / "hooks" / script)],
        env=env,
        input_text=json.dumps(payload),
    )


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _wait_for_remote_ref(bare: Path, ref: str, timeout_s: float = 10.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        result = subprocess.run(
            ["git", "-C", str(bare), "rev-parse", "--verify", ref],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return True
        time.sleep(0.2)
    return False


@pytest.mark.timeout(240)
def test_ai_trace_codex_hooks_snapshots_and_attribution_e2e(tmp_path):
    repo, bare, env = _init_student_repo(tmp_path)
    head_before = _git(repo, "rev-parse", "HEAD")

    (repo / "src" / "e2e_demo.py").write_text(
        'def student_line():\n    return "student"\n',
        encoding="utf-8",
    )
    baseline = _run(
        repo,
        [sys.executable, "-m", "tests._capture", "snapshot", "--reason", "student baseline"],
        env=env,
    )
    assert baseline.returncode == 0, baseline.stdout + baseline.stderr
    assert _git(repo, "rev-parse", "HEAD") == head_before

    sid = "manual-codex-e2e"
    common = {"session_id": sid, "turn_id": "turn-1", "cwd": str(repo)}
    assert _hook(repo, env, "user_prompt_submit.py", {
        **common,
        "prompt": "Add an AI-authored helper to src/e2e_demo.py",
    }).returncode == 0
    assert _hook(repo, env, "permission_request.py", {
        **common,
        "request_id": "tool-1",
        "tool_name": "apply_patch",
        "command": "edit src/e2e_demo.py",
    }).returncode == 0
    assert _hook(repo, env, "pre_tool_use.py", {
        **common,
        "tool_use_id": "tool-1",
        "tool_name": "apply_patch",
        "command": "edit src/e2e_demo.py",
        "files_touched": ["src/e2e_demo.py"],
    }).returncode == 0

    with (repo / "src" / "e2e_demo.py").open("a", encoding="utf-8", newline="\n") as f:
        f.write('\n\ndef ai_line():\n    return "ai"\n')
    (repo / ".codex" / "auth.json").write_text('{"token": "do-not-commit"}\n', encoding="utf-8")

    assert _hook(repo, env, "post_tool_use.py", {
        **common,
        "tool_use_id": "tool-1",
        "tool_name": "apply_patch",
        "exit_code": 0,
        "files_touched": ["src/e2e_demo.py"],
    }).returncode == 0
    stop = _hook(repo, env, "stop.py", common)
    assert stop.returncode == 0, stop.stdout + stop.stderr
    assert json.loads(stop.stdout) == {"continue": True}

    raw_hook_log = repo / ".ai-traces" / "codex" / "raw" / "hooks" / f"hooks-{sid}.jsonl"
    assert raw_hook_log.exists()
    raw_events = _load_jsonl(raw_hook_log)
    assert [e["hook_event_name"] for e in raw_events] == [
        "UserPromptSubmit",
        "PermissionRequest",
        "PreToolUse",
        "PostToolUse",
        "Stop",
    ]

    stream = repo / ".ai-traces" / "interaction-stream.jsonl"
    assert stream.exists()
    events = _load_jsonl(stream)
    event_types = {e["event_type"] for e in events}
    assert {"user_prompt", "approval_request", "tool_start", "tool_result", "turn_end"} <= event_types
    approval = next(e for e in events if e["event_type"] == "approval_request")
    assert approval["approval_outcome"] == "inferred_approved"
    completed_tool = next(e for e in events if e["event_type"] == "tool_result")
    assert completed_tool["files_touched"] == ["src/e2e_demo.py"]

    body = _git(repo, "log", "-1", "--format=%B", "refs/auto-track/snapshots")
    assert "trigger: codex_stop" in body
    assert "agent_name: codex" in body
    assert f"agent_session_id: {sid}" in body
    assert "artifact_hashes:" in body

    tree_files = set(_git(repo, "ls-tree", "-r", "--name-only", "refs/auto-track/snapshots").splitlines())
    assert ".ai-traces/interaction-stream.jsonl" in tree_files
    assert f".ai-traces/codex/raw/hooks/hooks-{sid}.jsonl" in tree_files
    assert ".codex/hooks/stop.py" in tree_files
    assert ".codex/auth.json" not in tree_files
    assert not any("__pycache__" in path for path in tree_files)
    assert _wait_for_remote_ref(bare, "refs/auto-track/snapshots")

    attribution = _run(
        repo,
        [sys.executable, "-m", "tools.attribution", "build", ".", "--output", "attribution-ai.json"],
        env=env,
    )
    assert attribution.returncode == 0, attribution.stdout + attribution.stderr
    data = json.loads((repo / "attribution-ai.json").read_text(encoding="utf-8"))
    by_text = {row["text"]: row for row in data["files"]["src/e2e_demo.py"]}
    assert by_text["def student_line():"]["label"] == "student_authored"
    assert by_text["def ai_line():"]["label"] == "ai_authored"

    (repo / "src" / "e2e_demo.py").write_text(
        (repo / "src" / "e2e_demo.py").read_text(encoding="utf-8").replace(
            'return "ai"', 'return "student changed ai"'
        ),
        encoding="utf-8",
    )
    student_edit = _run(
        repo,
        [sys.executable, "-m", "tests._capture", "snapshot", "--reason", "student modifies ai line"],
        env=env,
    )
    assert student_edit.returncode == 0, student_edit.stdout + student_edit.stderr

    attribution = _run(
        repo,
        [sys.executable, "-m", "tools.attribution", "build", ".", "--output", "attribution-student-edit.json"],
        env=env,
    )
    assert attribution.returncode == 0, attribution.stdout + attribution.stderr
    data = json.loads((repo / "attribution-student-edit.json").read_text(encoding="utf-8"))
    by_text = {row["text"]: row for row in data["files"]["src/e2e_demo.py"]}
    assert by_text['    return "student changed ai"']["label"] == "student_modified_ai"
