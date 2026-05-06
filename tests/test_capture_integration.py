"""End-to-end test of the capture orchestration against a tmp git repo.

This test does NOT invoke pytest recursively — it exercises the capture
functions directly with a mock session object. Recursive pytest invocation
is covered by test_capture_conftest.py.
"""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests._capture import capture, metadata


@pytest.fixture
def tmp_git_repo(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@e.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, check=True)
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / ".gitkeep").write_text("")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)
    return tmp_path


@pytest.fixture
def tmp_git_repo_with_capture(tmp_git_repo):
    """tmp_git_repo plus project-template-config.json enabling capture."""
    (tmp_git_repo / "project-template-config.json").write_text(
        '{"capture_enabled": true}'
    )
    return tmp_git_repo


def test_session_start_then_finish_produces_one_auto_track_snapshot(tmp_git_repo_with_capture):
    repo = tmp_git_repo_with_capture
    head_before = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo,
        capture_output=True, text=True, check=True).stdout.strip()
    ctx = capture.session_start(repo)
    assert ctx is not None
    (repo / "src" / "work.py").write_text("x = 1\n")
    ctx.record_test(outcome="passed", bundle=1, points=10)
    ctx.record_test(outcome="failed", bundle=2, points=15)
    capture.session_finish(repo, ctx, status="completed")

    head_after = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo,
        capture_output=True, text=True, check=True).stdout.strip()
    assert head_after == head_before, "v3 must not commit to HEAD"

    tip = subprocess.run(
        ["git", "rev-parse", "--verify", "refs/auto-track/snapshots"],
        cwd=repo, capture_output=True, text=True)
    assert tip.returncode == 0, "snapshot ref not created"
    body = subprocess.run(
        ["git", "log", "-1", "--format=%B", "refs/auto-track/snapshots"],
        cwd=repo, capture_output=True, text=True, check=True).stdout
    assert f"session_id: {ctx.session_id}" in body
    assert "capture_version: 3" in body
    assert "current_head_ref:" in body
    assert "trigger: pytest" in body
    assert "agent_name: none" in body


def test_session_skipped_when_capture_disabled(tmp_git_repo):
    # No config file at all — capture should be off.
    ctx = capture.session_start(tmp_git_repo)
    assert ctx is None

    # Config present but capture_enabled false.
    (tmp_git_repo / "project-template-config.json").write_text(
        '{"capture_enabled": false}'
    )
    assert capture.session_start(tmp_git_repo) is None

    # Malformed config — treat as disabled (fail-safe).
    (tmp_git_repo / "project-template-config.json").write_text("not json")
    assert capture.session_start(tmp_git_repo) is None


def test_session_finish_ingests_codex_rollouts(
    tmp_git_repo_with_capture, tmp_path, monkeypatch
):
    """session_finish should copy matching Codex rollouts into .ai-traces/.

    Uses the REAL Codex rollout schema (type: session_meta, payload.cwd) and
    places the fixture under sessions/YYYY/MM/DD/ to exercise the recursive
    scan.
    """
    tmp_git_repo = tmp_git_repo_with_capture

    # Point CODEX_HOME at an isolated tmp dir and seed a realistic rollout.
    codex_home = tmp_path / "codex_home"
    rollout_dir = codex_home / "sessions" / "2026" / "04" / "22"
    rollout_dir.mkdir(parents=True)
    rollout_path = rollout_dir / "rollout-xyz.jsonl"
    session_meta = {
        "timestamp": "2026-04-22T12:00:00Z",
        "type": "session_meta",
        "payload": {
            "id": "xyz",
            "cwd": str(tmp_git_repo),
            "originator": "codex_exec",
            "cli_version": "0.119.0-alpha.28",
            "source": "exec",
        },
    }
    rollout_path.write_text(json.dumps(session_meta) + "\n", encoding="utf-8")
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    ctx = capture.session_start(tmp_git_repo)
    assert ctx is not None
    # Note: we do NOT need to forward-date the rollout mtime. The ingest
    # matches by cwd alone (plus idempotency) — the realistic workflow has
    # the student using Codex BEFORE running pytest, so the rollout mtime
    # is necessarily < session_started_at. Capturing it is the whole point.
    ctx.record_test(outcome="passed", bundle=1, points=10)
    capture.session_finish(tmp_git_repo, ctx, status="completed")

    copied = tmp_git_repo / ".ai-traces" / "codex" / "raw" / "rollouts" / "rollout-xyz.jsonl"
    assert copied.exists(), (
        f"Expected rollout to be copied to {copied}, but it was not. "
        f"Contents of .ai-traces/: "
        f"{list((tmp_git_repo / '.ai-traces').rglob('*')) if (tmp_git_repo / '.ai-traces').exists() else 'missing'}"
    )
    assert (tmp_git_repo / ".ai-traces" / "interaction-stream.jsonl").exists()


