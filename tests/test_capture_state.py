import json
import time
from pathlib import Path

from tests._capture import state


def test_start_session_creates_marker(tmp_path):
    sid = state.start_session(tmp_path, hard_deadline_seconds=60)
    marker = tmp_path / ".test-run-state" / f"{sid}.json"
    assert marker.exists()
    data = json.loads(marker.read_text())
    assert data["session_id"] == sid
    assert data["hard_deadline_seconds"] == 60
    assert "started_at" in data


def test_finish_session_removes_marker(tmp_path):
    sid = state.start_session(tmp_path, hard_deadline_seconds=60)
    state.finish_session(tmp_path, sid)
    marker = tmp_path / ".test-run-state" / f"{sid}.json"
    assert not marker.exists()


def test_detect_orphans_returns_prior_sessions(tmp_path):
    # Simulate a session that never finished
    sid = state.start_session(tmp_path, hard_deadline_seconds=60)
    # Backdate it so deadline has passed
    marker = tmp_path / ".test-run-state" / f"{sid}.json"
    data = json.loads(marker.read_text())
    data["started_at"] = time.time() - 120
    marker.write_text(json.dumps(data))

    orphans = state.detect_orphans(tmp_path)
    assert len(orphans) == 1
    assert orphans[0]["session_id"] == sid


def test_clear_orphans_removes_markers(tmp_path):
    sid = state.start_session(tmp_path, hard_deadline_seconds=1)
    marker = tmp_path / ".test-run-state" / f"{sid}.json"
    data = json.loads(marker.read_text())
    data["started_at"] = time.time() - 120
    marker.write_text(json.dumps(data))

    orphans = state.detect_orphans(tmp_path)
    state.clear_orphans(tmp_path, orphans)
    assert not marker.exists()


def test_recent_session_not_reported_as_orphan(tmp_path):
    state.start_session(tmp_path, hard_deadline_seconds=300)
    orphans = state.detect_orphans(tmp_path)
    assert orphans == []
