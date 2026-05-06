# Process Tracking in This Assignment

This project automatically records a snapshot of your code at three moments: when you run the tests, when you run any other Python script in the project venv, and when you make a git commit. These snapshots live on a dedicated ref `refs/auto-track/snapshots` in your repository and are pushed to the configured remote — they do **not** land on your branches (`main`, feature branches, etc.), so your normal `git log` only shows your intentional commits.

Audit your local trail with `python -m tests._capture.audit`.

## When capture fires

A snapshot is recorded when:

1. **You run `pytest` or `python run_tests.py`** — the standard pytest trigger. Each snapshot's body lists `trigger: pytest`.
2. **You run any Python script in the project venv** — for example `python src/foo.py`, an IDE green-arrow run, the debugger, or a REPL session. Triggered by an `atexit` hook installed into your venv's `sitecustomize.py` the first time you run pytest. The hook only fires when the working directory is inside the project, and it skips itself when pytest is already running so you don't get double snapshots. Snapshot body lists `trigger: sitecustomize`.
3. **You make a git commit in this repo** — fires `.githooks/post-commit`, which is wired up via `core.hooksPath = .githooks` (a per-repo git setting; it does not affect any other git repo on your machine). Snapshot body lists `trigger: git_post_commit`.

None of these triggers install anything outside the project directory. The sitecustomize hook is only installed when your venv lives at `venv/` or `.venv/` inside this folder — a venv stored elsewhere (`~/.virtualenvs/...`, conda, virtualenvwrapper, or a venv belonging to another project) is rejected so capture infrastructure isn't dropped into a venv shared with your other work. The post-commit hook lives inside `.git/config` and `.githooks/` (per-repo only). `run_tests.py` refuses to run unless you're in the local venv and prints the exact setup commands.

## What is captured

Files under `src/`, `tests/`, and `.ai-traces/` are staged into the commit, along with the shipped guardrail files (`AGENTS.md`, `.codex/config.toml`, `AI_POLICY.md`). The commit message carries this metadata:

- A timestamp and session ID
- Test pass/fail counts and duration
- How many lines were added or removed since the previous run
- Your Python version and OS type
- A one-way hash of your machine's hostname (the instructor cannot recover your hostname from the hash; it is only used to tell apart your home laptop from a lab machine in a pattern-of-use sense)

Local AI-agent traces (`.ai-traces/**/*.jsonl`) are also captured when present. Codex is the first supported adapter. See [AI_POLICY.md](AI_POLICY.md) for the full AI policy.

**Nothing outside the project directory is captured. No credentials, no browsing history, no system information.**

## What is NOT captured

- Files outside the allowlist above
- Your hostname (only a hash)
- Keystrokes, timing within a session, cursor position, or anything your editor sees
- AI assistant interactions from tools without a local adapter (ChatGPT web, Codex cloud, Claude web, Copilot Chat, etc.). See [AI_POLICY.md](AI_POLICY.md); uncaptured tool use should be recorded in `.ai-traces/external-attestation.txt`.
- Your Codex OpenAI token (`.codex/auth.json` is gitignored).

## Why this exists

Your learning matters more than your final grade. A passing submission tells us you delivered working code. A development history tells us *you* wrote it — by showing how your understanding evolved, where you got stuck, which tests flipped from failing to passing as you learned. This is the process your instructor wants to see.

## You can verify exactly what is committed

The primary way to inspect your local capture trail:

```bash
python -m tests._capture.audit
```

This summarizes every snapshot recorded on `refs/auto-track/snapshots`, including timestamps, test counts, and the commit SHA your `HEAD` pointed at during each run.

If you prefer raw git commands, the snapshot trail lives on a dedicated ref and is not visible from a normal `git log`:

```bash
git log refs/auto-track/snapshots --format="%h %cI %s"
git show <sha>          # full body of a single snapshot
```

You'll see entries whose subject lines begin with `test-run:`.

## Filtering test-run commits out of your log

Under v3, capture commits are stored on `refs/auto-track/snapshots` rather than on your branches, so your normal `git log` already shows only your own intentional commits — no filtering needed.

For backwards compatibility with v1 repositories that may still have `test-run:` commits on `main` from an earlier semester, this wrapper is still provided:

```
python tools/my_commits.py
```

Works on Windows (PowerShell, cmd, Git Bash), macOS, and Linux — no shell-specific invocation needed. It accepts any `git log` flags (e.g. `-10`, `--since=1.week`). The equivalent raw command if you prefer to type it directly:

```
git log --oneline --invert-grep --grep='^test-run:'
```

Under v3 the filter is a harmless no-op (there are no `test-run:` commits on your branch to strip out).

## If the push fails

The commit always happens locally, even if your machine is offline or your credentials aren't set up. The next successful push will carry all backlogged commits. Warnings are written to `.test-runs.log` in the project root.

If your student repo has no remote configured yet, or your credentials aren't set up, run:

```bash
python tools/setup_credentials.py
```

It will diagnose the most common first-time push problems (no remote, no credential helper, rejected PAT) and print step-by-step fix instructions for your platform.

## What you'll see when a test hangs

If one of your tests blocks indefinitely (most commonly a socket waiting for a connection that never arrives), two things can kill it:

- **Per-test timeout** — the default is 30 seconds per test; a test can override with `@pytest.mark.timeout(N)`. When this fires, the test is marked failed and **on Windows the entire pytest process exits** (this is a quirk of pytest-timeout's thread method, which is the only mechanism that works on Windows). On macOS/Linux with the signal method, only that one test dies and the suite continues.
- **Session watchdog** — a background subprocess that terminates the whole test session if it runs past `max(120s, 3 × n_tests × 30s)`. This is a safety net for the case where pytest itself hangs or a per-test timeout can't interrupt the blocked code path.

Both routes still produce a `test-run:` snapshot on `refs/auto-track/snapshots`. A per-test timeout records `status: pytest_exit_<code>` (usually `pytest_exit_1`) or `status: completed` depending on which layer saw the exit first; a watchdog kill records `status: hang_watchdog_killed`. Either way the run is visible in your auto-track trail (`python -m tests._capture.audit`); you don't need to do anything special.

## Academic integrity note

Tampering with the capture layer (deleting `tests/conftest.py`, editing `tests/_capture/`, force-updating or deleting `refs/auto-track/snapshots`) is treated the same as any other academic integrity violation and is easy to detect. If you have a legitimate reason to disable capture on a specific machine (for example, a machine where git push authentication cannot be set up), contact your instructor rather than removing the hook.
