"""Migration tests: v1 capture history coexists with v2 auto-track snapshots.

Per spec §9.4 + §10. The fixture hand-crafts v1-style commits on main (whose
subject lines look like real v1 capture output, but are NOT produced by any
real v1 capture path — these tests assert reachability and coexistence, NOT
body parsing).

After running one v3 capture session, the tests verify:

  1. The v1 commits are still on main (HEAD untouched).
  2. The first v3 snapshot's second parent is the v1 HEAD (no first parent
     yet because refs/auto-track/snapshots didn't exist).
  3. Walking refs/auto-track/snapshots WITHOUT --first-parent reaches the v1
     commits via the second-parent edge.
"""
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def tmp_git_repo_with_v1_history(tmp_path):
    """Per spec §9.4.1: hand-craft a v1-style commit history on main.

    The two synthetic v1 commits have subjects shaped like real v1 capture
    output. They are NOT real v1 captures — just commits whose surface form
    matches what a v1-migrated repo would look like for migration testing.
    """
    work = tmp_path / "work"
    subprocess.run(["git", "init", "-q", str(work)], check=True)
    subprocess.run(
        ["git", "-C", str(work), "config", "user.email", "t@e.com"],
        check=True)
    subprocess.run(
        ["git", "-C", str(work), "config", "user.name", "T"], check=True)
    (work / "src").mkdir()
    (work / "tests").mkdir()
    (work / "src" / "init.py").write_text("# init\n")
    subprocess.run(["git", "-C", str(work), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(work), "commit", "-q", "-m", "init"], check=True)
    for i in range(2):
        (work / "src" / f"f{i}.py").write_text(f"# v1 work {i}\n")
        subprocess.run(["git", "-C", str(work), "add", "-A"], check=True)
        subprocess.run(
            ["git", "-C", str(work), "commit", "-q", "-m",
             f"test-run: 0/0 passed\n\nsession_id: deadbeef{i}"],
            check=True)
    (work / "project-template-config.json").write_text(
        '{"capture_enabled": true}')
    return work


def test_v1_commits_remain_on_main_after_v2_capture(tmp_git_repo_with_v1_history):
    """v3 capture must not touch main; v1 history is preserved."""
    repo = tmp_git_repo_with_v1_history
    from tests._capture import capture
    ctx = capture.session_start(repo)
    assert ctx is not None, "capture should be enabled"
    capture.session_finish(repo, ctx, status="completed")

    # Determine the actual default branch name (some git installs use
    # `master`, others `main`). HEAD points to it post-init.
    branch = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True, text=True, check=True).stdout.strip()
    main_log = subprocess.run(
        ["git", "-C", str(repo), "log", "--format=%s", branch],
        capture_output=True, text=True, check=True).stdout
    assert "test-run: 0/0 passed" in main_log, (
        f"v1 subjects missing from {branch}:\n{main_log}")


def test_first_v2_snapshot_second_parents_current_head(
        tmp_git_repo_with_v1_history):
    """First v3 snapshot in a migrated repo: parents = [snap, head_before].

    Because refs/auto-track/snapshots did not exist before this run, there is
    no first parent — only the second parent (= HEAD before the run).
    """
    repo = tmp_git_repo_with_v1_history
    head_before = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True).stdout.strip()
    from tests._capture import capture
    ctx = capture.session_start(repo)
    assert ctx is not None
    capture.session_finish(repo, ctx, status="completed")

    snap = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "refs/auto-track/snapshots"],
        capture_output=True, text=True, check=True).stdout.strip()
    parents = subprocess.run(
        ["git", "-C", str(repo), "rev-list", "--parents", "-n", "1", snap],
        capture_output=True, text=True, check=True
    ).stdout.strip().split()
    # rev-list --parents output: <snap> <parent1>
    # When there is no first parent (auto-track ref new) but there IS a
    # second parent (current HEAD), the snapshot is built with a SINGLE
    # parent — namely the current HEAD. Total tokens: 2.
    assert len(parents) == 2, (
        f"expected snap + one parent, got {parents!r}")
    assert parents[0] == snap
    assert parents[1] == head_before, (
        f"second parent {parents[1]} != head_before {head_before}")


def test_v1_commits_reachable_via_auto_track(tmp_git_repo_with_v1_history):
    """Walk all ancestors of the auto-track ref (NO --first-parent) and assert
    the v1 subjects appear via the second-parent edge.

    The v3 snapshot subject is also `test-run: ... passed -- ...`. Counting
    occurrences of the exact v1 subject `test-run: 0/0 passed` distinguishes:
    the v3 snapshot reports the real test count (0/0 here, since no tests
    ran) but its subject form is `test-run: 0/0 passed -- session=...` so
    the prefix substring match below would catch it. To pin v1 commits
    specifically, count BLANK-LINE-prefixed occurrences (subject lines, not
    body lines) and exclude the v3 subject by checking for the v1 body
    marker `session_id: deadbeef`.
    """
    repo = tmp_git_repo_with_v1_history
    from tests._capture import capture
    ctx = capture.session_start(repo)
    assert ctx is not None
    capture.session_finish(repo, ctx, status="completed")

    # Walk all ancestors WITHOUT --first-parent so the second-parent edge
    # into v1 history is followed.
    log = subprocess.run(
        ["git", "-C", str(repo), "log", "--format=%H %s",
         "refs/auto-track/snapshots"],
        capture_output=True, text=True, check=True).stdout

    # Count subject lines that match the v1 form `test-run: 0/0 passed`
    # exactly (no trailing ` -- session=...`). The v3 snapshot subject has
    # a trailing ` -- session=` segment, so an exact-suffix check excludes it.
    v1_subject_lines = [
        ln for ln in log.strip().splitlines()
        if ln.split(" ", 1)[1] == "test-run: 0/0 passed"
    ]
    assert len(v1_subject_lines) == 2, (
        f"expected 2 v1 commits reachable, got {len(v1_subject_lines)}\n"
        f"full log:\n{log}"
    )
