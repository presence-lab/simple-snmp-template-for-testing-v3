"""The sitecustomize.py body installed into the project venv.

Stored as a string so the integrity audit can hash it and so it lives
with the rest of the capture layer rather than loose inside a venv.
runtime_triggers.install_sitecustomize() writes PAYLOAD to
<venv>/site-packages/sitecustomize.py on first pytest run.

Behavior at interpreter startup (when site.py imports sitecustomize):
  1. Resolve project root via CAPTURE_PROJECT_ROOT env or by walking
     up from cwd looking for project-template-config.json.
  2. If cwd isn't inside the project root, no-op.
  3. If running under pytest (PYTEST_CURRENT_TEST set), no-op — the
     conftest already triggers capture, and double-firing wastes work.
  4. If we are already inside a capture-spawned subprocess
     (_CAPTURE_SUBPROCESS set), no-op — prevents recursion.
  5. Otherwise register an atexit callback that calls
     capture.snapshot_now() with trigger='sitecustomize'. atexit (not
     import time) so we capture the post-run state of src/, not its
     pre-run state.

All failure modes are silent: the payload runs on every interpreter
start in the venv and must never raise into the student's Python
invocation.
"""
PAYLOAD = '''"""Auto-installed by tests/_capture/runtime_triggers.py — DO NOT EDIT.
Source: tests/_capture/sitecustomize_payload.py:PAYLOAD
"""
import atexit
import os
import sys
from pathlib import Path


def _find_project_root():
    explicit = os.environ.get("CAPTURE_PROJECT_ROOT")
    if explicit:
        return Path(explicit)
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        if (parent / "project-template-config.json").is_file():
            return parent
    return None


def _should_skip():
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return True
    if os.environ.get("_CAPTURE_SUBPROCESS"):
        return True
    return False


def _trigger_snapshot():
    try:
        root = _find_project_root()
        if root is None:
            return
        cwd = Path.cwd().resolve()
        try:
            cwd.relative_to(root.resolve())
        except ValueError:
            return
        sys.path.insert(0, str(root))
        os.environ["_CAPTURE_SUBPROCESS"] = "1"
        try:
            from tests._capture import capture
            capture.snapshot_now(root, trigger_name="sitecustomize")
        finally:
            os.environ.pop("_CAPTURE_SUBPROCESS", None)
    except Exception:
        pass


if not _should_skip():
    atexit.register(_trigger_snapshot)
'''
