"""Python entry point invoked by .githooks/post-commit.

Kept thin so the shell hook is a one-liner and the orchestration
logic lives here, where it can be unit-tested. Always returns 0:
a misbehaving hook must not block a student's commit.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    try:
        explicit = os.environ.get("CAPTURE_PROJECT_ROOT")
        if explicit:
            root = Path(explicit)
        else:
            cwd = Path.cwd()
            root = next(
                (p for p in [cwd, *cwd.parents]
                 if (p / "project-template-config.json").is_file()),
                None,
            )
        if root is None:
            return 0
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from tests._capture import capture
        capture.snapshot_now(root, trigger_name="git_post_commit")
    except Exception:
        # Hook MUST NOT block commits.
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
