"""Tests for the git post-commit Python entry."""
import os
import subprocess
from pathlib import Path

from tests._capture import post_commit_entry


def test_main_returns_zero_when_capture_succeeds(tmp_git_repo_with_capture, monkeypatch):
    monkeypatch.chdir(tmp_git_repo_with_capture)
    monkeypatch.setenv("CAPTURE_PROJECT_ROOT", str(tmp_git_repo_with_capture))

    rc = post_commit_entry.main()

    assert rc == 0


def test_main_returns_zero_even_when_capture_disabled(tmp_path, monkeypatch):
    """A disabled capture must not abort the commit."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    monkeypatch.chdir(tmp_path)

    rc = post_commit_entry.main()

    assert rc == 0


def test_main_returns_zero_when_no_project_root(tmp_path, monkeypatch):
    """No project-template-config.json anywhere up the tree."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CAPTURE_PROJECT_ROOT", raising=False)

    rc = post_commit_entry.main()

    assert rc == 0


def test_main_returns_zero_when_snapshot_now_raises(tmp_git_repo_with_capture, monkeypatch):
    """Even if the orchestrator entry raises, main() must return 0."""
    from tests._capture import capture
    def boom(*a, **kw):
        raise RuntimeError("synthetic")
    monkeypatch.setattr(capture, "snapshot_now", boom)
    monkeypatch.chdir(tmp_git_repo_with_capture)
    monkeypatch.setenv("CAPTURE_PROJECT_ROOT", str(tmp_git_repo_with_capture))

    rc = post_commit_entry.main()

    assert rc == 0


def test_post_commit_hook_script_exists_and_delegates_to_python_module():
    project_root = Path(__file__).resolve().parent.parent
    hook = project_root / ".githooks" / "post-commit"
    assert hook.exists(), "Missing .githooks/post-commit"
    body = hook.read_text(encoding="utf-8")
    assert body.startswith("#!"), "Hook missing shebang"
    assert "post_commit_entry" in body, "Hook does not delegate to post_commit_entry"


def test_post_commit_hook_actually_fires_via_real_commit(tmp_git_repo_with_capture, monkeypatch):
    """End-to-end: install hook, configure hooksPath, make a commit,
    verify a snapshot landed on refs/auto-track/snapshots."""
    repo = tmp_git_repo_with_capture
    project_root = Path(__file__).resolve().parent.parent

    # Mirror the production .githooks/ into the tmp repo and configure it.
    hooks_src = project_root / ".githooks"
    hooks_dst = repo / ".githooks"
    import shutil
    shutil.copytree(hooks_src, hooks_dst)
    # On POSIX make sure executable bit is set; harmless on Windows.
    if os.name != "nt":
        for f in hooks_dst.iterdir():
            f.chmod(0o755)
    subprocess.run(
        ["git", "config", "--local", "core.hooksPath", ".githooks"],
        cwd=repo, check=True,
    )

    # Mirror the capture infrastructure so the hook can `import tests._capture.*`.
    for relpath in [
        "tests/__init__.py",
        "tests/_capture",
    ]:
        src = project_root / relpath
        dst = repo / relpath
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    # Make a real commit and check that the post-commit hook fired and
    # produced an auto-track snapshot.
    (repo / "src" / "scratch.py").write_text("x = 1\n")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo) + os.pathsep + env.get("PYTHONPATH", "")
    env["CAPTURE_PROJECT_ROOT"] = str(repo)
    subprocess.run(["git", "add", "src/scratch.py"], cwd=repo, check=True, env=env)
    result = subprocess.run(
        ["git", "commit", "-m", "trigger hook"],
        cwd=repo, env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0, f"commit failed: {result.stderr}"

    # Verify a snapshot was created with the right trigger label.
    body = subprocess.run(
        ["git", "log", "refs/auto-track/snapshots", "--format=%B", "-n", "1"],
        cwd=repo, capture_output=True, text=True,
    )
    assert "trigger: git_post_commit" in body.stdout, \
        f"hook did not produce git_post_commit snapshot:\n{body.stdout}"
