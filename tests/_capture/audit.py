"""Friendly local audit of refs/auto-track/snapshots.

Invocation:
    python -m tests._capture.audit            # last 50, fixed-width columns
    python -m tests._capture.audit --all      # remove the cap

Local-only -- does NOT call git fetch. Does NOT modify any state.
See spec section 5 audit.py row for the contract.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

EMPTY_REPO_MESSAGE = (
    "No snapshots recorded yet. "
    "Run `python run_tests.py` to create the first one."
)
DEFAULT_CAP = 50
AUTO_TRACK_REF = "refs/auto-track/snapshots"

# Strip C0/C1 control characters (excluding tab/newline) before printing
# to defang ANSI escapes / cursor-control sequences in untrusted commit
# bodies. A determined student can write any commit and force-push the
# auto-track ref, so audit fields are not necessarily safe to render
# verbatim.
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


def _safe(text: str) -> str:
    return _CONTROL_CHAR_RE.sub("?", text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tests._capture.audit")
    parser.add_argument("--all", action="store_true",
                        help="Show all snapshots (default: last 50)")
    args = parser.parse_args(argv)

    repo = Path.cwd()
    tip_check = subprocess.run(
        ["git", "rev-parse", "--verify", AUTO_TRACK_REF],
        cwd=repo, capture_output=True, text=True)
    if tip_check.returncode != 0:
        print(EMPTY_REPO_MESSAGE)
        return 0

    cap = None if args.all else DEFAULT_CAP
    print_snapshots(repo, cap)
    return 0


def print_snapshots(repo: Path, cap: int | None) -> None:
    """Walk refs/auto-track/snapshots --first-parent and print each commit
    in the pinned column order. Local-only -- no fetch.

    --first-parent intentionally excludes commits reachable only via
    second-parent edges (for example: intentional commits on main that the
    snapshot merge folded in). Those edges exist for ancestry but are not
    snapshot rows in the audit.
    """
    # %cI gives a strict-ISO committer date, but in the local timezone with a
    # numeric offset (e.g. ...-04:00). The audit's pinned iso_timestamp column
    # uses the body's `timestamp:` field, which the orchestrator already emits
    # in UTC-Z form. We pass %cI as a fallback for v1/non-snapshot commits in
    # the ancestry that lack a body timestamp.
    fmt = "%H%x00%cI%x00%B%x00----RECORD----"
    args = ["git", "log", AUTO_TRACK_REF, "--first-parent", "--format=" + fmt]
    if cap is not None:
        args.extend(["-n", str(cap)])
    raw = subprocess.run(
        args, cwd=repo, capture_output=True, text=True, check=True).stdout
    for record in raw.split("----RECORD----\n"):
        record = record.strip()
        if not record:
            continue
        parts = record.split("\x00")
        if len(parts) < 3:
            continue
        full_sha, fallback_ts, body = parts[0], parts[1], parts[2]
        fields = parse_body(body)
        subject = body.splitlines()[0] if body else ""
        # Prefer the orchestrator-recorded UTC `timestamp:` from the body; fall
        # back to git's committer ISO date for non-snapshot commits.
        iso_ts = fields.get("timestamp", fallback_ts)
        capture_version = fields.get("capture_version")
        # Current schema is v3 (Phase 2 bumped CAPTURE_VERSION = 3; v2 was
        # never shipped). Anything lacking v3 is a "v1 capture" body.
        if capture_version != "3":
            print_v1_line(full_sha, iso_ts, subject)
            continue
        head_ref = fields.get("current_head_ref", "?")
        head_sha = fields.get("current_head_sha", "unborn")
        head_sha7 = head_sha[:7] if head_sha != "unborn" else "unborn"
        git_state = fields.get("git_state", "?")
        passed = fields.get("tests_passed", "?")
        total = fields.get("tests_total", "?")
        print(f"{full_sha[:7]}  {_safe(iso_ts)}  {_safe(head_ref)}  "
              f"{_safe(head_sha7)}  {_safe(git_state)}  "
              f"{_safe(passed)}/{_safe(total)}  {_safe(subject)}")


def parse_body(body: str) -> dict:
    """Parse 'key: value' lines from a v3 commit body."""
    fields = {}
    for line in body.splitlines():
        if ": " in line:
            k, _, v = line.partition(": ")
            fields[k.strip()] = v.strip()
    return fields


def print_v1_line(full_sha: str, iso_ts: str, subject: str) -> None:
    """v1 commits lack v3 fields -- annotate columns the v1 schema lacks.

    Spec section 5 audit.py row says to annotate '[v1 capture]' in the
    columns the v1 schema lacks (head_ref, head_sha7, git_state). This
    consolidates the annotation into the head_ref column and uses '-------'
    placeholders for head_sha7 and '-' for git_state, since rendering a
    multi-token annotation across three columns adds noise without aiding
    grep/awk usability. The '[v1 capture]' label in the head_ref position
    is still grep-friendly and unambiguous.
    """
    print(f"{full_sha[:7]}  {_safe(iso_ts)}  [v1 capture]  -------  -        "
          f"-/-      {_safe(subject)}")


if __name__ == "__main__":
    sys.exit(main())
