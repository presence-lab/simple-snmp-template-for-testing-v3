from tests._capture import metadata


def test_hostname_hash_is_deterministic_and_16_chars():
    h1 = metadata.hostname_hash("/some/project")
    h2 = metadata.hostname_hash("/some/project")
    assert h1 == h2
    assert len(h1) == 16
    assert all(c in "0123456789abcdef" for c in h1)


def test_hostname_hash_varies_by_project_path():
    h1 = metadata.hostname_hash("/project/a")
    h2 = metadata.hostname_hash("/project/b")
    assert h1 != h2


def test_format_commit_message_includes_all_fields():
    result = metadata.TestResult(
        total=15, passed=12, failed=3, error=0, skipped=0,
        duration_seconds=23.4,
        bundles_passing=[1], bundles_failing=[2, 3],
    )
    msg = metadata.format_commit_message(
        session_id="abc12345",
        status="completed",
        result=result,
        diff_added=47, diff_removed=12,
        files_changed=["src/a.py"],
        hostname_hash="deadbeef0000",
    )
    assert msg.startswith("test-run:")
    assert "12/15 passed" in msg
    assert "session_id: abc12345" in msg
    assert "status: completed" in msg
    assert "tests_passed: 12" in msg
    assert "bundles_passing: [1]" in msg
    assert "hostname_hash: deadbeef0000" in msg


def test_format_commit_message_hang_status_has_warning_summary():
    result = metadata.TestResult(
        total=0, passed=0, failed=0, error=0, skipped=0,
        duration_seconds=180.0,
        bundles_passing=[], bundles_failing=[],
    )
    msg = metadata.format_commit_message(
        session_id="abc12345", status="hang_watchdog_killed",
        result=result, diff_added=0, diff_removed=0, files_changed=[],
        hostname_hash="deadbeef0000",
    )
    assert "SESSION HUNG" in msg
    assert "killed by watchdog" in msg
    assert "--" in msg  # ASCII separator, not em-dash


def test_format_includes_v3_fields():
    msg = metadata.format_commit_message(
        session_id="abc",
        status="completed",
        result=metadata.TestResult(),
        diff_added=0, diff_removed=0, files_changed=[],
        hostname_hash="hh",
        current_head_ref="main",
        current_head_sha="0" * 40,
        git_state="clean",
        trigger="pytest",
        agent_name="none",
        agent_session_id="none",
    )
    assert "current_head_ref: main" in msg
    assert f"current_head_sha: {'0' * 40}" in msg
    assert "git_state: clean" in msg
    assert "trigger: pytest" in msg
    assert "agent_name: none" in msg
    assert "agent_session_id: none" in msg
    assert "capture_version: 3" in msg

def test_format_handles_unborn_head():
    msg = metadata.format_commit_message(
        session_id="abc", status="completed", result=metadata.TestResult(),
        diff_added=0, diff_removed=0, files_changed=[],
        hostname_hash="hh",
        current_head_ref="main",
        current_head_sha="unborn",
        git_state="clean",
    )
    assert "current_head_sha: unborn" in msg

def test_format_handles_detached_head():
    msg = metadata.format_commit_message(
        session_id="abc", status="completed", result=metadata.TestResult(),
        diff_added=0, diff_removed=0, files_changed=[],
        hostname_hash="hh",
        current_head_ref="detached",
        current_head_sha="a" * 40,
        git_state="clean",
    )
    assert "current_head_ref: detached" in msg

def test_format_accepts_each_git_state():
    for state in ("clean", "merging", "rebasing", "cherry-picking"):
        msg = metadata.format_commit_message(
            session_id="abc", status="completed", result=metadata.TestResult(),
            diff_added=0, diff_removed=0, files_changed=[],
            hostname_hash="hh",
            current_head_ref="main", current_head_sha="0" * 40,
            git_state=state,
        )
        assert f"git_state: {state}" in msg

def test_format_accepts_each_trigger():
    for trig in ("pytest", "codex_stop", "claude_code_stop", "manual"):
        msg = metadata.format_commit_message(
            session_id="abc", status="completed", result=metadata.TestResult(),
            diff_added=0, diff_removed=0, files_changed=[],
            hostname_hash="hh",
            trigger=trig,
        )
        assert f"trigger: {trig}" in msg

def test_zero_tests_with_pytest_trigger_says_no_tests_collected():
    """A pytest run that genuinely collected nothing keeps the existing wording."""
    msg = metadata.format_commit_message(
        session_id="abc", status="completed", result=metadata.TestResult(),
        diff_added=0, diff_removed=0, files_changed=[],
        hostname_hash="hh", trigger="pytest",
    )
    assert msg.startswith("test-run: no tests collected")


def test_zero_tests_with_snapshot_trigger_uses_snapshot_wording():
    """Trigger-driven snapshots (post-commit, sitecustomize, manual) must NOT
    look like a failed test session. The summary line should mark them as
    code-state captures, not as zero-test runs.
    """
    for trig in ("git_post_commit", "sitecustomize", "manual"):
        msg = metadata.format_commit_message(
            session_id="abc", status="completed", result=metadata.TestResult(),
            diff_added=0, diff_removed=0, files_changed=[],
            hostname_hash="hh", trigger=trig,
        )
        assert msg.startswith("snapshot: code state captured"), (
            f"trigger={trig} produced wrong summary: {msg.splitlines()[0]!r}"
        )
        assert f"trigger={trig}" in msg.splitlines()[0]
        assert "no tests collected" not in msg.splitlines()[0]


def test_format_records_agent_session_when_provided():
    msg = metadata.format_commit_message(
        session_id="abc", status="completed", result=metadata.TestResult(),
        diff_added=0, diff_removed=0, files_changed=[],
        hostname_hash="hh",
        trigger="codex_stop",
        agent_name="codex",
        agent_session_id="019d4abd-1234-7890-abcd-ef0123456789",
    )
    assert "agent_name: codex" in msg
    assert "agent_session_id: 019d4abd-1234-7890-abcd-ef0123456789" in msg
