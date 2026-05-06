# AI Assistance Policy for This Assignment

This course provides access to Codex (OpenAI's coding assistant) through
Clemson's site license. You are encouraged to use it as a tutor. You are
**not** encouraged to use it as a ghostwriter.

## What is captured

Local AI-agent traces for sessions you start inside this repository are saved
to `.ai-traces/` and committed to the auto-track snapshot ref. Codex is the
first supported adapter; future tools can write the same unified stream. Your
instructor can read these traces.

**This is captured:**

- The prompt you typed to a locally captured AI agent.
- The reply the AI agent produced.
- Any tool calls, shell commands, command outputs, approvals, or denials that
  the local adapter can observe.
- Any file edits the AI agent proposed or made.
- A snapshot of the working-tree files in the allowlist (`src/`, `tests/`,
  `.ai-traces/`, `.codex/`, `AGENTS.md`, `AI_POLICY.md`) on every
  test run, every Python invocation inside the project venv (via an
  `atexit` hook installed into the venv's `sitecustomize.py`), and every
  git commit (via a per-repo `.githooks/post-commit` hook). All three
  triggers record to a separate ref `refs/auto-track/snapshots` rather
  than to your branch. None of them install anything outside the project
  directory; see `PROCESS_TRACKING.md` for the trigger list and scoping
  details.
- Any commit reachable from your current branch HEAD when `pytest` runs —
  including commits on local branches you have not pushed yourself. We
  record the SHA of your current commit alongside each snapshot so that
  intentional commits you later rebase or amend away are still preserved
  as research data.
- If you run tests during a `git rebase`, `git merge`, or `git cherry-pick`
  operation, the in-progress state is captured even if you later abort the
  operation. The body field `git_state` records the operation context
  (`rebasing`/`merging`/`cherry-picking`/`clean`).

**This is NOT captured:**

- Your OpenAI API token (`.codex/auth.json` is gitignored).
- AI-agent sessions you run in directories outside this assignment.
- AI-agent sessions you run in tools that are not locally captured here
  (ChatGPT web, Codex cloud, Claude web, Copilot Chat, etc.). If you use
  those for this course, paste or summarize the interaction in
  `.ai-traces/external-attestation.txt` so your work is auditable.
- The contents of branches not reachable from your current HEAD at
  test-run time.
- Anything you do outside the course repository directory.

## How to keep work private

If you want to do truly private exploration (sketching an algorithm you may
not keep, scratch work you do not want recorded, etc.), do it in a separate
clone of the repository outside the course directory, or in a scratch
directory. The capture only fires when `pytest` runs inside the configured
course repo. There is no way to opt out of capture within a single test run
short of disabling it entirely (which violates course policy).

## Migration from v1

If your assignment repo started the semester under the v1 capture (commits
with `test-run:` subject lines on `main`), the first time you run tests
under v3, the new snapshot ref will second-parent your current `main`
HEAD — meaning both the v1 capture history AND any intentional commits you
authored on `main` before this point become reachable from
`refs/auto-track/snapshots`. v3 does not wipe the slate; it preserves and
reorganizes the prior trail.

## What Codex is configured to do here

The file `AGENTS.md` at the root of this repo tells Codex to act as a
Socratic tutor. It will generally ask you questions and give hints rather
than writing complete solutions. You can override this by insisting, but
the instructor can see that you did (the transcript records your prompt).

Approving a command or edit is captured as part of the interaction record.
Approval means you allowed the tool to proceed; it is not treated as proof
that you authored the resulting code.

## What counts as academic honesty

| You do this... | ...and it's: |
|---|---|
| Ask Codex to explain a concept you just learned | fine |
| Ask Codex to review your code for bugs | fine |
| Ask Codex for a hint on where you're stuck | fine |
| Ask Codex to generate a function, then type it over verbatim | violation |
| Ask Codex to do the assignment, then edit lightly | violation |
| Use an uncaptured AI tool and not record it in `.ai-traces/external-attestation.txt` | violation |
| Delete an AI trace from `.ai-traces/` before submission | violation |

If you're uncertain whether a use is allowed, ask your instructor before
submitting — not after.

## Verifying what was captured

The primary way to audit your local capture trail:

```bash
python -m tests._capture.audit
```

This summarizes every snapshot recorded on `refs/auto-track/snapshots`,
including timestamps, test counts, and the `current_head_sha` observed at
each run.

For power users who prefer raw git plumbing:

```bash
git log refs/auto-track/snapshots --format="%h %cI %s"
git show <sha>          # full body of a single snapshot
```

## If Codex is down or you prefer not to use it

You are never required to use Codex. This policy only covers what happens
**if** you use it.
