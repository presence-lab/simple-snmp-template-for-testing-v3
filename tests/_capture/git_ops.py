"""Git subprocess wrappers used by the capture layer.

All operations are scoped to student-editable areas (src/ and tests/).
Never calls git commands that could affect branches other than HEAD.
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple


GIT_ENV = {
    # Never prompt for credentials — prevents hangs if auth isn't configured.
    "GIT_TERMINAL_PROMPT": "0",
    # Don't pop up askpass dialogs either.
    "GIT_ASKPASS": "echo",
}


def run_git(args: List[str], cwd: Path, timeout: float = 15.0,
            capture: bool = True) -> subprocess.CompletedProcess:
    """Run a git command with our safe env. Never raises on non-zero exit.

    Public so other capture modules can introspect git state (e.g., dedupe
    logic in capture.py checking `git log -1`).
    """
    env = {**os.environ, **GIT_ENV}
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        env=env,
        capture_output=capture,
        text=True,
        timeout=timeout,
    )


@dataclass
class DiffStats:
    added: int
    removed: int
    files: List[str]


def push_auto_track_background(repo: Path, log_path: Path) -> None:
    """Detached push of refs/auto-track/snapshots. Mirrors v1 push_background
    pattern. Best-effort -- never raises (open() failures and Popen failures
    both caught locally; callers can rely on this being safe to invoke even
    on a disk-full / permission-denied system)."""
    env = {**os.environ, **GIT_ENV}
    if run_git(["remote", "get-url", "origin"], cwd=repo, timeout=5.0).returncode != 0:
        return
    try:
        log_fh = open(log_path, "ab")
    except OSError:
        return
    try:
        kwargs = {
            "cwd": str(repo),
            "env": env,
            "stdout": log_fh,
            "stderr": subprocess.STDOUT,
            "stdin": subprocess.DEVNULL,
        }
        if os.name == "nt":
            kwargs["creationflags"] = 0x08000000 | 0x00000008
        else:
            kwargs["start_new_session"] = True
        try:
            subprocess.Popen(
                ["git", "push", "origin",
                 f"{AUTO_TRACK_REF}:{AUTO_TRACK_REF}"],
                **kwargs,
            )
        except OSError:
            pass
    finally:
        log_fh.close()


def is_git_repo(path: Path) -> bool:
    """True iff path is inside a git working tree."""
    result = run_git(["rev-parse", "--is-inside-work-tree"], cwd=path, timeout=5.0)
    return result.returncode == 0 and result.stdout.strip() == "true"


def diff_stats_trees(repo: Path, prev_tree: str, new_tree: str) -> DiffStats:
    """Numstat between two tree SHAs. prev_tree may be EMPTY_TREE_SHA for
    first-snapshot baseline. Mirrors v1's diff_stats_staged interface but
    against arbitrary trees."""
    result = run_git(["diff", "--numstat", prev_tree, new_tree],
                     cwd=repo, timeout=10.0)
    added = removed = 0
    files: List[str] = []
    if result.returncode == 0:
        for line in result.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) >= 3:
                try:
                    added += int(parts[0])
                    removed += int(parts[1])
                except ValueError:
                    pass
                files.append(parts[2])
    return DiffStats(added=added, removed=removed, files=files)


def current_head_sha(repo: Path) -> Optional[str]:
    """Returns HEAD sha or None if unavailable."""
    result = run_git(["rev-parse", "HEAD"], cwd=repo, timeout=5.0)
    if result.returncode == 0:
        return result.stdout.strip()
    return None


AUTO_TRACK_REF = "refs/auto-track/snapshots"
AUTO_TRACK_ORIGIN_TIP_REF = "refs/auto-track/origin-tip"
EMPTY_TREE_SHA = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


def read_auto_track_tip(repo: Path) -> Optional[str]:
    """Returns the SHA of refs/auto-track/snapshots if the ref exists, else None."""
    result = run_git(["rev-parse", "--verify", AUTO_TRACK_REF],
                     cwd=repo, timeout=5.0)
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def pick_first_parent(repo: Path) -> Optional[str]:
    """Apply spec §6 step 5 dominance rules to choose first parent SHA."""
    local = read_auto_track_tip(repo)
    origin_result = run_git(["rev-parse", "--verify", AUTO_TRACK_ORIGIN_TIP_REF],
                            cwd=repo, timeout=5.0)
    origin = origin_result.stdout.strip() if origin_result.returncode == 0 else None

    if local is None and origin is None:
        return None
    if local is None:
        return origin
    if origin is None:
        return local
    if local == origin:
        return local
    # Both exist and differ — check ancestry
    local_in_origin = run_git(
        ["merge-base", "--is-ancestor", local, origin],
        cwd=repo, timeout=5.0).returncode == 0
    if local_in_origin:
        return origin  # origin is ahead
    origin_in_local = run_git(
        ["merge-base", "--is-ancestor", origin, local],
        cwd=repo, timeout=5.0).returncode == 0
    if origin_in_local:
        return local  # local is ahead
    return local  # divergence — local wins, push will surface non-FF


def fetch_auto_track(repo: Path) -> Optional[str]:
    """Best-effort fetch into AUTO_TRACK_ORIGIN_TIP_REF. Pre-deletes the local
    mirror so a remote-side deletion is reflected. Never raises. Returns the
    post-fetch SHA, or None if the ref does not exist on origin or fetch failed."""
    # Pre-fetch delete: clear any stale local mirror before fetching. Without
    # this, a remote-side deletion would leave the prior local ref untouched —
    # git fetch exits non-zero on a missing remote ref but does not clear the
    # destination. See spec §6 step 4.
    run_git(["update-ref", "-d", AUTO_TRACK_ORIGIN_TIP_REF], cwd=repo, timeout=5.0)

    refspec = f"+{AUTO_TRACK_REF}:{AUTO_TRACK_ORIGIN_TIP_REF}"
    result = run_git(
        ["fetch", "--no-tags", "--force", "--no-write-fetch-head",
         "origin", refspec],
        cwd=repo, timeout=5.0,
    )
    if result.returncode != 0:
        return None
    # Read the just-fetched ref to confirm presence
    rev = run_git(["rev-parse", "--verify", AUTO_TRACK_ORIGIN_TIP_REF],
                  cwd=repo, timeout=5.0)
    if rev.returncode != 0:
        return None
    return rev.stdout.strip()


def detect_git_state(repo: Path) -> str:
    """Returns 'clean' | 'merging' | 'rebasing' | 'cherry-picking'."""
    git_dir = repo / ".git"
    if not git_dir.is_dir():
        return "clean"  # not a git repo; caller will skip earlier
    if (git_dir / "MERGE_HEAD").exists():
        return "merging"
    if (git_dir / "CHERRY_PICK_HEAD").exists():
        return "cherry-picking"
    if (git_dir / "rebase-merge").exists() or (git_dir / "rebase-apply").exists():
        return "rebasing"
    if (git_dir / "REBASE_HEAD").exists():
        return "rebasing"
    return "clean"


def current_head_info(repo: Path) -> Tuple[str, Optional[str]]:
    """Returns (ref_name_or_'detached', sha_or_None_for_unborn)."""
    ref_result = run_git(["symbolic-ref", "--short", "HEAD"],
                         cwd=repo, timeout=5.0)
    if ref_result.returncode == 0:
        ref = ref_result.stdout.strip()
    else:
        ref = "detached"
    sha_result = run_git(["rev-parse", "--verify", "HEAD"],
                         cwd=repo, timeout=5.0)
    sha = sha_result.stdout.strip() if sha_result.returncode == 0 else None
    return ref, sha


def snapshot_to_auto_track(
    repo: Path,
    message: str,
    snapshot_paths: List[str],
    head_ref: str,
    head_sha: Optional[str],
    *,
    force_paths: Optional[List[str]] = None,
    unstage_after: Optional[List[str]] = None,
) -> Optional[str]:
    """Execute spec §6 steps 7-11 with exactly one CAS retry on update-ref failure.

    `force_paths` (Task 2.5.10) are staged with `git add -Af` so they enter the
    snapshot tree even when .gitignore excludes them — defeats Attack K
    (gitignore evasion).

    `unstage_after` (Task 2.5.10) are removed from the index after staging
    via `git rm --cached --ignore-unmatch` — defeats Attack L (accidental
    .codex/auth.json staging). Both are keyword-only and default to None;
    the watchdog calls without them and that path is unchanged.
    """
    existing = [p for p in snapshot_paths if (repo / p).exists()]
    second_parent = head_sha

    for attempt in range(2):  # at most two attempts (initial + one retry)
        if attempt == 1:
            # Retry path: re-fetch and re-pick first parent against current state
            fetch_auto_track(repo)
        first_parent = pick_first_parent(repo)
        new_sha = _build_and_commit(
            repo, message, existing, first_parent, second_parent,
            force_paths=force_paths,
            unstage_after=unstage_after,
        )
        if new_sha is None:
            return None
        # CAS predicate is the LOCAL ref's current value, not the chosen
        # first parent. The two diverge on a fresh clone: local ref is None
        # while origin-tip exists, so first_parent is origin-tip but the
        # local ref still doesn't exist (must use 0-OID for create).
        local_tip = read_auto_track_tip(repo)
        expected_old = local_tip if local_tip else "0" * 40
        update_result = run_git(
            ["update-ref", AUTO_TRACK_REF, new_sha, expected_old],
            cwd=repo, timeout=5.0,
        )
        if update_result.returncode == 0:
            return new_sha
    return None


def preview_tree(repo: Path, snapshot_paths: List[str]) -> Optional[str]:
    """Build a tree object from snapshot_paths against a per-PID temp index
    WITHOUT committing or updating any ref. Returns the tree SHA, or None on
    failure. Used for tree-SHA dedupe in the orchestrator.

    Mirrors the read-tree+add+write-tree portion of _build_and_commit. The
    temp index file is unique per call (uses os.getpid() + a small random
    suffix) so it never collides with a concurrent snapshot's index.
    """
    import secrets
    existing = [p for p in snapshot_paths if (repo / p).exists()]
    suffix = f"{os.getpid()}.preview.{secrets.token_hex(4)}"
    idx_path = repo / ".git" / f"auto-track.idx.{suffix}"
    env = {**os.environ, **GIT_ENV, "GIT_INDEX_FILE": str(idx_path)}
    try:
        rt = subprocess.run(
            ["git", "read-tree", "--empty"],
            cwd=str(repo), env=env, capture_output=True, text=True, timeout=10,
        )
        if rt.returncode != 0:
            return None
        if existing:
            ar = subprocess.run(
                ["git", "add", "-A", "--", *existing],
                cwd=str(repo), env=env, capture_output=True, text=True, timeout=30,
            )
            if ar.returncode != 0:
                return None
        wt = subprocess.run(
            ["git", "write-tree"],
            cwd=str(repo), env=env, capture_output=True, text=True, timeout=10,
        )
        if wt.returncode != 0:
            return None
        return wt.stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        return None
    finally:
        try:
            idx_path.unlink()
        except (FileNotFoundError, OSError):
            pass


def _build_and_commit(
    repo: Path,
    message: str,
    existing_paths: List[str],
    first_parent: Optional[str],
    second_parent: Optional[str],
    *,
    force_paths: Optional[List[str]] = None,
    unstage_after: Optional[List[str]] = None,
) -> Optional[str]:
    """Build temp index, write tree, commit-tree. Returns new commit SHA or None.

    See `snapshot_to_auto_track` for force_paths / unstage_after semantics.
    """
    idx_path = repo / ".git" / f"auto-track.idx.{os.getpid()}"
    env = {**os.environ, **GIT_ENV, "GIT_INDEX_FILE": str(idx_path)}
    try:
        # Step 7: build temp index
        rt = subprocess.run(["git", "read-tree", "--empty"],
                            cwd=str(repo), env=env, capture_output=True, text=True, timeout=10)
        if rt.returncode != 0:
            return None

        # Force-paths take precedence over the regular add: any path that
        # appears in BOTH lists is staged via `git add -Af` only, so the
        # regular `git add -A` doesn't trip on gitignored entries (which
        # would otherwise cause it to exit non-zero).
        force_set = set(force_paths or [])
        regular_paths = [p for p in existing_paths if p not in force_set]

        if regular_paths:
            ar = subprocess.run(
                ["git", "add", "-A", "--", *regular_paths],
                cwd=str(repo), env=env, capture_output=True, text=True, timeout=30,
            )
            if ar.returncode != 0:
                return None

        # Adapter-contributed force-staging (defeats .gitignore evasion).
        if force_paths:
            existing_force = [p for p in force_paths if (repo / p).exists()]
            if existing_force:
                fr = subprocess.run(
                    ["git", "add", "-Af", "--", *existing_force],
                    cwd=str(repo), env=env, capture_output=True, text=True,
                    timeout=30,
                )
                if fr.returncode != 0:
                    return None

        # Adapter-contributed post-stage unstage (defends against secret leaks).
        # `-r` is required for directory paths -- without it, git rm refuses
        # with "fatal: not removing 'd' recursively without -r" (exit 128) and
        # the dir's contents stay in the snapshot tree, silently leaking
        # whatever the adapter wanted excluded. `--ignore-unmatch` keeps the
        # call cheap when the path is absent. We log a warning if the call
        # exits non-zero so silent failures still leave a trail.
        if unstage_after:
            for p in unstage_after:
                try:
                    rm = subprocess.run(
                        ["git", "rm", "-r", "--cached", "--ignore-unmatch",
                         "--", p],
                        cwd=str(repo), env=env, capture_output=True,
                        text=True, timeout=10,
                    )
                    if rm.returncode != 0:
                        # Best-effort log to .test-runs.log so a partial
                        # failure does not hide. Never raise.
                        try:
                            (repo / ".test-runs.log").open("a", encoding="utf-8").write(
                                f"git_ops: unstage_after {p!r} failed rc={rm.returncode}: "
                                f"{rm.stderr.strip()[:200]}\n"
                            )
                        except OSError:
                            pass
                except (subprocess.TimeoutExpired, OSError):
                    continue

        # Step 8: write tree
        wt = subprocess.run(["git", "write-tree"],
                            cwd=str(repo), env=env, capture_output=True, text=True, timeout=10)
        if wt.returncode != 0:
            return None
        new_tree = wt.stdout.strip()

        # Step 9: numstat against prior tree (for callers that care; baked into message by caller)
        # Caller already composed the full message including diff stats.

        # Step 10: commit-tree with parents
        commit_args = ["commit-tree", new_tree]
        if first_parent:
            commit_args += ["-p", first_parent]
        if second_parent:
            commit_args += ["-p", second_parent]
        commit_args += ["-F", "-"]
        ct = subprocess.run(["git", *commit_args],
                            cwd=str(repo), env=env, input=message,
                            capture_output=True, text=True, timeout=10)
        if ct.returncode != 0:
            return None
        return ct.stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        return None
    finally:
        try:
            idx_path.unlink()
        except (FileNotFoundError, OSError):
            pass
