"""
Integration test suite for SNMP Agent-Manager communication.
Tests end-to-end functionality with real network sockets and protocol handling.
Organized by specification grading bundles for clear expectations.

Bundle 1 (C Grade): Basic end-to-end communication - GET operations work across network
Bundle 2 (B Grade): Complete protocol support - SET operations, error propagation
Bundle 3 (A Grade): Production scenarios - concurrent clients, persistence, stress testing
"""

import random
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


def find_free_port():
    """Find a free port for testing."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port


@pytest.fixture
def free_port():
    """Provide a free port for each test."""
    return find_free_port()


@pytest.fixture
def agent_thread():
    """Start an SNMP agent in a background thread for testing."""
    agents = []
    
    def start_agent(port):
        from src.snmp_agent import SNMPAgent
        agent = SNMPAgent(port=port)
        agents.append(agent)
        # Start agent in separate thread
        def run_agent():
            try:
                agent.start()
            except Exception:
                pass  # Ignore exceptions when shutting down
        
        thread = threading.Thread(target=run_agent, daemon=True)
        thread.start()
        return agent, thread
    
    yield start_agent
    
    # Cleanup: stop all agents
    for agent in agents:
        agent.running = False
        if hasattr(agent, 'server_socket') and agent.server_socket:
            try:
                agent.server_socket.close()
            except:
                pass


# ============================================================================
# BUNDLE 1 (C GRADE) - BASIC END-TO-END COMMUNICATION
# Core integration testing: GET operations working across real network sockets
# ============================================================================

class TestBundleCIntegrationCore:
    """Bundle C tests for core SNMP agent-manager integration"""
    
    @pytest.mark.bundle(1)
    @pytest.mark.points(5)
    def test_basic_get_integration(self, free_port, agent_thread, capsys):
        """Test basic GET request from manager to agent over real sockets."""
        from src.snmp_manager import SNMPManager

        # Start agent
        agent, thread = agent_thread(free_port)
        time.sleep(0.1)  # Let agent start
        
        # Create manager and perform GET
        manager = SNMPManager()
        manager.get('localhost', free_port, ['1.3.6.1.2.1.1.1.0'])
        
        # Verify output
        captured = capsys.readouterr()
        assert '1.3.6.1.2.1.1.1.0 =' in captured.out, "Should receive valid GET response"
        assert 'Router Model X2000' in captured.out or 'High Performance Edge Router' in captured.out
    
    @pytest.mark.bundle(1)
    @pytest.mark.points(4)
    def test_multiple_oid_get_integration(self, free_port, agent_thread, capsys):
        """Test GET request with multiple OIDs over real sockets."""
        from src.snmp_manager import SNMPManager

        # Start agent
        agent, thread = agent_thread(free_port)
        time.sleep(0.1)
        
        # Request multiple OIDs
        test_oids = [
            '1.3.6.1.2.1.1.1.0',  # sysDescr
            '1.3.6.1.2.1.1.5.0',  # sysName
            '1.3.6.1.2.1.1.6.0',  # sysLocation
        ]
        
        manager = SNMPManager()
        manager.get('localhost', free_port, test_oids)
        
        # Verify all OIDs in response
        captured = capsys.readouterr()
        # Filter for lines containing OID responses (ignoring debug output)
        output_lines = [line for line in captured.out.split('\n') if '=' in line and '.' in line]
        assert len(output_lines) == 3, f"Should have 3 OID response lines, got {len(output_lines)}"
        
        for oid in test_oids:
            assert any(oid in line for line in output_lines), f"OID {oid} should be in output"
    
    @pytest.mark.bundle(1)
    @pytest.mark.points(3)
    def test_get_nonexistent_oid_integration(self, free_port, agent_thread, capsys):
        """Test GET request for non-existent OID propagates error correctly."""
        from src.snmp_manager import SNMPManager

        # Start agent
        agent, thread = agent_thread(free_port)
        time.sleep(0.1)
        
        # Request non-existent OID
        manager = SNMPManager()
        manager.get('localhost', free_port, ['9.8.7.6.5.4.3.2.1.0'])
        
        # Verify error is propagated
        captured = capsys.readouterr()
        assert 'Error: No such OID exists' in captured.out
    
    @pytest.mark.bundle(1)
    @pytest.mark.points(3)
    def test_uptime_integration(self, free_port, agent_thread, capsys):
        """Test that uptime updates correctly in real integration."""
        from src.snmp_manager import SNMPManager

        # Start agent
        agent, thread = agent_thread(free_port)
        time.sleep(0.1)
        
        manager = SNMPManager()
        
        # Get initial uptime
        manager.get('localhost', free_port, ['1.3.6.1.2.1.1.3.0'])
        captured1 = capsys.readouterr()
        
        # Extract uptime value (look for the number before the parentheses)
        import re
        match1 = re.search(r'1\.3\.6\.1\.2\.1\.1\.3\.0 = (\d+)', captured1.out)
        assert match1, "Should find uptime value in output"
        initial_uptime = int(match1.group(1))
        
        # Wait and get uptime again
        time.sleep(0.2)  # 200ms
        manager.get('localhost', free_port, ['1.3.6.1.2.1.1.3.0'])
        captured2 = capsys.readouterr()
        
        match2 = re.search(r'1\.3\.6\.1\.2\.1\.1\.3\.0 = (\d+)', captured2.out)
        assert match2, "Should find second uptime value in output"
        second_uptime = int(match2.group(1))
        
        # Uptime should have increased
        assert second_uptime > initial_uptime, f"Uptime should increase: {initial_uptime} -> {second_uptime}"
        
        # Increase should be reasonable (less than 100 timeticks for 200ms)
        time_diff = second_uptime - initial_uptime
        assert time_diff < 100, f"Time difference should be reasonable: got {time_diff} timeticks"
    
    @pytest.mark.bundle(1)
    @pytest.mark.points(3)
    def test_agent_accepts_multiple_connections(self, free_port, agent_thread):
        """Test that agent can accept multiple sequential connections."""
        from src.snmp_manager import SNMPManager

        # Start agent
        agent, thread = agent_thread(free_port)
        time.sleep(0.1)
        
        # Make multiple connections
        manager = SNMPManager()
        
        for i in range(5):
            # Each get() call creates a new connection
            with patch('sys.stdout', new=StringIO()) as fake_out:
                manager.get('localhost', free_port, ['1.3.6.1.2.1.1.1.0'])
                output = fake_out.getvalue()
                assert '1.3.6.1.2.1.1.1.0 =' in output, f"Connection {i} should succeed"
    
    @pytest.mark.bundle(1)
    @pytest.mark.points(2)
    def test_agent_handles_client_disconnection(self, free_port, agent_thread):
        """Test that agent handles client disconnections gracefully."""
        from src.snmp_manager import SNMPManager

        # Start agent
        agent, thread = agent_thread(free_port)
        time.sleep(0.1)
        
        # Create a connection and deliberately close it
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            client_socket.connect(('localhost', free_port))
            client_socket.close()  # Close without sending data
            
            # Agent should still be running and accept new connections
            time.sleep(0.1)  # Give agent time to handle the disconnection
            
            # Verify agent still accepts new connections
            manager = SNMPManager()
            with patch('sys.stdout', new=StringIO()) as fake_out:
                manager.get('localhost', free_port, ['1.3.6.1.2.1.1.1.0'])
                output = fake_out.getvalue()
                assert '1.3.6.1.2.1.1.1.0 =' in output, "Agent should still accept connections after client disconnect"
        
        finally:
            if not client_socket._closed:
                client_socket.close()


# ============================================================================
# BUNDLE 2 (B GRADE) - COMPLETE PROTOCOL SUPPORT
# SET operations, error handling, and full protocol compliance
# ============================================================================

class TestBundleBIntegrationIntermediate:
    """Bundle B tests for intermediate SNMP integration features"""
    
    @pytest.mark.bundle(2)
    @pytest.mark.points(5)
    def test_basic_set_integration(self, free_port, agent_thread, capsys):
        """Test basic SET request from manager to agent over real sockets."""
        from src.snmp_manager import SNMPManager

        # Start agent
        agent, thread = agent_thread(free_port)
        time.sleep(0.1)
        
        # Perform SET operation
        manager = SNMPManager()
        manager.set('localhost', free_port, '1.3.6.1.2.1.1.4.0', 'string', 'integration-test@example.com')
        
        # Verify successful SET
        captured = capsys.readouterr()
        assert 'Set operation successful:' in captured.out
        assert '1.3.6.1.2.1.1.4.0 = integration-test@example.com' in captured.out
    
    @pytest.mark.bundle(2)
    @pytest.mark.points(4)
    def test_set_persistence_integration(self, free_port, agent_thread, capsys):
        """Test that SET values persist and can be retrieved with GET."""
        from src.snmp_manager import SNMPManager

        # Start agent
        agent, thread = agent_thread(free_port)
        time.sleep(0.1)
        
        manager = SNMPManager()
        
        # Set a value
        new_contact = f'persistent-test-{random.randint(1000, 9999)}@example.org'
        manager.set('localhost', free_port, '1.3.6.1.2.1.1.4.0', 'string', new_contact)
        
        captured_set = capsys.readouterr()
        assert 'Set operation successful:' in captured_set.out
        
        # Retrieve the value with GET
        manager.get('localhost', free_port, ['1.3.6.1.2.1.1.4.0'])
        
        captured_get = capsys.readouterr()
        assert new_contact in captured_get.out, "SET value should persist and be retrievable with GET"
    
    @pytest.mark.bundle(2)
    @pytest.mark.points(4)
    def test_multiple_set_operations_integration(self, free_port, agent_thread, capsys):
        """Test multiple SET operations work correctly."""
        from src.snmp_manager import SNMPManager

        # Start agent
        agent, thread = agent_thread(free_port)
        time.sleep(0.1)
        
        manager = SNMPManager()
        
        # Set multiple writable values
        test_values = {
            '1.3.6.1.2.1.1.4.0': f'multi-contact-{random.randint(1000, 9999)}@test.com',
            '1.3.6.1.2.1.1.5.0': f'multi-router-{random.randint(1000, 9999)}',
            '1.3.6.1.2.1.1.6.0': f'Multi-Test Location {random.randint(1000, 9999)}'
        }
        
        # Perform SET operations
        for oid, value in test_values.items():
            manager.set('localhost', free_port, oid, 'string', value)
            captured = capsys.readouterr()
            assert 'Set operation successful:' in captured.out
            assert value in captured.out
        
        # Verify all values with GET
        manager.get('localhost', free_port, list(test_values.keys()))
        captured = capsys.readouterr()
        
        for oid, value in test_values.items():
            assert value in captured.out, f"Value for {oid} should be retrievable"
    
    @pytest.mark.bundle(2)
    @pytest.mark.points(4)
    def test_set_readonly_error_integration(self, free_port, agent_thread, capsys):
        """Test SET on read-only OID propagates error correctly."""
        from src.snmp_manager import SNMPManager

        # Start agent
        agent, thread = agent_thread(free_port)
        time.sleep(0.1)
        
        # Try to SET read-only OID (uptime)
        manager = SNMPManager()
        manager.set('localhost', free_port, '1.3.6.1.2.1.1.3.0', 'timeticks', '999999')
        
        # Verify error propagation
        captured = capsys.readouterr()
        assert 'Error: OID is read-only' in captured.out
    
    @pytest.mark.bundle(2)
    @pytest.mark.points(3)
    def test_set_nonexistent_oid_integration(self, free_port, agent_thread, capsys):
        """Test SET on non-existent OID propagates error correctly."""
        from src.snmp_manager import SNMPManager

        # Start agent
        agent, thread = agent_thread(free_port)
        time.sleep(0.1)
        
        # Try to SET non-existent OID
        manager = SNMPManager()
        manager.set('localhost', free_port, '9.8.7.6.5.4.3.2.1.0', 'string', 'test-value')
        
        # Verify error propagation
        captured = capsys.readouterr()
        assert 'Error: No such OID exists' in captured.out
    
    @pytest.mark.bundle(2)
    @pytest.mark.points(3)
    def test_set_type_mismatch_integration(self, free_port, agent_thread, capsys):
        """Test SET with wrong type propagates error correctly."""
        from src.snmp_manager import SNMPManager

        # Start agent
        agent, thread = agent_thread(free_port)
        time.sleep(0.1)
        
        # Try to SET string OID with integer type (sysContact expects STRING)
        manager = SNMPManager()
        manager.set('localhost', free_port, '1.3.6.1.2.1.1.4.0', 'integer', '12345')
        
        # Verify error propagation
        captured = capsys.readouterr()
        assert 'Error: Bad value for OID type' in captured.out
    
    @pytest.mark.bundle(2)
    @pytest.mark.points(3)
    def test_mixed_get_set_operations_integration(self, free_port, agent_thread, capsys):
        """Test mixing GET and SET operations in sequence."""
        from src.snmp_manager import SNMPManager

        # Start agent
        agent, thread = agent_thread(free_port)
        time.sleep(0.1)
        
        manager = SNMPManager()
        
        # Get initial value
        manager.get('localhost', free_port, ['1.3.6.1.2.1.1.5.0'])
        captured1 = capsys.readouterr()
        assert '1.3.6.1.2.1.1.5.0 =' in captured1.out
        
        # Set new value
        new_name = f'mixed-ops-test-{random.randint(1000, 9999)}'
        manager.set('localhost', free_port, '1.3.6.1.2.1.1.5.0', 'string', new_name)
        captured2 = capsys.readouterr()
        assert 'Set operation successful:' in captured2.out
        
        # Get updated value
        manager.get('localhost', free_port, ['1.3.6.1.2.1.1.5.0'])
        captured3 = capsys.readouterr()
        assert new_name in captured3.out
        
        # Get multiple values including the changed one
        manager.get('localhost', free_port, ['1.3.6.1.2.1.1.1.0', '1.3.6.1.2.1.1.5.0'])
        captured4 = capsys.readouterr()
        assert new_name in captured4.out
        assert '1.3.6.1.2.1.1.1.0 =' in captured4.out
    
    @pytest.mark.bundle(2)
    @pytest.mark.points(2)
    def test_request_response_correlation_integration(self, free_port, agent_thread):
        """Test that request IDs are properly correlated in responses."""
        import struct

        from src.snmp_manager import SNMPManager
        from src.snmp_protocol import GetRequest, unpack_message

        # Start agent
        agent, thread = agent_thread(free_port)
        time.sleep(0.1)
        
        # Create a socket and send request with specific ID
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            client_socket.settimeout(5.0)
            client_socket.connect(('localhost', free_port))
            
            # Send request with specific ID
            test_request_id = 0x12345678
            request = GetRequest(request_id=test_request_id, oids=['1.3.6.1.2.1.1.1.0'])
            request_bytes = request.pack()
            client_socket.send(request_bytes)
            
            # Receive response
            from src.snmp_protocol import receive_complete_message
            response_bytes = receive_complete_message(client_socket)
            response = unpack_message(response_bytes)
            
            # Verify request ID correlation
            assert response.request_id == test_request_id, \
                f"Response ID should match request ID: got {response.request_id:08x}, expected {test_request_id:08x}"
            
        finally:
            client_socket.close()


# ============================================================================
# BUNDLE 3 (A GRADE) - PRODUCTION SCENARIOS
# Concurrent clients, stress testing, and edge cases
# ============================================================================

class TestBundleAIntegrationAdvanced:
    """Bundle A tests for advanced SNMP integration scenarios"""
    
    @pytest.mark.bundle(3)
    @pytest.mark.points(5)
    def test_agent_persistence_across_operations(self, free_port, agent_thread, capsys):
        """Test that agent maintains state consistency across many operations."""
        from src.snmp_manager import SNMPManager

        # Start agent
        agent, thread = agent_thread(free_port)
        time.sleep(0.1)
        
        manager = SNMPManager()
        
        # Set initial values
        initial_values = {
            '1.3.6.1.2.1.1.4.0': f'persistence-contact-{random.randint(10000, 99999)}@test.com',
            '1.3.6.1.2.1.1.5.0': f'persistence-host-{random.randint(10000, 99999)}',
            '1.3.6.1.2.1.1.6.0': f'Persistence Location {random.randint(10000, 99999)}'
        }
        
        # Set all values
        for oid, value in initial_values.items():
            manager.set('localhost', free_port, oid, 'string', value)
            captured = capsys.readouterr()
            assert 'Set operation successful:' in captured.out
        
        # Perform many intervening operations
        for i in range(20):
            # GET operations on various OIDs
            manager.get('localhost', free_port, ['1.3.6.1.2.1.1.1.0'])  # sysDescr
            manager.get('localhost', free_port, ['1.3.6.1.2.1.1.3.0'])  # sysUpTime (changes)
            manager.get('localhost', free_port, [f'1.3.6.1.4.1.99.1.{(i % 25) + 1}.0'])  # Test OIDs
            capsys.readouterr()  # Clear output
        
        # Verify initial values still persist
        manager.get('localhost', free_port, list(initial_values.keys()))
        captured = capsys.readouterr()
        
        for oid, value in initial_values.items():
            assert value in captured.out, f"Initial value for {oid} should persist across many operations"
    
    @pytest.mark.bundle(3)
    @pytest.mark.points(5)
    def test_agent_error_recovery_integration(self, free_port, agent_thread, capsys):
        """Test agent recovery from various error conditions."""
        from src.snmp_manager import SNMPManager

        # Start agent
        agent, thread = agent_thread(free_port)
        time.sleep(0.1)
        
        manager = SNMPManager()
        
        # Create various error conditions and verify recovery
        error_scenarios = [
            # Non-existent OID
            ('1.2.3.4.5.6.7.8.9.0', 'No such OID exists'),
            # Read-only OID
            ('1.3.6.1.2.1.1.3.0', 'OID is read-only'),
            # Another non-existent OID
            ('9.8.7.6.5.4.3.2.1.0', 'No such OID exists'),
        ]
        
        for oid, expected_error in error_scenarios:
            if 'read-only' in expected_error:
                # SET operation on read-only OID
                manager.set('localhost', free_port, oid, 'timeticks', '12345')
            else:
                # GET operation on non-existent OID  
                manager.get('localhost', free_port, [oid])
                
            captured = capsys.readouterr()
            assert expected_error in captured.out, f"Should get expected error for {oid}"
        
        # Verify agent still works after errors
        manager.get('localhost', free_port, ['1.3.6.1.2.1.1.1.0'])
        captured = capsys.readouterr()
        assert '1.3.6.1.2.1.1.1.0 =' in captured.out, "Agent should recover and handle valid requests"
        
        # Verify SET still works after errors
        recovery_value = f'recovery-test-{random.randint(10000, 99999)}'
        manager.set('localhost', free_port, '1.3.6.1.2.1.1.4.0', 'string', recovery_value)
        captured = capsys.readouterr()
        assert 'Set operation successful:' in captured.out, "Agent should handle SET after errors"
        assert recovery_value in captured.out
    
    @pytest.mark.bundle(3)
    @pytest.mark.points(5)
    def test_full_protocol_compliance_integration(self, free_port, agent_thread, capsys):
        """Test comprehensive protocol compliance across various scenarios."""
        from src.snmp_manager import SNMPManager

        # Start agent
        agent, thread = agent_thread(free_port)
        time.sleep(0.1)
        
        manager = SNMPManager()
        
        # Test sequence: comprehensive protocol exercise
        test_sequence = [
            # Basic GET
            ('GET', ['1.3.6.1.2.1.1.1.0'], None, 'should contain system description'),
            
            # Multi-OID GET
            ('GET', ['1.3.6.1.2.1.1.1.0', '1.3.6.1.2.1.1.5.0'], None, 'should have 2 lines'),
            
            # SET writable value
            ('SET', '1.3.6.1.2.1.1.4.0', f'protocol-test-{random.randint(10000, 99999)}@test.org', 'Set operation successful'),
            
            # GET to verify SET
            ('GET', ['1.3.6.1.2.1.1.4.0'], None, 'should show updated contact'),
            
            # SET with type validation
            ('SET', '1.3.6.1.2.1.1.5.0', f'protocol-host-{random.randint(10000, 99999)}', 'Set operation successful'),
            
            # Error case: non-existent OID
            ('GET', ['9.8.7.6.5.4.3.2.1.0'], None, 'Error: No such OID exists'),
            
            # Error case: read-only SET
            ('SET', '1.3.6.1.2.1.1.3.0', '999999', 'Error: OID is read-only'),
            
            # Recovery: valid GET after error
            ('GET', ['1.3.6.1.2.1.1.1.0'], None, 'should work after errors'),
            
            # Dynamic value (uptime)
            ('GET', ['1.3.6.1.2.1.1.3.0'], None, 'should show current uptime'),
        ]
        
        previous_outputs = []
        
        for i, (operation, oid_or_list, value, expectation) in enumerate(test_sequence):
            if operation == 'GET':
                manager.get('localhost', free_port, oid_or_list)
            else:  # SET
                manager.set('localhost', free_port, oid_or_list, 'string', value)
            
            captured = capsys.readouterr()
            previous_outputs.append(captured.out)
            
            # Basic validation based on expectation
            if 'Error:' in expectation:
                assert 'Error:' in captured.out, f"Step {i+1}: {expectation}"
            elif 'Set operation successful' in expectation:
                assert 'Set operation successful:' in captured.out, f"Step {i+1}: {expectation}"
            elif 'should have 2 lines' in expectation:
                # Filter for lines containing OID responses (ignoring debug output)
                lines = [line for line in captured.out.split('\n') if '=' in line and '.' in line]
                assert len(lines) == 2, f"Step {i+1}: Should have exactly 2 OID response lines"
            elif 'should show updated contact' in expectation:
                # Check that the contact was actually updated
                set_value = test_sequence[2][2]  # Value from SET operation
                assert set_value in captured.out, f"Step {i+1}: Should show updated contact value"
            else:
                # Basic success check
                if operation == 'GET':
                    oid_str = oid_or_list[0] if isinstance(oid_or_list, list) else oid_or_list
                    assert oid_str in captured.out, f"Step {i+1}: Should contain requested OID"
        
        # Final verification: system should still be responsive
        manager.get('localhost', free_port, ['1.3.6.1.2.1.1.1.0'])
        final_output = capsys.readouterr()
        assert '1.3.6.1.2.1.1.1.0 =' in final_output.out, "System should remain responsive after full test sequence"