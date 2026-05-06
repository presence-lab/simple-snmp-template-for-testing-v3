#!/usr/bin/env python3
"""Show your commits without the automatic test-run entries.

Under the v3 capture design, snapshot commits no longer land on your
branches at all -- they are recorded on the separate ref
``refs/auto-track/snapshots`` (see PROCESS_TRACKING.md). That means a
plain ``git log`` already shows only your intentional commits, and this
tool's purpose is satisfied automatically by the v3 design.

This wrapper is kept for two reasons:

1. Backwards compatibility with v1 repositories that still have
   ``test-run:`` commits on ``main`` from an earlier semester. The
   ``--invert-grep --grep='^test-run:'`` filter strips those out so a
   migrated repo's log looks the same as a fresh one.
2. Under v3, the filter is a harmless no-op: no v3 capture commits
   land on your branch, so there is nothing for the filter to remove.

Usage:
    python tools/my_commits.py              # all your commits, most recent first
    python tools/my_commits.py -10          # last 10
    python tools/my_commits.py --since=1.week
    python tools/my_commits.py --author=you@example.com

Any argument you pass is forwarded to ``git log``. The filter is::

    git log --oneline --invert-grep --grep='^test-run:' <your args>

If you prefer typing the raw command, the one-liner above works in any
shell with no Python needed.
"""
import subprocess
import sys


def main() -> int:
    cmd = [
        "git", "log", "--oneline",
        "--invert-grep", "--grep=^test-run:",
        *sys.argv[1:],
    ]
    try:
        result = subprocess.run(cmd, check=False)
    except FileNotFoundError:
        print("git is not on PATH. Install Git and retry.", file=sys.stderr)
        return 127
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
