"""Manual CLI entrypoint for the capture orchestrator.

Usage::

    python -m tests._capture snapshot [--reason "instructor checkpoint"]

`--reason` is forwarded to the orchestrator and ends up as a
`manual_reason: ...` line in the snapshot commit body. Manual
snapshots always go through, regardless of dedupe state, per
spec decision row 6.

Exit codes:
    0  — snapshot created (commit SHA written to stdout)
    2  — orchestrator returned None (capture disabled, lock contention,
         or internal failure — see .test-runs.log for details)
    >0 — argparse usage error
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from tests._capture import orchestrator


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tests._capture",
        description="Manual capture-orchestrator CLI",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    snap = sub.add_parser(
        "snapshot",
        help="Take a manual auto-track snapshot of the current repo.",
    )
    snap.add_argument(
        "--reason", default=None,
        help="Free-form reason; recorded in the snapshot commit body.",
    )
    return parser


def main(argv: Optional[List[str]] = None, cwd: Optional[Path] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    repo = Path(cwd) if cwd is not None else Path.cwd()

    if args.cmd == "snapshot":
        sha = orchestrator.take_snapshot(
            repo,
            trigger="manual",
            pytest_session_id=None,
            manual_reason=args.reason,
        )
        if sha is None:
            return 2
        sys.stdout.write(sha + "\n")
        return 0
    # argparse's required=True means this should never trigger.
    return 1


if __name__ == "__main__":
    sys.exit(main())
