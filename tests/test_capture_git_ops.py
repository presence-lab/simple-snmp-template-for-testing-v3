"""Tests for _capture.git_ops. These run in a throwaway git repo per test."""
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests._capture import git_ops


@pytest.fixture
def tmp_git_repo(tmp_path, monkeypatch):
    """Create a tmp git repo with src/ and tests/ directories."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / ".gitkeep").write_text("")
    (tmp_path / "tests" / ".gitkeep").write_text("")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)
    return tmp_path


@pytest.fixture
def tmp_git_repo_with_bare_remote(tmp_path):
    """tmp_git_repo plus a file:// remote bare repo at origin."""
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
    return work, bare


def test_current_head_info_clean_branch(tmp_git_repo):
    ref, sha = git_ops.current_head_info(tmp_git_repo)
    assert ref in ("main", "master")  # depends on git init.defaultBranch
    assert sha is not None
    assert len(sha) == 40

def test_current_head_info_detached_head(tmp_git_repo):
    # Detach HEAD onto the initial commit
    sha_initial = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_git_repo,
        capture_output=True, text=True, check=True).stdout.strip()
    subprocess.run(["git", "checkout", "--detach", sha_initial],
                   cwd=tmp_git_repo, check=True, capture_output=True)
    ref, sha = git_ops.current_head_info(tmp_git_repo)
    assert ref == "detached"
    assert sha == sha_initial

def test_current_head_info_unborn_head(tmp_path):
    # Fresh repo, no commits yet
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    ref, sha = git_ops.current_head_info(tmp_path)
    assert ref in ("main", "master")  # initial branch is set even before first commit
    assert sha is None


def test_detect_git_state_clean(tmp_git_repo):
    assert git_ops.detect_git_state(tmp_git_repo) == "clean"

def test_detect_git_state_merging(tmp_git_repo):
    (tmp_git_repo / ".git" / "MERGE_HEAD").write_text("deadbeef\n")
    assert git_ops.detect_git_state(tmp_git_repo) == "merging"

def test_detect_git_state_rebasing(tmp_git_repo):
    (tmp_git_repo / ".git" / "rebase-merge").mkdir()
    assert git_ops.detect_git_state(tmp_git_repo) == "rebasing"

def test_detect_git_state_rebasing_apply_variant(tmp_git_repo):
    (tmp_git_repo / ".git" / "rebase-apply").mkdir()
    assert git_ops.detect_git_state(tmp_git_repo) == "rebasing"

def test_detect_git_state_cherry_picking(tmp_git_repo):
    (tmp_git_repo / ".git" / "CHERRY_PICK_HEAD").write_text("deadbeef\n")
    assert git_ops.detect_git_state(tmp_git_repo) == "cherry-picking"


def test_read_auto_track_tip_missing(tmp_git_repo):
    assert git_ops.read_auto_track_tip(tmp_git_repo) is None

def test_read_auto_track_tip_returns_sha(tmp_git_repo):
    # Create the ref pointing at the initial commit
    head_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_git_repo,
        capture_output=True, text=True, check=True).stdout.strip()
    subprocess.run(
        ["git", "update-ref", "refs/auto-track/snapshots", head_sha],
        cwd=tmp_git_repo, check=True)
    assert git_ops.read_auto_track_tip(tmp_git_repo) == head_sha


def test_fetch_auto_track_no_remote_ref_returns_none(tmp_git_repo_with_bare_remote):
    work, _ = tmp_git_repo_with_bare_remote
    assert git_ops.fetch_auto_track(work) is None

