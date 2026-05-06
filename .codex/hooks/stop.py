from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import project_repo_root, safe_main


def _snapshot(payload):
    from tests._capture import orchestrator
    from tests._capture.agent_adapters.codex import CodexAdapter

    adapter = CodexAdapter()
    meta = adapter.metadata_from_hook_payload(payload)
    orchestrator.take_snapshot(
        project_repo_root(),
        trigger="codex_stop",
        pytest_session_id=None,
        adapter_metadata=meta,
    )


if __name__ == "__main__":
    raise SystemExit(safe_main("Stop", _snapshot, emit_continue_json=True))
