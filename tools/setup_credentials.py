#!/usr/bin/env python3
"""
Cross-platform Git credentials helper for GitHub Classroom.

Purpose:
    Diagnose and (with your confirmation) fix the three most common reasons
    `git push` fails on day 1 of a GitHub Classroom assignment:
      1. No `origin` remote configured.
      2. No credential helper set, so Git keeps asking for a password.
      3. Credentials rejected (expired token, 2FA/SSO, wrong URL).

Usage:
    python tools/setup_credentials.py             # interactive diagnose + fix
    python tools/setup_credentials.py --diagnose  # read-only report, exit
    python tools/setup_credentials.py --help      # this help

This script will NEVER silently change your Git config. Every command it is
about to run is printed first, and it waits for you to type `y` before doing
anything.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

# ANSI color codes -- match the style used by run_tests.py.
if os.environ.get("NO_COLOR"):
    GREEN = RED = YELLOW = BLUE = BOLD = RESET = ""
else:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


def _platform() -> str:
    """Return 'windows', 'macos', or 'linux'."""
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    """Run a command capturing stdout/stderr. Never uses shell=True."""
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        errors="replace",
    )


def _ok(msg: str) -> None:
    print(f"{GREEN}[OK]{RESET} {msg}")


def _warn(msg: str) -> None:
    print(f"{YELLOW}[WARN]{RESET} {msg}")


def _err(msg: str) -> None:
    print(f"{RED}[ERROR]{RESET} {msg}")


def _header(msg: str) -> None:
    print()
    print(f"{BOLD}{BLUE}== {msg} =={RESET}")


def _prompt(msg: str) -> str:
    """Prompt for input, showing the prompt in bold."""
    return input(f"{BOLD}{msg}{RESET}").strip()


def _confirm(cmd: list[str]) -> bool:
    """Show a command and ask y/N. Returns True if the user said yes."""
    print(f"  Proposed: {BOLD}{' '.join(cmd)}{RESET}")
    answer = _prompt("  Run this command? (y/N): ").lower()
    return answer == "y"


def _get_remote_url() -> str | None:
    """Return the URL for `origin`, or None if not configured."""
    result = _run(["git", "remote", "get-url", "origin"])
    if result.returncode != 0:
        return None
    url = result.stdout.strip()
    return url or None


def _get_credential_helper() -> str:
    """Return the effective credential.helper value (empty string if unset)."""
    result = _run(["git", "config", "--get", "credential.helper"])
    return result.stdout.strip()


def _in_git_repo() -> bool:
    result = _run(["git", "rev-parse", "--is-inside-work-tree"])
    return result.returncode == 0 and result.stdout.strip() == "true"


def _recommended_helper(platform: str) -> str:
    if platform == "windows":
        return "manager"
    if platform == "macos":
        return "osxkeychain"
    return "store"  # Linux default; we'll warn about it.


def _helper_is_acceptable(helper: str, platform: str) -> bool:
    """Return True if the current helper is a sensible choice for the platform."""
    if not helper:
        return False
    if platform == "windows":
        return helper in ("manager", "manager-core")
    if platform == "macos":
        return helper == "osxkeychain"
    # Linux: any non-empty helper is at least something.
    return True


# ---------------------------------------------------------------------------
# Diagnostic report
# ---------------------------------------------------------------------------

def diagnose(verbose: bool = True) -> int:
    """Print the current state. Return 0 if healthy, 1 otherwise."""
    platform = _platform()
    issues = 0

    _header("Git repository")
    if not _in_git_repo():
        _err("Current directory is not inside a Git repository.")
        _err("Run this script from the root of your cloned assignment.")
        return 1
    _ok("Inside a Git working tree.")

    _header("Remote (origin)")
    url = _get_remote_url()
    if url is None:
        _warn("No `origin` remote configured.")
        if verbose:
            print("  Fix:  git remote add origin <your-repo-url>")
        issues += 1
    else:
        _ok(f"origin = {url}")
        if not url.startswith("https://"):
            _warn("origin is not an HTTPS URL; SSH uses a separate auth flow.")

    _header("Credential helper")
    helper = _get_credential_helper()
    if not helper:
        _warn("credential.helper is not set.")
        if verbose:
            print(f"  Recommended on {platform}: {_recommended_helper(platform)}")
        issues += 1
    elif not _helper_is_acceptable(helper, platform):
        _warn(f"credential.helper = {helper!r} (unusual for {platform})")
        if verbose:
            print(f"  Recommended on {platform}: {_recommended_helper(platform)}")
        issues += 1
    else:
        _ok(f"credential.helper = {helper}")

    print()
    if issues == 0:
        _ok("No issues detected.")
        return 0
    _warn(f"{issues} issue(s) detected. Run without --diagnose to fix interactively.")
    return 1


# ---------------------------------------------------------------------------
# Interactive fix-up flow
# ---------------------------------------------------------------------------

def _fix_remote() -> None:
    """Ensure origin is configured. Prompts for URL if missing."""
    _header("Remote (origin)")
    url = _get_remote_url()
    if url is not None:
        _ok(f"origin already set to {url}")
        return

    _warn("You don't have an `origin` remote configured.")
    print("  GitHub Classroom should have given you a repo URL.")
    pasted = _prompt(
        "Paste your GitHub repo URL (HTTPS form, e.g. "
        "https://github.com/org/repo.git) or press Enter to skip: "
    )
    if not pasted:
        print("  Skipped. You can set this later with:")
        print("    git remote add origin <your-repo-url>")
        return

    cmd = ["git", "remote", "add", "origin", pasted]
    if _confirm(cmd):
        result = _run(cmd)
        if result.returncode == 0:
            _ok(f"origin set to {pasted}")
        else:
            _err(result.stderr.strip() or "git remote add failed")
    else:
        print(f"  OK, not running. Command for later: {' '.join(cmd)}")


def _set_helper(value: str) -> None:
    """Run `git config --global credential.helper <value>` with confirmation."""
    cmd = ["git", "config", "--global", "credential.helper", value]
    if not _confirm(cmd):
        print(f"  OK, not running. Command for later: {' '.join(cmd)}")
        return
    result = _run(cmd)
    if result.returncode == 0:
        _ok(f"credential.helper set to {value!r}")
    else:
        _err(result.stderr.strip() or "git config failed")


def _fix_helper() -> None:
    """Set a credential helper appropriate for the platform."""
    platform = _platform()
    _header("Credential helper")
    helper = _get_credential_helper()

    if _helper_is_acceptable(helper, platform):
        _ok(f"credential.helper = {helper} (good for {platform})")
        return

    if helper:
        _warn(f"credential.helper = {helper!r} (unusual for {platform})")
    else:
        _warn("credential.helper is not set.")

    if platform == "windows":
        print("  Recommended: Git Credential Manager (bundled with Git for Windows).")
        print("  It opens a browser window for GitHub sign-in and remembers you.")
        _set_helper("manager")
        return

    if platform == "macos":
        print("  Recommended: osxkeychain (uses your macOS Keychain).")
        _set_helper("osxkeychain")
        return

    # Linux: give the student a choice.
    print("  Two common options on Linux:")
    print(f"    {BOLD}1){RESET} store  -- saves credentials to ~/.git-credentials")
    print(f"       {YELLOW}Warning:{RESET} PLAINTEXT file. Anyone who can read")
    print(f"       your home directory can see your token.")
    print(f"    {BOLD}2){RESET} cache  -- keeps credentials in memory for 1 hour")
    print(f"       More secure, but you re-enter your token each session.")
    choice = _prompt("  Choose 1 (store), 2 (cache), or press Enter to skip: ")
    if choice == "1":
        _set_helper("store")
    elif choice == "2":
        _set_helper("cache --timeout=3600")
    else:
        print("  Skipped.")


def _explain_push_failure(stderr: str) -> None:
    """Translate common git push errors into actionable advice."""
    lower = stderr.lower()

    if "could not read username" in lower or "authentication failed" in lower:
        print()
        _warn("Looks like a credentials problem.")
        print("  If your GitHub account has 2FA enabled (or your org requires tokens),")
        print("  create a Personal Access Token:")
        print("    1. https://github.com/settings/tokens?type=beta")
        print("    2. Fine-grained token, scoped to this repository")
        print("    3. Permissions: Contents -> Read and write")
        print("    4. Use the token as your password on the next `git push`")
        return

    if "does not appear to be a git repository" in lower or "repository not found" in lower:
        print()
        _warn("The remote URL is wrong, the repo doesn't exist, or you lack access.")
        print("  Double-check the URL with: git remote -v")
        return

    if "could not resolve host" in lower or "network is unreachable" in lower:
        print()
        _warn("Network issue -- can't reach github.com.")
        print("  Check your internet connection and try again.")
        return

    if "src refspec" in lower and "does not match" in lower:
        print()
        _warn("Nothing to push -- you haven't made any commits yet.")
        print("  That's fine. Make a commit, then push.")
        return

    # Fallback.
    print()
    _warn("Push failed for a reason this script doesn't recognize.")
    print("  Full error is above. Common fixes:")
    print("    - Wrong URL? Check `git remote -v`")
    print("    - Need a token? https://github.com/settings/tokens?type=beta")


def _probe_push() -> None:
    """Offer a dry-run push so the student can see auth works before committing."""
    _header("Push probe")
    if _get_remote_url() is None:
        print("  Skipping -- no origin configured yet.")
        return

    print("  A dry-run push will contact GitHub, verify the URL, and")
    print("  verify your credentials would be accepted. It does NOT upload anything.")
    answer = _prompt("  Run `git push -u origin HEAD --dry-run`? (y/N): ").lower()
    if answer != "y":
        print("  Skipped.")
        return

    result = _run(["git", "push", "-u", "origin", "HEAD", "--dry-run"])
    if result.stdout:
        print(result.stdout.rstrip())
    if result.stderr:
        print(result.stderr.rstrip())

    if result.returncode == 0:
        _ok("Dry-run push succeeded. You are ready to push for real.")
    else:
        _err(f"Dry-run push failed (exit {result.returncode}).")
        _explain_push_failure(result.stderr or "")


def interactive() -> int:
    """Run the full interactive diagnose + guided setup."""
    print("=" * 72)
    print(f"{BOLD}GitHub credentials setup helper{RESET}")
    print("=" * 72)
    print("This script helps you get `git push` working for the first time.")
    print("It will NEVER change your Git config silently -- every command is")
    print("shown first, and you must type `y` to run it.")

    if not _in_git_repo():
        _err("Current directory is not inside a Git repository.")
        _err("Run this script from the root of your cloned assignment.")
        return 1

    _fix_remote()
    _fix_helper()
    _probe_push()

    _header("Final state")
    diagnose(verbose=False)

    print()
    url = _get_remote_url()
    if url is None:
        print(f"{BOLD}Next step:{RESET} add your repo URL with `git remote add origin ...`")
    else:
        print(f"{BOLD}Next step:{RESET} run `git push -u origin HEAD` to publish your work.")
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        prog="setup_credentials.py",
        description=(
            "Diagnose and fix common Git push problems "
            "(missing remote, no credential helper, rejected credentials)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python tools/setup_credentials.py             # interactive\n"
            "  python tools/setup_credentials.py --diagnose  # read-only report\n"
        ),
    )
    parser.add_argument(
        "--diagnose",
        action="store_true",
        help="Report current state without prompting. Exit 0 if healthy, 1 otherwise.",
    )
    args = parser.parse_args()

    try:
        if args.diagnose:
            return diagnose(verbose=True)
        return interactive()
    except KeyboardInterrupt:
        print()
        print("Cancelled.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