def test_fetch_auto_track_pulls_remote_ref(tmp_git_repo_with_bare_remote):
    work, bare = tmp_git_repo_with_bare_remote
    # Push a snapshot ref to the bare remote
    head_sha = subprocess.run(
        ["git", "-C", str(work), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True).stdout.strip()
    subprocess.run(
        ["git", "-C", str(work), "update-ref",
         "refs/auto-track/snapshots", head_sha], check=True)
    subprocess.run(
        ["git", "-C", str(work), "push", "origin",
         "refs/auto-track/snapshots:refs/auto-track/snapshots"], check=True)
    # Drop the local ref so fetch is the only way to get it
    subprocess.run(
        ["git", "-C", str(work), "update-ref", "-d",
         "refs/auto-track/snapshots"], check=True)
    fetched = git_ops.fetch_auto_track(work)
    assert fetched == head_sha

def test_fetch_auto_track_pre_delete_clears_stale_mirror(tmp_git_repo_with_bare_remote):
    """If the remote ref disappears, the local mirror MUST be cleared by fetch_auto_track."""
    work, bare = tmp_git_repo_with_bare_remote
    head_sha = subprocess.run(
        ["git", "-C", str(work), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True).stdout.strip()
    # Pre-seed a local origin-tip pointing at HEAD (pretending we previously fetched)
    subprocess.run(
        ["git", "-C", str(work), "update-ref",
         "refs/auto-track/origin-tip", head_sha], check=True)
    # Remote has nothing under refs/auto-track/
    result = git_ops.fetch_auto_track(work)
    assert result is None
    # Local mirror must now be gone
    check = subprocess.run(
        ["git", "-C", str(work), "rev-parse", "--verify",
         "refs/auto-track/origin-tip"],
        capture_output=True, text=True)
    assert check.returncode != 0, "stale local mirror ref must be cleared"


def test_pick_first_parent_neither_ref_exists(tmp_git_repo):
    assert git_ops.pick_first_parent(tmp_git_repo) is None

def test_pick_first_parent_only_local_exists(tmp_git_repo):
    head_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_git_repo,
        capture_output=True, text=True, check=True).stdout.strip()
    subprocess.run(
        ["git", "update-ref", git_ops.AUTO_TRACK_REF, head_sha],
        cwd=tmp_git_repo, check=True)
    assert git_ops.pick_first_parent(tmp_git_repo) == head_sha

def test_pick_first_parent_only_origin_tip_exists(tmp_git_repo):
    head_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_git_repo,
        capture_output=True, text=True, check=True).stdout.strip()
    subprocess.run(
        ["git", "update-ref", git_ops.AUTO_TRACK_ORIGIN_TIP_REF, head_sha],
        cwd=tmp_git_repo, check=True)
    assert git_ops.pick_first_parent(tmp_git_repo) == head_sha

def test_pick_first_parent_local_dominates(tmp_git_repo):
    """Local has commits ahead of origin-tip → local wins."""
    sha_a = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_git_repo,
        capture_output=True, text=True, check=True).stdout.strip()
    # origin-tip points at sha_a
    subprocess.run(
        ["git", "update-ref", git_ops.AUTO_TRACK_ORIGIN_TIP_REF, sha_a],
        cwd=tmp_git_repo, check=True)
    # Local advances past sha_a
    (tmp_git_repo / "src" / "newfile.py").write_text("y = 2\n")
    subprocess.run(["git", "add", "-A"], cwd=tmp_git_repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "advance"],
                   cwd=tmp_git_repo, check=True)
    sha_b = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_git_repo,
        capture_output=True, text=True, check=True).stdout.strip()
    subprocess.run(
        ["git", "update-ref", git_ops.AUTO_TRACK_REF, sha_b],
        cwd=tmp_git_repo, check=True)
    assert git_ops.pick_first_parent(tmp_git_repo) == sha_b

def test_pick_first_parent_origin_dominates(tmp_git_repo):
    """origin-tip has commits ahead of local → origin-tip wins."""
    sha_a = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_git_repo,
        capture_output=True, text=True, check=True).stdout.strip()
    subprocess.run(
        ["git", "update-ref", git_ops.AUTO_TRACK_REF, sha_a],
        cwd=tmp_git_repo, check=True)
    (tmp_git_repo / "src" / "newfile.py").write_text("y = 2\n")
    subprocess.run(["git", "add", "-A"], cwd=tmp_git_repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "advance"],
                   cwd=tmp_git_repo, check=True)
    sha_b = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_git_repo,
        capture_output=True, text=True, check=True).stdout.strip()
    subprocess.run(
        ["git", "update-ref", git_ops.AUTO_TRACK_ORIGIN_TIP_REF, sha_b],
        cwd=tmp_git_repo, check=True)
    assert git_ops.pick_first_parent(tmp_git_repo) == sha_b

