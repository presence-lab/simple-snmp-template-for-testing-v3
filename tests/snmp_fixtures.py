"""
SNMP-specific pytest fixtures and hooks.

Loaded as a pytest plugin via the project-root conftest.py so that
tests/conftest.py can stay byte-identical to the template's
integrity-verified version (hashed in tools/INTEGRITY_HASHES.txt).
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Tuple

import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from .test_utils import (MockTCPClient, MockTCPServer,
                              TestDataGenerator)


@pytest.fixture
def mock_server():
    """Provide a mock TCP server for testing."""
    server = MockTCPServer()
    port = server.start()
    yield server, port
    server.stop()


@pytest.fixture
def mock_client():
    """Provide a mock TCP client for testing."""
    client = MockTCPClient()
    yield client
    client.close()


@pytest.fixture
def test_data_generator():
    """Provide a test data generator instance."""
    return TestDataGenerator()


@pytest.fixture
def sample_mib_data():
    """Provide sample MIB data for testing."""
    return TestDataGenerator.generate_test_mib_data()


@pytest.fixture
def temp_mib_file(tmp_path):
    """Create a temporary MIB file for testing."""
    mib_file = tmp_path / "test_mib.txt"

    # Write sample MIB data
    mib_content = """# Test MIB file
1.3.6.1.2.1.1.1.0,string,Test System Description
1.3.6.1.2.1.1.3.0,integer,1234567
1.3.6.1.2.1.1.4.0,string,admin@test.com
1.3.6.1.2.1.1.5.0,string,TestHost
1.3.6.1.2.1.2.1.0,integer,8
"""
    mib_file.write_text(mib_content)

    return str(mib_file)


@pytest.fixture
def sample_oids():
    """Provide a list of sample OIDs for testing."""
    return [
        "1.3.6.1.2.1.1.1.0",  # sysDescr
        "1.3.6.1.2.1.1.3.0",  # sysUpTime
        "1.3.6.1.2.1.1.5.0",  # sysName
        "1.3.6.1.2.1.2.1.0",  # ifNumber
        "1.3.6.1.2.1.2.2.1.2.1",  # ifDescr.1
    ]


@pytest.fixture
def sample_varbinds():
    """Provide sample varbinds for SET operations."""
    return [
        ("1.3.6.1.2.1.1.4.0", "string", "new_admin@test.com"),
        ("1.3.6.1.2.1.1.5.0", "string", "NewHostName"),
        ("1.3.6.1.2.1.2.2.1.7.1", "integer", 1),  # ifAdminStatus.1 = up
    ]


@pytest.fixture
def malformed_messages():
    """Provide various malformed messages for error testing."""
    return {
        "invalid_version": bytes([99, 0, 0, 0, 0, 1, 0, 0]),
        "invalid_pdu_type": bytes([1, 99, 0, 0, 0, 1, 0, 0]),
        "truncated": bytes([1, 0, 0, 0]),
        "empty": bytes(),
        "invalid_oid": bytes([1, 0, 0, 0, 0, 1, 0, 1, 255, 255]),
        "negative_varbind_count": bytes([1, 0, 0, 0, 0, 1, 255, 255]),
    }


@pytest.fixture(scope="session")
def bundle_points():
    """Define point allocations for each bundle."""
    return {
        1: 30,  # Bundle C - Core functionality
        2: 35,  # Bundle B - Intermediate features
        3: 35,  # Bundle A - Advanced features
    }


@pytest.fixture
def timeout_handler():
    """Provide a timeout handler for long-running operations."""
    import signal

    class TimeoutHandler:
        def __init__(self, seconds=5):
            self.seconds = seconds

        def __enter__(self):
            def timeout_handler(signum, frame):
                raise TimeoutError(f"Operation timed out after {self.seconds} seconds")

            # Set up the timeout
            if hasattr(signal, 'SIGALRM'):
                signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(self.seconds)
            return self

        def __exit__(self, type, value, traceback):
            # Disable the alarm
            if hasattr(signal, 'SIGALRM'):
                signal.alarm(0)

    return TimeoutHandler


@pytest.fixture
def capture_stdout(monkeypatch):
    """Capture stdout for testing print statements."""
    import io

    captured = io.StringIO()

    def get_output():
        return captured.getvalue()

    monkeypatch.setattr('sys.stdout', captured)

    return get_output


@pytest.fixture
def mock_socket(monkeypatch):
    """Mock socket module for testing without network access."""
    import socket as real_socket

    class MockSocket:
        def __init__(self):
            self.sent_data = []
            self.recv_data = []
            self.connected = False
            self.bind_address = None
            self.listening = False

        def connect(self, address):
            self.connected = True
            self.connect_address = address

        def bind(self, address):
            self.bind_address = address

        def listen(self, backlog):
            self.listening = True

        def accept(self):
            if not self.listening:
                raise RuntimeError("Socket not listening")
            return (MockSocket(), ('127.0.0.1', 12345))

        def send(self, data):
            if not self.connected:
                raise RuntimeError("Socket not connected")
            self.sent_data.append(data)
            return len(data)

        def sendall(self, data):
            return self.send(data)

        def recv(self, size):
            if not self.recv_data:
                return b''
            return self.recv_data.pop(0)

        def close(self):
            self.connected = False

        def setsockopt(self, *args):
            pass

        def getsockname(self):
            if self.bind_address:
                return self.bind_address
            return ('127.0.0.1', 12345)

        def settimeout(self, timeout):
            pass

    mock_socket_inst = MockSocket()

    def socket_constructor(*args, **kwargs):
        return mock_socket_inst

    monkeypatch.setattr('socket.socket', socket_constructor)

    return mock_socket_inst


@pytest.fixture
def clean_imports():
    """Clean imports to ensure fresh module loading."""
    # Store original modules
    original_modules = {}

    modules_to_clean = [
        'src.snmp_protocol',
        'src.snmp_agent',
        'src.snmp_manager',
        'src.mib_database',
        'solution.snmp_protocol',
        'solution.snmp_agent',
        'solution.snmp_manager',
        'solution.mib_database',
    ]

    for module in modules_to_clean:
        if module in sys.modules:
            original_modules[module] = sys.modules[module]
            del sys.modules[module]

    yield

    # Restore original modules
    for module, original in original_modules.items():
        sys.modules[module] = original


def pytest_collection_modifyitems(config, items):
    """Add default bundle(1) and points(1) markers to any test missing them."""
    for item in items:
        if not any(mark.name == 'bundle' for mark in item.iter_markers()):
            item.add_marker(pytest.mark.bundle(1))
        if not any(mark.name == 'points' for mark in item.iter_markers()):
            item.add_marker(pytest.mark.points(1))


def pytest_configure(config):
    """Register SNMP-specific custom markers."""
    config.addinivalue_line(
        "markers", "bundle(n): mark test as part of bundle n (1, 2, or 3)"
    )
    config.addinivalue_line(
        "markers", "points(n): assign n points to a test"
    )
    config.addinivalue_line(
        "markers", "timeout(n): set timeout for test in seconds"
    )