def test_session_finish_snapshots_during_merge(tmp_git_repo_with_capture):
    repo = tmp_git_repo_with_capture
    # Fake a merge in progress without actually merging
    head_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo,
        capture_output=True, text=True, check=True).stdout.strip()
    (repo / ".git" / "MERGE_HEAD").write_text(head_sha + "\n")
    ctx = capture.session_start(repo)
    assert ctx is not None, "session_start MUST not skip during merge in v2"
    capture.session_finish(repo, ctx, status="completed")
    body = subprocess.run(
        ["git", "log", "-1", "--format=%B", "refs/auto-track/snapshots"],
        cwd=repo, capture_output=True, text=True, check=True).stdout
    assert "git_state: merging" in body


def test_session_finish_snapshots_during_rebase(tmp_git_repo_with_capture):
    repo = tmp_git_repo_with_capture
    (repo / ".git" / "rebase-merge").mkdir()
    ctx = capture.session_start(repo)
    assert ctx is not None
    capture.session_finish(repo, ctx, status="completed")
    body = subprocess.run(
        ["git", "log", "-1", "--format=%B", "refs/auto-track/snapshots"],
        cwd=repo, capture_output=True, text=True, check=True).stdout
    assert "git_state: rebasing" in body


def test_outer_and_inner_session_dedup_to_one_snapshot(tmp_git_repo_with_capture):
    """Simulate run_tests.py's outer session_start + inner conftest session_start."""
    repo = tmp_git_repo_with_capture
    outer_ctx = capture.session_start(repo)
    inner_ctx = capture.session_start(
        repo, session_id=outer_ctx.session_id, started_at=outer_ctx.started_at)
    assert inner_ctx.session_id == outer_ctx.session_id
    capture.session_finish(repo, inner_ctx, status="completed")
    capture.session_finish(repo, outer_ctx, status="completed")
    # Count snapshots — filter to auto-track snapshot commits only.
    # `git log refs/auto-track/snapshots` walks parents, so the HEAD commit
    # (the snapshot's second parent) shows up too. Filter by subject prefix.
    log = subprocess.run(
        ["git", "log", "--format=%H %s", "refs/auto-track/snapshots"],
        cwd=repo, capture_output=True, text=True, check=True).stdout
    snapshot_lines = [ln for ln in log.strip().splitlines()
                      if "test-run:" in ln]
    assert len(snapshot_lines) == 1, (
        f"dedupe failed: multiple snapshots\n{log}")


def test_session_start_commits_orphan_from_prior_run(tmp_git_repo_with_capture):
    tmp_git_repo = tmp_git_repo_with_capture
    # Simulate a prior orphaned session
    from tests._capture import state
    import json, time
    sid = state.start_session(tmp_git_repo, hard_deadline_seconds=1)
    marker = tmp_git_repo / ".test-run-state" / f"{sid}.json"
    data = json.loads(marker.read_text())
    data["started_at"] = time.time() - 120
    marker.write_text(json.dumps(data))

    capture.session_start(tmp_git_repo)

    # Under v3, orphan recovery records to refs/auto-track/snapshots, not HEAD.
    log = subprocess.run(
        ["git", "log", "--pretty=%s", "-3", "refs/auto-track/snapshots"],
        cwd=tmp_git_repo, capture_output=True, text=True, check=True,
    ).stdout
    assert "recovered orphaned session from prior run" in log