def test_pick_first_parent_divergence_picks_local(tmp_git_repo):
    """When neither tip dominates, local wins (push will surface non-FF)."""
    sha_a = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_git_repo,
        capture_output=True, text=True, check=True).stdout.strip()
    # Local advances on one branch
    (tmp_git_repo / "src" / "local.py").write_text("local\n")
    subprocess.run(["git", "add", "-A"], cwd=tmp_git_repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "local"], cwd=tmp_git_repo, check=True)
    sha_local = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_git_repo,
        capture_output=True, text=True, check=True).stdout.strip()
    subprocess.run(
        ["git", "update-ref", git_ops.AUTO_TRACK_REF, sha_local],
        cwd=tmp_git_repo, check=True)
    # Origin tip is on a divergent commit (reset HEAD, make a different commit)
    subprocess.run(["git", "reset", "--hard", "-q", sha_a], cwd=tmp_git_repo, check=True)
    (tmp_git_repo / "src" / "remote.py").write_text("remote\n")
    subprocess.run(["git", "add", "-A"], cwd=tmp_git_repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "remote"], cwd=tmp_git_repo, check=True)
    sha_remote = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_git_repo,
        capture_output=True, text=True, check=True).stdout.strip()
    subprocess.run(
        ["git", "update-ref", git_ops.AUTO_TRACK_ORIGIN_TIP_REF, sha_remote],
        cwd=tmp_git_repo, check=True)
    assert git_ops.pick_first_parent(tmp_git_repo) == sha_local


def test_snapshot_to_auto_track_first_ever_creates_initial_commit(tmp_git_repo):
    head_ref, head_sha = git_ops.current_head_info(tmp_git_repo)
    new_sha = git_ops.snapshot_to_auto_track(
        tmp_git_repo,
        message="test-run: 0/0 passed\n\nsession_id: deadbeef\n",
        snapshot_paths=["src", "tests"],
        head_ref=head_ref,
        head_sha=head_sha,
    )
    assert new_sha is not None
    assert len(new_sha) == 40
    # Ref now exists
    assert git_ops.read_auto_track_tip(tmp_git_repo) == new_sha
    # Snapshot has no first parent (first ever) and head_sha as second parent
    parents = subprocess.run(
        ["git", "rev-list", "--parents", "-n", "1", new_sha],
        cwd=tmp_git_repo, capture_output=True, text=True, check=True
    ).stdout.strip().split()
    assert parents[0] == new_sha  # commit itself
    assert len(parents) == 2  # only second parent (HEAD)
    assert parents[1] == head_sha

def test_snapshot_to_auto_track_dual_parent_chain(tmp_git_repo):
    head_ref, head_sha_initial = git_ops.current_head_info(tmp_git_repo)
    first_snap = git_ops.snapshot_to_auto_track(
        tmp_git_repo, "subj1\n\nbody1", ["src", "tests"], head_ref, head_sha_initial)
    # Make a student commit on main
    (tmp_git_repo / "src" / "more.py").write_text("z = 3\n")
    subprocess.run(["git", "add", "-A"], cwd=tmp_git_repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "student work"], cwd=tmp_git_repo, check=True)
    head_ref2, head_sha2 = git_ops.current_head_info(tmp_git_repo)
    second_snap = git_ops.snapshot_to_auto_track(
        tmp_git_repo, "subj2\n\nbody2", ["src", "tests"], head_ref2, head_sha2)
    # Second snapshot's parents are (first_snap, head_sha2)
    parents = subprocess.run(
        ["git", "rev-list", "--parents", "-n", "1", second_snap],
        cwd=tmp_git_repo, capture_output=True, text=True, check=True
    ).stdout.strip().split()
    assert parents[1] == first_snap
    assert parents[2] == head_sha2

def test_snapshot_does_not_touch_working_tree_or_index_or_head(tmp_git_repo):
    # Snapshot a clean state
    head_ref, head_sha = git_ops.current_head_info(tmp_git_repo)
    status_before = subprocess.run(
        ["git", "status", "--porcelain"], cwd=tmp_git_repo,
        capture_output=True, text=True, check=True).stdout
    git_ops.snapshot_to_auto_track(
        tmp_git_repo, "subj\n\nbody", ["src", "tests"], head_ref, head_sha)
    status_after = subprocess.run(
        ["git", "status", "--porcelain"], cwd=tmp_git_repo,
        capture_output=True, text=True, check=True).stdout
    assert status_before == status_after
    head_after = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_git_repo,
        capture_output=True, text=True, check=True).stdout.strip()
    assert head_after == head_sha

