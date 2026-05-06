"""Tests for the force_paths + unstage_after Protocol extension (Task 2.5.10).

Three layers:
    1. Protocol acceptance — adapters that DON'T implement the new methods
       still satisfy isinstance(AgentAdapter) and registry filtering, with
       defaults of [] for both.
    2. snapshot_to_auto_track honors force_paths via `git add -Af`,
       defeating .gitignore. unstage_after removes paths via
       `git rm --cached --ignore-unmatch`, even when the path is missing.
    3. Orchestrator collects union(force_paths) + union(unstage_after)
       from registered adapters and passes them through.
"""
import subprocess
from pathlib import Path
from typing import List, Optional

import pytest

from tests._capture import git_ops, orchestrator
from tests._capture.agent_adapters import AgentAdapter, registry
from tests._capture.agent_adapters.base import AdapterMetadata, IngestResult
from tests._capture.agent_adapters.codex import CodexAdapter


# --- Layer 1: Protocol contract ------------------------------------------

class _MinimalAdapter:
    """Adapter that implements ONLY the original Protocol — no
    force_paths / unstage_after overrides."""
    name = "minimal"
    transcripts_dir = ".minimal-transcripts"

    def is_present(self) -> bool:
        return True

    def ingest(self, repo, since) -> IngestResult:
        return IngestResult(adapter_name=self.name)

    def detect_active_session(self) -> Optional[AdapterMetadata]:
        return None

    def stage_paths(self) -> List[str]:
        return [self.transcripts_dir]


def test_minimal_adapter_still_satisfies_protocol():
    """An adapter that doesn't override the new methods is still valid."""
    assert isinstance(_MinimalAdapter(), AgentAdapter)


def test_codex_adapter_force_paths_include_trace_roots():
    """Codex force-stages trace/config paths and excludes auth.json."""
    adapter = CodexAdapter()
    assert adapter.force_paths() == [".ai-traces", ".codex"]
    assert adapter.unstage_after() == [".codex/auth.json", ".codex/hooks/__pycache__"]


# --- Layer 2: snapshot_to_auto_track honors force_paths + unstage_after ---

@pytest.fixture
def repo_with_remote(tmp_path):
    """Tmp repo + bare remote so push paths work."""
    bare = tmp_path / "remote.git"
    work = tmp_path / "work"
    subprocess.run(["git", "init", "--bare", "-q", str(bare)], check=True)
    subprocess.run(["git", "init", "-q", str(work)], check=True)
    subprocess.run(["git", "-C", str(work), "config", "user.email", "t@e.com"], check=True)
    subprocess.run(["git", "-C", str(work), "config", "user.name", "T"], check=True)
    subprocess.run(["git", "-C", str(work), "remote", "add", "origin", str(bare)], check=True)
    (work / "src").mkdir()
    (work / "src" / ".gitkeep").write_text("")
    subprocess.run(["git", "-C", str(work), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(work), "commit", "-q", "-m", "init"], check=True)
    return work


def _list_tree(repo: Path, sha: str) -> set:
    out = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", sha],
        cwd=repo, capture_output=True, text=True, check=True).stdout
    return set(out.splitlines())


def test_snapshot_to_auto_track_honors_force_paths_against_gitignore(
        repo_with_remote):
    """A path in .gitignore lands in the snapshot tree when force_paths
    declares it."""
    repo = repo_with_remote
    (repo / ".codex").mkdir()
    (repo / ".codex" / "telemetry.jsonl").write_text("event\n")
    (repo / ".gitignore").write_text(".codex/\n")
    (repo / "src" / "work.py").write_text("x = 1\n")

    head_ref, head_sha = git_ops.current_head_info(repo)
    sha = git_ops.snapshot_to_auto_track(
        repo, "test-run: forced\n\nsession_id: f1\ncapture_version: 3\n",
        ["src", ".codex"], head_ref, head_sha,
        force_paths=[".codex"],
    )
    assert sha is not None
    files = _list_tree(repo, sha)
    assert "src/work.py" in files
    assert ".codex/telemetry.jsonl" in files


def test_snapshot_to_auto_track_unstage_after_removes_blacklisted_path(
        repo_with_remote):
    """A path declared in unstage_after is removed from the snapshot tree
    even when it would otherwise have been staged."""
    repo = repo_with_remote
    (repo / ".codex").mkdir()
    (repo / ".codex" / "config.toml").write_text('model = "x"\n')
    (repo / ".codex" / "auth.json").write_text('{"token": "secret"}\n')

    head_ref, head_sha = git_ops.current_head_info(repo)
    sha = git_ops.snapshot_to_auto_track(
        repo, "test-run: unstage\n\nsession_id: u1\ncapture_version: 3\n",
        [".codex"], head_ref, head_sha,
        force_paths=[".codex"],  # force-stage everything in .codex
        unstage_after=[".codex/auth.json"],  # then yank auth.json
    )
    assert sha is not None
    files = _list_tree(repo, sha)
    assert ".codex/config.toml" in files
    assert ".codex/auth.json" not in files