# ---------------------------------------------------------------------------
# Phase 7: end-to-end pytest subprocess invocation against a fake remote.
#
# These tests spawn a real `python -m pytest` inside a tmp working repo with a
# bare file:// remote. They verify the full capture pipeline (conftest hooks
# -> capture.session_start/finish -> orchestrator.take_snapshot ->
# snapshot_to_auto_track -> push_auto_track_background) creates the snapshot
# ref locally AND propagates it to the remote.
# ---------------------------------------------------------------------------


@pytest.fixture
def repo_with_remote(tmp_path):
    """Per spec §9.3.1: tmp working repo + bare remote at file://."""
    bare = tmp_path / "remote.git"
    work = tmp_path / "work"
    subprocess.run(["git", "init", "--bare", "-q", str(bare)], check=True)
    subprocess.run(["git", "init", "-q", str(work)], check=True)
    subprocess.run(
        ["git", "-C", str(work), "config", "user.email", "t@e.com"], check=True)
    subprocess.run(
        ["git", "-C", str(work), "config", "user.name", "T"], check=True)
    subprocess.run(
        ["git", "-C", str(work), "remote", "add", "origin", str(bare)],
        check=True)
    (work / "src").mkdir()
    (work / "src" / "x.py").write_text("# placeholder\n")
    (work / "tests").mkdir()
    (work / "tests" / "test_x.py").write_text("def test_passes(): assert True\n")
    (work / "project-template-config.json").write_text(
        '{"distribution_mode": "student", "capture_enabled": true}\n')
    subprocess.run(["git", "-C", str(work), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(work), "commit", "-q", "-m", "init"], check=True)
    return work, bare


def _setup_work_repo(work: Path) -> None:
    """Copy the capture harness + conftest + pyproject.toml into the work repo.

    The inner pytest subprocess needs:
    - tests/__init__.py (so `from tests._capture import capture` resolves)
    - tests/_capture/ package (the capture pipeline modules)
    - tests/conftest.py (the pytest_sessionstart/finish hooks)
    - pyproject.toml at repo root (so pytest discovers tests + applies
      timeout/marker config). Without pyproject.toml, the inner pytest may
      either find no tests or fail with strict-marker errors.

    Idempotent: safe to call repeatedly across multiple `_run_pytest_in`
    invocations within the same test (re-copies conftest.py and pyproject.toml
    to overwrite any modifications, leaves _capture in place if present).
    """
    tests_dir = Path(__file__).resolve().parent
    src_capture = tests_dir / "_capture"
    dst_capture = work / "tests" / "_capture"
    if not dst_capture.exists():
        shutil.copytree(src_capture, dst_capture)
    src_init = tests_dir / "__init__.py"
    if src_init.exists():
        shutil.copy2(src_init, work / "tests" / "__init__.py")
    shutil.copy2(tests_dir / "conftest.py", work / "tests" / "conftest.py")
    src_pyproject = tests_dir.parent / "pyproject.toml"
    shutil.copy2(src_pyproject, work / "pyproject.toml")


def _run_pytest_in(work: Path) -> subprocess.CompletedProcess:
    """Invoke pytest as a subprocess inside the work repo.

    Uses 120s timeout for the inner process. The single test inside is a
    no-op assert; anything beyond a few seconds means the watchdog or push
    machinery is hung.
    """
    return subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_x.py", "-q"],
        cwd=work, capture_output=True, text=True, timeout=120,
    )