def test_snapshot_skips_missing_allowlist_paths(tmp_git_repo):
    # Note: tmp_git_repo lacks .ai-traces/, .codex/, AGENTS.md, AI_POLICY.md
    head_ref, head_sha = git_ops.current_head_info(tmp_git_repo)
    new_sha = git_ops.snapshot_to_auto_track(
        tmp_git_repo, "subj\n\nbody",
        ["src", "tests", ".ai-traces", ".codex", "AGENTS.md", "AI_POLICY.md"],
        head_ref, head_sha)
    assert new_sha is not None  # missing paths must be filtered out, not crash

def test_snapshot_unborn_head_creates_commit_with_no_parents(tmp_path):
    # Fresh repo with no commits
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@e.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, check=True)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "x.py").write_text("# scratch\n")
    head_ref, head_sha = git_ops.current_head_info(tmp_path)
    assert head_sha is None
    new_sha = git_ops.snapshot_to_auto_track(
        tmp_path, "subj\n\nbody", ["src"], head_ref, head_sha)
    assert new_sha is not None
    parents = subprocess.run(
        ["git", "rev-list", "--parents", "-n", "1", new_sha],
        cwd=tmp_path, capture_output=True, text=True, check=True
    ).stdout.strip().split()
    assert len(parents) == 1  # commit itself, no parents

def test_snapshot_temp_index_uses_pid_suffix_and_is_cleaned_up(tmp_git_repo):
    head_ref, head_sha = git_ops.current_head_info(tmp_git_repo)
    git_ops.snapshot_to_auto_track(
        tmp_git_repo, "subj\n\nbody", ["src", "tests"], head_ref, head_sha)
    # No leftover index files for this PID (or any other)
    leftovers = list((tmp_git_repo / ".git").glob("auto-track.idx.*"))
    assert leftovers == [], f"temp index files leaked: {leftovers}"


def test_diff_stats_against_empty_tree(tmp_git_repo):
    # Build a tree from src/ contents
    (tmp_git_repo / "src" / "x.py").write_text("a = 1\nb = 2\n")
    head_ref, head_sha = git_ops.current_head_info(tmp_git_repo)
    new_sha = git_ops.snapshot_to_auto_track(
        tmp_git_repo, "subj\n\nbody", ["src"], head_ref, head_sha)
    new_tree = subprocess.run(
        ["git", "rev-parse", f"{new_sha}^{{tree}}"],
        cwd=tmp_git_repo, capture_output=True, text=True, check=True).stdout.strip()
    stats = git_ops.diff_stats_trees(tmp_git_repo, prev_tree=git_ops.EMPTY_TREE_SHA, new_tree=new_tree)
    assert stats.added > 0
    assert stats.removed == 0
    assert "src/x.py" in stats.files

def test_diff_stats_reflects_deletion(tmp_git_repo):
    (tmp_git_repo / "src" / "x.py").write_text("a = 1\n")
    head_ref, head_sha = git_ops.current_head_info(tmp_git_repo)
    snap1 = git_ops.snapshot_to_auto_track(
        tmp_git_repo, "s1", ["src"], head_ref, head_sha)
    (tmp_git_repo / "src" / "x.py").unlink()
    snap2 = git_ops.snapshot_to_auto_track(
        tmp_git_repo, "s2", ["src"], head_ref, head_sha)
    tree1 = subprocess.run(
        ["git", "rev-parse", f"{snap1}^{{tree}}"],
        cwd=tmp_git_repo, capture_output=True, text=True, check=True).stdout.strip()
    tree2 = subprocess.run(
        ["git", "rev-parse", f"{snap2}^{{tree}}"],
        cwd=tmp_git_repo, capture_output=True, text=True, check=True).stdout.strip()
    stats = git_ops.diff_stats_trees(tmp_git_repo, prev_tree=tree1, new_tree=tree2)
    assert stats.removed > 0
    assert "src/x.py" in stats.files


