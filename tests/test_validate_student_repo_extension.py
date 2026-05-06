"""Verify the student-repo validator requires the new editor-agnostic
capture files when capture is enabled."""
from pathlib import Path


REQUIRED_NEW_PATHS = [
    "tests/_capture/runtime_triggers.py",
    "tests/_capture/sitecustomize_payload.py",
    "tests/_capture/post_commit_entry.py",
    ".githooks/post-commit",
]


def test_validator_lists_new_capture_files():
    body = (Path(__file__).resolve().parent.parent
            / "tools" / "validate_student_repo.py").read_text(encoding="utf-8")
    for required in REQUIRED_NEW_PATHS:
        assert required in body, f"{required} not declared in validator"