def _wait_for_remote_ref(bare: Path, ref: str, timeout_s: float = 10.0) -> bool:
    """Poll the bare remote until `ref` resolves or timeout expires."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        result = subprocess.run(
            ["git", "-C", str(bare), "rev-parse", "--verify", ref],
            capture_output=True, text=True)
        if result.returncode == 0:
            return True
        time.sleep(0.2)
    return False


@pytest.mark.timeout(180)
def test_full_pytest_invocation_pushes_to_remote(repo_with_remote):
    work, bare = repo_with_remote
    _setup_work_repo(work)

    result = _run_pytest_in(work)
    assert result.returncode == 0, result.stdout + result.stderr

    # Verify ref exists locally.
    local = subprocess.run(
        ["git", "-C", str(work), "rev-parse", "--verify",
         "refs/auto-track/snapshots"],
        capture_output=True, text=True)
    assert local.returncode == 0, (
        f"local snapshot ref missing\nstdout={result.stdout}\n"
        f"stderr={result.stderr}")

    # Verify the background push propagated to the bare remote.
    assert _wait_for_remote_ref(bare, "refs/auto-track/snapshots"), (
        "background push did not propagate to bare remote within 10s")


# ---------------------------------------------------------------------------
# Phase 7.2: dual-parent chain assertions across multiple snapshots.
#
# These tests build on Task 7.1's harness. Each test runs pytest as a
# subprocess in the work repo multiple times, mutating the working tree
# between runs (so tree-SHA dedupe doesn't collapse snapshots), then walks
# the resulting auto-track ref via `git rev-list --parents` to verify:
#
#   - parents[0] is always the snapshot itself (rev-list output convention)
#   - parents[1] is the first parent (= prior auto-track tip), and
#   - parents[2], when present, is the second parent (= current_head_ref).
#
# `git rev-list --parents -n 1 <sha>` outputs:
#   <sha> <parent1> [<parent2>]
# space-separated on one line.
# ---------------------------------------------------------------------------


def _read_auto_track_tip(work: Path) -> str:
    """Resolve refs/auto-track/snapshots in `work` and return the SHA."""
    return subprocess.run(
        ["git", "-C", str(work), "rev-parse", "--verify",
         "refs/auto-track/snapshots"],
        capture_output=True, text=True, check=True).stdout.strip()


def _read_parents(work: Path, sha: str) -> list[str]:
    """Return [<sha>, <parent1>, ...] from `git rev-list --parents -n 1`."""
    out = subprocess.run(
        ["git", "-C", str(work), "rev-list", "--parents", "-n", "1", sha],
        capture_output=True, text=True, check=True).stdout.strip()
    return out.split()


def _mutate_tree(work: Path, tag: str) -> None:
    """Touch a unique file so the next snapshot has a distinct tree SHA.

    Without this, the orchestrator's tree-SHA dedupe would skip the second
    snapshot (same staged tree as the first). The capture pipeline stages
    tracked + allowlisted files; writing under src/ guarantees inclusion.
    """
    (work / "src" / f"mutation_{tag}.py").write_text(f"# {tag}\n")


@pytest.mark.timeout(240)
def test_second_snapshot_first_parent_is_first_snapshot(repo_with_remote):
    """Two consecutive pytest runs: snap2's first parent is snap1's SHA."""
    work, _bare = repo_with_remote
    _setup_work_repo(work)

    # Run #1
    r1 = _run_pytest_in(work)
    assert r1.returncode == 0, r1.stdout + r1.stderr
    snap1 = _read_auto_track_tip(work)

    # Mutate tree so snap2 has a different tree SHA than snap1.
    _mutate_tree(work, "first")

    # Run #2
    r2 = _run_pytest_in(work)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    snap2 = _read_auto_track_tip(work)

    assert snap2 != snap1, (
        f"snap2 == snap1 ({snap1}); tree-SHA dedupe likely collapsed runs")

    parents = _read_parents(work, snap2)
    # rev-list --parents output: <snap2> <parent1> [<parent2>]
    assert parents[0] == snap2
    assert len(parents) >= 2, (
        f"snap2 has no first parent: {parents!r}")
    assert parents[1] == snap1, (
        f"snap2's first parent {parents[1]} != snap1 {snap1}")


@pytest.mark.timeout(240)
def test_feature_branch_snapshot_second_parents_feature_head(repo_with_remote):
    """Run pytest on main, then create a feature branch + commit + run pytest;
    snap2's second parent is the feature-branch HEAD."""
    work, _bare = repo_with_remote
    _setup_work_repo(work)

    # Run #1 on main
    r1 = _run_pytest_in(work)
    assert r1.returncode == 0, r1.stdout + r1.stderr
    snap1 = _read_auto_track_tip(work)

    # Switch to a feature branch and commit a tree change.
    subprocess.run(
        ["git", "-C", str(work), "checkout", "-b", "feature/x", "-q"],
        check=True)
    (work / "src" / "feature.py").write_text("# feature\n")
    subprocess.run(["git", "-C", str(work), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(work), "commit", "-q", "-m", "feature work"],
        check=True)
    feature_head = subprocess.run(
        ["git", "-C", str(work), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True).stdout.strip()

    # Run #2 on the feature branch
    r2 = _run_pytest_in(work)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    snap2 = _read_auto_track_tip(work)
    assert snap2 != snap1

    parents = _read_parents(work, snap2)
    # Expect: <snap2> <parent1=snap1> <parent2=feature_head>
    assert parents[0] == snap2
    assert len(parents) == 3, (
        f"snap2 should have both parents: {parents!r}")
    assert parents[1] == snap1, (
        f"snap2's first parent {parents[1]} != snap1 {snap1}")
    assert parents[2] == feature_head, (
        f"snap2's second parent {parents[2]} != feature HEAD {feature_head}")


@pytest.mark.timeout(360)
def test_dual_parent_chain_sane_after_three_runs(repo_with_remote):
    """Three runs produce three snapshots with a valid first-parent chain."""
    work, _bare = repo_with_remote
    _setup_work_repo(work)

    snaps: list[str] = []
    for i in range(3):
        if i > 0:
            _mutate_tree(work, f"run{i}")
        result = _run_pytest_in(work)
        assert result.returncode == 0, (
            f"run {i} failed: {result.stdout}\n{result.stderr}")
        snaps.append(_read_auto_track_tip(work))

    # Each snapshot is distinct.
    assert len(set(snaps)) == 3, f"snapshots collapsed: {snaps!r}"

    # snap2's first parent is snap1; snap3's first parent is snap2.
    p2 = _read_parents(work, snaps[1])
    p3 = _read_parents(work, snaps[2])
    assert p2[1] == snaps[0], f"snap2.first_parent {p2[1]} != snap1 {snaps[0]}"
    assert p3[1] == snaps[1], f"snap3.first_parent {p3[1]} != snap2 {snaps[1]}"


def test_pytest_sessionstart_self_installs_capture_triggers(tmp_git_repo_with_capture):
    """After running pytest in a capture-enabled repo, sitecustomize is in
    the active venv (when one is active) and core.hooksPath is set."""
    repo = tmp_git_repo_with_capture
    # Drop a trivial test the sub-pytest can collect.
    (repo / "tests" / "test_trivial.py").write_text("def test_ok(): pass\n")
    # Mirror the production conftest path: the sub-pytest needs the same
    # capture infrastructure to fire pytest_sessionstart.
    project_root = Path(__file__).resolve().parent.parent
    for relpath in [
        "tests/__init__.py",
        "tests/conftest.py",
        "tests/_capture",
    ]:
        src = project_root / relpath
        dst = repo / relpath
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    # Run the inner pytest from the inner repo's directory.
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo) + os.pathsep + env.get("PYTHONPATH", "")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_trivial.py", "-q"],
        cwd=repo, env=env, capture_output=True, text=True, timeout=60,
    )
    # Sub-pytest should pass.
    assert result.returncode == 0, f"inner pytest failed: {result.stdout}\n{result.stderr}"
    # core.hooksPath should be configured by ensure_installed.
    cfg = subprocess.run(
        ["git", "config", "--local", "core.hooksPath"],
        cwd=repo, capture_output=True, text=True,
    )
    assert cfg.stdout.strip() == ".githooks", \
        f"core.hooksPath not set; got {cfg.stdout!r}"