def test_snapshot_retries_once_when_ref_advances_underneath(tmp_git_repo, monkeypatch):
    """Simulate: between commit-tree and update-ref, another process advances
    the ref. The first update-ref fails (CAS mismatch); the retry rebuilds
    against the new tip and succeeds."""
    head_ref, head_sha = git_ops.current_head_info(tmp_git_repo)
    # First snapshot establishes the ref
    git_ops.snapshot_to_auto_track(tmp_git_repo, "s1", ["src", "tests"], head_ref, head_sha)
    # Now hook update-ref so the FIRST call sneakily advances the ref
    # (simulating concurrent winner) and reports failure to our caller.
    original_run_git = git_ops.run_git
    call_state = {"calls": 0}
    def hooked(args, **kw):
        if args[:1] == ["update-ref"] and len(args) >= 4 and args[1] == git_ops.AUTO_TRACK_REF:
            call_state["calls"] += 1
            if call_state["calls"] == 1:
                # Advance the ref out from under us before our update would land
                conflicting = original_run_git(
                    ["commit-tree", git_ops.EMPTY_TREE_SHA, "-p",
                     git_ops.read_auto_track_tip(tmp_git_repo), "-m", "race"],
                    cwd=kw["cwd"], timeout=5.0).stdout.strip()
                original_run_git(["update-ref", git_ops.AUTO_TRACK_REF, conflicting],
                                 cwd=kw["cwd"], timeout=5.0)
                # Now return failure for the original call
                return SimpleNamespace(returncode=1, stdout="", stderr="lock")
        return original_run_git(args, **kw)
    monkeypatch.setattr(git_ops, "run_git", hooked)
    new_sha = git_ops.snapshot_to_auto_track(
        tmp_git_repo, "s2", ["src", "tests"], head_ref, head_sha)
    assert new_sha is not None  # retry succeeded
    assert call_state["calls"] >= 2  # at least one retry happened

def test_snapshot_gives_up_after_one_retry(tmp_git_repo, monkeypatch):
    """If both update-ref attempts fail, snapshot returns None (no infinite loop)."""
    head_ref, head_sha = git_ops.current_head_info(tmp_git_repo)
    git_ops.snapshot_to_auto_track(tmp_git_repo, "s1", ["src", "tests"], head_ref, head_sha)
    original_run_git = git_ops.run_git
    call_state = {"calls": 0}
    def hooked(args, **kw):
        if args[:1] == ["update-ref"] and len(args) >= 4 and args[1] == git_ops.AUTO_TRACK_REF:
            call_state["calls"] += 1
            return SimpleNamespace(returncode=1, stdout="", stderr="lock")
        return original_run_git(args, **kw)
    monkeypatch.setattr(git_ops, "run_git", hooked)
    new_sha = git_ops.snapshot_to_auto_track(
        tmp_git_repo, "s2", ["src", "tests"], head_ref, head_sha)
    assert new_sha is None
    assert call_state["calls"] == 2  # exactly two attempts, never more


def test_snapshot_fresh_clone_with_origin_tip_succeeds(tmp_git_repo_with_bare_remote):
    """Multi-machine scenario per spec §11.1.D: local ref is missing but
    origin-tip exists. Earlier impl used `expected_old = first_parent`
    (= origin_tip), which made update-ref fail because the local ref
    did not exist. Regression guard for that bug.
    """
    work, bare = tmp_git_repo_with_bare_remote
    # Machine 1: take a snapshot and push it to the bare remote
    head_ref1, head_sha1 = git_ops.current_head_info(work)
    snap1 = git_ops.snapshot_to_auto_track(
        work, "s1\n\nbody", ["src"], head_ref1, head_sha1)
    assert snap1 is not None
    push = subprocess.run(
        ["git", "-C", str(work), "push", "origin",
         f"{git_ops.AUTO_TRACK_REF}:{git_ops.AUTO_TRACK_REF}"],
        capture_output=True, text=True)
    assert push.returncode == 0, push.stderr
    # Simulate a fresh clone on machine 2: drop the local snapshot ref so
    # only origin has it. (origin-tip mirror ref also gone — fetch will
    # repopulate it.)
    subprocess.run(
        ["git", "-C", str(work), "update-ref", "-d", git_ops.AUTO_TRACK_REF],
        check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(work), "update-ref", "-d",
         git_ops.AUTO_TRACK_ORIGIN_TIP_REF],
        capture_output=True)  # may not exist; ignore failure
    # Machine 2 snapshot: orchestrator-style sequence (fetch first so origin-tip is populated)
    git_ops.fetch_auto_track(work)
    head_ref2, head_sha2 = git_ops.current_head_info(work)
    snap2 = git_ops.snapshot_to_auto_track(
        work, "s2\n\nbody", ["src"], head_ref2, head_sha2)
    assert snap2 is not None, (
        "fresh-clone snapshot must succeed; first parent is origin-tip "
        "but local ref does not yet exist (CAS predicate must use 0-OID)")
    # The new snapshot's first parent should be the origin-tip (= snap1).
    parents = subprocess.run(
        ["git", "-C", str(work), "rev-list", "--parents", "-n", "1", snap2],
        capture_output=True, text=True, check=True).stdout.strip().split()
    assert parents[1] == snap1, (
        f"expected first parent = origin-tip {snap1[:7]}, got {parents[1][:7]}")