def test_snapshot_to_auto_track_unstage_after_silent_on_missing(repo_with_remote):
    """unstage_after must NOT abort the snapshot when the path is absent."""
    repo = repo_with_remote
    (repo / "src" / "work.py").write_text("x = 1\n")
    head_ref, head_sha = git_ops.current_head_info(repo)
    sha = git_ops.snapshot_to_auto_track(
        repo, "test-run: m1\n\nsession_id: m1\ncapture_version: 3\n",
        ["src"], head_ref, head_sha,
        unstage_after=["does-not-exist", ".codex/auth.json"],
    )
    assert sha is not None


def test_snapshot_to_auto_track_default_kwargs_unchanged(repo_with_remote):
    """Backward compat: omitting the new kwargs still works (watchdog uses
    this signature)."""
    repo = repo_with_remote
    (repo / "src" / "work.py").write_text("x = 1\n")
    head_ref, head_sha = git_ops.current_head_info(repo)
    sha = git_ops.snapshot_to_auto_track(
        repo, "test-run: c\n\nsession_id: c\ncapture_version: 3\n",
        ["src"], head_ref, head_sha,
    )
    assert sha is not None


# --- Layer 3: orchestrator threads through --------------------------------

class _ForceUnstageAdapter:
    """Adapter that exercises the new Protocol methods."""
    name = "force"
    transcripts_dir = ".force-transcripts"

    def is_present(self) -> bool:
        return True

    def detect_active_session(self) -> Optional[AdapterMetadata]:
        return None

    def stage_paths(self) -> List[str]:
        return [self.transcripts_dir, ".force"]

    def force_paths(self) -> List[str]:
        return [".force"]

    def unstage_after(self) -> List[str]:
        return [".force/secret.txt"]

    def ingest(self, repo: Path, since) -> IngestResult:
        d = repo / ".force"
        d.mkdir(exist_ok=True)
        (d / "kept.txt").write_text("kept\n")
        (d / "secret.txt").write_text("oops\n")
        return IngestResult(adapter_name=self.name)


def test_orchestrator_threads_force_paths_and_unstage_after(
        tmp_git_repo_with_capture, monkeypatch):
    repo = tmp_git_repo_with_capture
    # The .force directory is gitignored — only force-stage saves it.
    (repo / ".gitignore").write_text(".force/\n")
    monkeypatch.setattr(registry, "_REGISTERED", (_ForceUnstageAdapter,))

    sha = orchestrator.take_snapshot(
        repo, trigger="pytest", pytest_session_id="force-1")
    assert sha is not None
    files = _list_tree(repo, sha)
    assert ".force/kept.txt" in files
    assert ".force/secret.txt" not in files


def test_orchestrator_unions_paths_across_adapters(
        tmp_git_repo_with_capture, monkeypatch):
    """When two adapters declare overlapping force_paths, the union is
    de-duplicated and passed in sorted order (deterministic)."""
    captured = {}

    real_snapshot = git_ops.snapshot_to_auto_track

    def spy(repo, msg, paths, head_ref, head_sha,
            *, force_paths=None, unstage_after=None):
        captured["force_paths"] = list(force_paths or [])
        captured["unstage_after"] = list(unstage_after or [])
        return real_snapshot(repo, msg, paths, head_ref, head_sha,
                             force_paths=force_paths,
                             unstage_after=unstage_after)

    monkeypatch.setattr("tests._capture.git_ops.snapshot_to_auto_track", spy)

    class A:
        name = "a"
        transcripts_dir = ".a"
        def is_present(self): return True
        def detect_active_session(self): return None
        def stage_paths(self): return [".a"]
        def force_paths(self): return [".shared", ".a-only"]
        def unstage_after(self): return [".shared/x"]
        def ingest(self, repo, since): return IngestResult(adapter_name=self.name)

    class B:
        name = "b"
        transcripts_dir = ".b"
        def is_present(self): return True
        def detect_active_session(self): return None
        def stage_paths(self): return [".b"]
        def force_paths(self): return [".shared", ".b-only"]
        def unstage_after(self): return [".shared/x", ".b-only/y"]
        def ingest(self, repo, since): return IngestResult(adapter_name=self.name)

    monkeypatch.setattr(registry, "_REGISTERED", (A, B))
    orchestrator.take_snapshot(
        tmp_git_repo_with_capture, trigger="pytest",
        pytest_session_id="union-1")
    assert captured["force_paths"] == sorted({".shared", ".a-only", ".b-only"})
    assert captured["unstage_after"] == sorted({".shared/x", ".b-only/y"})


def test_orchestrator_force_paths_default_to_empty(
        tmp_git_repo_with_capture, monkeypatch):
    """Adapter without force_paths/unstage_after methods → empty lists
    threaded through, no crash."""
    captured = {}

    def spy(repo, msg, paths, head_ref, head_sha,
            *, force_paths=None, unstage_after=None):
        captured["force_paths"] = list(force_paths or [])
        captured["unstage_after"] = list(unstage_after or [])
        return "deadbeef" * 5

    monkeypatch.setattr("tests._capture.git_ops.snapshot_to_auto_track", spy)
    monkeypatch.setattr(registry, "_REGISTERED", (_MinimalAdapter,))
    orchestrator.take_snapshot(
        tmp_git_repo_with_capture, trigger="manual",
        pytest_session_id=None)
    assert captured["force_paths"] == []
    assert captured["unstage_after"] == []
