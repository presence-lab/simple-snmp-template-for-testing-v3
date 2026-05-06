"""Tests for the body that gets installed into the venv as sitecustomize.py."""
import json
import os
import subprocess
import sys
from pathlib import Path

from tests._capture import sitecustomize_payload


def test_payload_is_a_nonempty_string():
    assert isinstance(sitecustomize_payload.PAYLOAD, str)
    assert len(sitecustomize_payload.PAYLOAD) > 100


def test_payload_compiles_as_python():
    compile(sitecustomize_payload.PAYLOAD, "sitecustomize.py", "exec")


def _run_payload(cwd: Path, env_overrides: dict):
    """Execute the payload in a subprocess and return (returncode, stdout, stderr)."""
    env = os.environ.copy()
    env.pop("PYTEST_CURRENT_TEST", None)
    env.pop("_CAPTURE_SUBPROCESS", None)
    env.update(env_overrides)
    return subprocess.run(
        [sys.executable, "-c", sitecustomize_payload.PAYLOAD],
        cwd=str(cwd), env=env, capture_output=True, text=True, timeout=15,
    )


def test_payload_does_not_crash_outside_project_root(tmp_path):
    # cwd is some random tmp dir; CAPTURE_PROJECT_ROOT points elsewhere
    # that doesn't exist. Payload must exit cleanly.
    result = _run_payload(
        tmp_path,
        {"CAPTURE_PROJECT_ROOT": str(tmp_path / "nonexistent")},
    )
    assert result.returncode == 0, result.stderr


def test_payload_skips_under_pytest(tmp_path):
    # When PYTEST_CURRENT_TEST is set, payload must be a no-op.
    result = _run_payload(
        tmp_path,
        {"PYTEST_CURRENT_TEST": "x::y", "CAPTURE_PROJECT_ROOT": str(tmp_path)},
    )
    assert result.returncode == 0, result.stderr


def test_payload_skips_inside_capture_subprocess(tmp_path):
    result = _run_payload(
        tmp_path,
        {"_CAPTURE_SUBPROCESS": "1", "CAPTURE_PROJECT_ROOT": str(tmp_path)},
    )
    assert result.returncode == 0, result.stderr


def test_payload_no_ops_when_cwd_outside_project_root(tmp_path):
    # Real project-template-config under tmp_path/project; cwd is tmp_path/elsewhere.
    project = tmp_path / "project"
    project.mkdir()
    (project / "project-template-config.json").write_text(
        json.dumps({"distribution_mode": "student", "capture_enabled": False})
    )
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    result = _run_payload(
        elsewhere,
        {"CAPTURE_PROJECT_ROOT": str(project)},
    )
    assert result.returncode == 0, result.stderr


def test_payload_swallows_all_errors(tmp_path):
    # Force the orchestrator path: project root that exists but isn't a
    # git repo. snapshot_now() returns None internally without raising;
    # the payload must exit 0 regardless.
    project = tmp_path / "project"
    project.mkdir()
    (project / "project-template-config.json").write_text(
        json.dumps({"distribution_mode": "student", "capture_enabled": True})
    )

    result = _run_payload(
        project,
        {"CAPTURE_PROJECT_ROOT": str(project)},
    )
    assert result.returncode == 0, result.stderr
