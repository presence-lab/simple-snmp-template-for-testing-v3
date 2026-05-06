"""Friendly error diagnosis for common git auth failures."""
from pathlib import Path


AUTH_HINT_HEADER = "--- Git push could not complete ---"

HINTS = {
    "could not read Username": (
        "Git needs credentials to push. On first use:\n"
        "  - Windows: Install Git Credential Manager (usually bundled with Git for Windows).\n"
        "  - macOS: Run `git config --global credential.helper osxkeychain`.\n"
        "  - Linux: Run `git config --global credential.helper store` (or use GCM).\n"
        "Then run any git push manually once to cache your token."
    ),
    "Authentication failed": (
        "Your GitHub credentials were rejected. If you recently changed your\n"
        "password or enabled 2FA, create a Personal Access Token at\n"
        "https://github.com/settings/tokens and use it as your password."
    ),
    "Could not resolve host": (
        "Network unreachable. Commits are still saved locally. Push will retry\n"
        "on the next test run once you're online."
    ),
    "does not appear to be a git repository": (
        "No git remote is configured. Commits are saved locally but cannot push.\n"
        "Ask your instructor for the repository URL, then run once:\n"
        "  git remote add origin <url>\n"
        "  git push -u origin HEAD\n"
        "Subsequent test runs will push automatically."
    ),
    "rejected": (
        "The remote has commits you don't. Run `git pull --rebase` to integrate\n"
        "them, then run the tests again."
    ),
}

# Markers that indicate `git push` succeeded. A successful push always emits a
# "To <url>" line followed by ref-update lines, or "Everything up-to-date" if
# the remote is already current. Finding one of these means everything before
# it is now-stale history.
_SUCCESS_MARKERS = ("\nTo ", "\nEverything up-to-date")

# Read enough of the tail to comfortably span several pushes' worth of output.
# 4KB used to be the window, but a single failure plus a few normal-run banners
# can push the success marker out of view, leaving the stale hint reappearing
# forever after a successful push.
_TAIL_BYTES = 32 * 1024


def diagnose_push_log(log_path: Path) -> str:
    """Return a friendly multi-line hint for the most recent push failure, or ''.

    Only failure indicators that appear AFTER the most recent successful push
    marker are considered. This way a single bad day of credentials does not
    keep reappearing on every snapshot for the rest of the semester.
    """
    if not log_path.exists():
        return ""
    try:
        data = log_path.read_bytes()[-_TAIL_BYTES:].decode("utf-8", errors="replace")
    except OSError:
        return ""

    last_success = max(data.rfind(marker) for marker in _SUCCESS_MARKERS)
    relevant = data[last_success:] if last_success >= 0 else data

    hints = [hint for trigger, hint in HINTS.items() if trigger in relevant]
    if not hints:
        return ""
    return AUTH_HINT_HEADER + "\n" + "\n\n".join(hints) + "\n"
