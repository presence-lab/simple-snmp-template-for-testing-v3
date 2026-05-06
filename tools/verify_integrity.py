"""Audit capture-layer integrity by comparing file hashes against INTEGRITY_HASHES.txt.

Usage:
    python tools/verify_integrity.py            # check current file hashes
    python tools/verify_integrity.py --update   # regenerate INTEGRITY_HASHES.txt
                                                # (instructor use only, after
                                                # intentional capture changes)

Exit code 0 on match, 1 on mismatch, 2 on missing file.
"""
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HASH_FILE = ROOT / "tools" / "INTEGRITY_HASHES.txt"

TRACKED = [
    ".codex/config.toml",
    ".codex/hooks/__init__.py",
    ".codex/hooks/_common.py",
    ".codex/hooks/permission_request.py",
    ".codex/hooks/post_tool_use.py",
    ".codex/hooks/pre_tool_use.py",
    ".codex/hooks/session_start.py",
    ".codex/hooks/stop.py",
    ".codex/hooks/user_prompt_submit.py",
    ".gitignore",
    "tests/conftest.py",
    "tests/_capture/__init__.py",
    "tests/_capture/__main__.py",
    "tests/_capture/ai_traces.py",
    "tests/_capture/agent_adapters/__init__.py",
    "tests/_capture/agent_adapters/base.py",
    "tests/_capture/agent_adapters/codex.py",
    "tests/_capture/agent_adapters/codex_normalize.py",
    "tests/_capture/agent_adapters/registry.py",
    "tests/_capture/audit.py",
    "tests/_capture/auth.py",
    "tests/_capture/capture.py",
    "tests/_capture/codex_ingest.py",
    "tests/_capture/git_ops.py",
    "tests/_capture/metadata.py",
    "tests/_capture/orchestrator.py",
    "tests/_capture/platform_compat.py",
    "tests/_capture/post_commit_entry.py",
    "tests/_capture/runtime_triggers.py",
    "tests/_capture/sitecustomize_payload.py",
    "tests/_capture/state.py",
    "tests/_capture/watchdog.py",
    ".githooks/post-commit",
]


def sha256_of(path: Path) -> str:
    # Normalize CRLF -> LF so hashes are stable across Windows working-tree
    # autocrlf expansion and Linux CI checkouts of the same git blob.
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def load_expected() -> dict:
    if not HASH_FILE.exists():
        return {}
    out = {}
    for line in HASH_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        h, _, path = line.partition("  ")
        out[path] = h
    return out


def write_expected(mapping: dict) -> None:
    HASH_FILE.write_text(
        "# Known-good SHA-256 hashes of capture-layer files.\n"
        "# Regenerated with: python tools/verify_integrity.py --update\n"
        + "".join(f"{h}  {path}\n" for path, h in sorted(mapping.items())),
        encoding="utf-8",
        newline="\n",
    )


def main() -> int:
    update = "--update" in sys.argv
    current = {}
    for rel in TRACKED:
        p = ROOT / rel
        if not p.exists():
            print(f"MISSING: {rel}")
            return 2
        current[rel] = sha256_of(p)

    if update:
        write_expected(current)
        print(f"Wrote {len(current)} hashes to {HASH_FILE}")
        return 0

    expected = load_expected()
    if not expected:
        print("No INTEGRITY_HASHES.txt found. Run with --update to create it.")
        return 2

    mismatches = [p for p in current if current[p] != expected.get(p)]
    missing = [p for p in expected if p not in current]

    if mismatches or missing:
        for p in mismatches:
            print(f"MODIFIED: {p}")
            print(f"  expected: {expected.get(p)}")
            print(f"  actual:   {current[p]}")
        for p in missing:
            print(f"MISSING_FROM_REPO: {p}")
        return 1

    print(f"OK - {len(current)} capture files unchanged.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