def test_push_auto_track_background_is_fire_and_forget(tmp_git_repo_with_bare_remote):
    work, bare = tmp_git_repo_with_bare_remote
    head_ref, head_sha = git_ops.current_head_info(work)
    git_ops.snapshot_to_auto_track(work, "s\n\nbody", ["src"], head_ref, head_sha)
    log_path = work / ".test-runs.log"
    git_ops.push_auto_track_background(work, log_path)
    # Wait briefly for the detached subprocess
    import time
    deadline = time.time() + 10
    while time.time() < deadline:
        result = subprocess.run(
            ["git", "-C", str(bare), "rev-parse", "--verify",
             "refs/auto-track/snapshots"],
            capture_output=True, text=True)
        if result.returncode == 0:
            break
        time.sleep(0.2)
    assert result.returncode == 0, "push did not propagate"


# --- preview_tree (Phase 2.5 prerequisite) -------------------------------

def test_preview_tree_empty_paths_returns_empty_tree_sha(tmp_git_repo):
    """No paths → builds an empty tree and returns the well-known empty-tree SHA."""
    sha = git_ops.preview_tree(tmp_git_repo, [])
    assert sha == git_ops.EMPTY_TREE_SHA


def test_preview_tree_with_one_file_returns_nonempty_tree(tmp_git_repo):
    (tmp_git_repo / "src" / "a.py").write_text("x = 1\n")
    sha = git_ops.preview_tree(tmp_git_repo, ["src"])
    assert sha is not None
    assert sha != git_ops.EMPTY_TREE_SHA
    assert len(sha) == 40


def test_preview_tree_does_not_disturb_index_or_working_tree(tmp_git_repo):
    """preview_tree must not change real index, HEAD, or working tree."""
    # Pre-stage a file in the real index, plus drop an unstaged one.
    (tmp_git_repo / "src" / "staged.py").write_text("staged = 1\n")
    subprocess.run(["git", "add", "src/staged.py"], cwd=tmp_git_repo, check=True)
    (tmp_git_repo / "src" / "fresh.py").write_text("fresh = 2\n")
    pre_status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=tmp_git_repo,
        capture_output=True, text=True, check=True).stdout
    pre_head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_git_repo,
        capture_output=True, text=True, check=True).stdout

    git_ops.preview_tree(tmp_git_repo, ["src"])

    post_status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=tmp_git_repo,
        capture_output=True, text=True, check=True).stdout
    post_head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_git_repo,
        capture_output=True, text=True, check=True).stdout
    assert pre_status == post_status
    assert pre_head == post_head
    # Working-tree files still exist
    assert (tmp_git_repo / "src" / "staged.py").read_text() == "staged = 1\n"
    assert (tmp_git_repo / "src" / "fresh.py").read_text() == "fresh = 2\n"


def test_preview_tree_deterministic_for_same_input(tmp_git_repo):
    (tmp_git_repo / "src" / "a.py").write_text("x = 1\n")
    s1 = git_ops.preview_tree(tmp_git_repo, ["src"])
    s2 = git_ops.preview_tree(tmp_git_repo, ["src"])
    assert s1 is not None
    assert s1 == s2


def test_preview_tree_filters_missing_paths(tmp_git_repo):
    """Missing pathspecs are filtered out (mirrors snapshot_to_auto_track)."""
    (tmp_git_repo / "src" / "a.py").write_text("x = 1\n")
    sha = git_ops.preview_tree(tmp_git_repo, ["src", "does-not-exist"])
    assert sha is not None
    assert sha != git_ops.EMPTY_TREE_SHA


def test_preview_tree_cleans_up_temp_index(tmp_git_repo):
    """Temp index files are removed even on success."""
    (tmp_git_repo / "src" / "a.py").write_text("x = 1\n")
    git_ops.preview_tree(tmp_git_repo, ["src"])
    leftover = list((tmp_git_repo / ".git").glob("auto-track.idx.*.preview.*"))
    assert leftover == []
