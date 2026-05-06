"""
Test suite for SNMP Agent Server functionality.
Organized by specification grading bundles for clear expectations.

Bundle 1 (C Grade): Core server functionality - socket lifecycle, basic request handling
Bundle 2 (B Grade): Intermediate features - SET operations, error handling, validation  
Bundle 3 (A Grade): Advanced features - concurrent operations, persistence, edge cases
"""

import random
import socket
import struct
import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


# ============================================================================
# BUNDLE 1 (C GRADE) - CORE SERVER FUNCTIONALITY
# Basic socket lifecycle and GET operations that all implementations must pass
# ============================================================================

class TestBundleCAgentCore:
    """Bundle C tests for core SNMP agent server functionality"""
    
    @pytest.mark.bundle(1)
    @pytest.mark.points(3)
    def test_agent_initialization(self):
        """Test that SNMPAgent initializes correctly with proper defaults."""
        from src.snmp_agent import SNMPAgent

        # Test default initialization
        agent = SNMPAgent()
        assert agent.port == 1161, "Default port should be 1161"
        assert agent.mib is not None, "MIB should be initialized"
        assert agent.start_time is not None, "Start time should be set"
        assert agent.server_socket is None, "Server socket should not be created yet"
        assert agent.running == True, "Agent should be marked as running initially"
        
        # Test custom port initialization
        custom_agent = SNMPAgent(port=2000)
        assert custom_agent.port == 2000, "Custom port should be set"
    
    @pytest.mark.bundle(1)
    @pytest.mark.points(4)
    def test_agent_socket_creation_and_binding(self, mock_socket):
        """Test server socket creation and binding process."""
        from src.snmp_agent import SNMPAgent
        
        agent = SNMPAgent(port=1161)
        
        # Mock the start method to only test socket setup without actual server loop
        with patch.object(agent, '_handle_client'):
            with patch('socket.socket', return_value=mock_socket):
                # Start in a thread to avoid blocking
                start_thread = threading.Thread(target=agent.start)
                start_thread.daemon = True
                start_thread.start()
                
                # Give it a moment to set up
                time.sleep(0.1)
                agent.running = False
                start_thread.join(timeout=1)
                
                # Verify socket operations were called correctly
                assert mock_socket.bind_address == ('', 1161), "Should bind to correct address"
                assert mock_socket.listening == True, "Socket should be in listening state"
    
    @pytest.mark.bundle(1)
    @pytest.mark.points(4)
    def test_agent_get_request_basic(self):
        """Test basic GET request processing."""
        import src.snmp_protocol as snmp_protocol
        from src.snmp_agent import SNMPAgent
        
        agent = SNMPAgent()
        
        # Test single OID GET request
        request = snmp_protocol.GetRequest(request_id=1234, oids=['1.3.6.1.2.1.1.1.0'])
        response = agent._handle_get_request(request)
        
        assert isinstance(response, snmp_protocol.GetResponse), "Should return GetResponse"
        assert response.request_id == 1234, "Request ID should match"
        assert response.error_code == snmp_protocol.ErrorCode.SUCCESS, "Should succeed for valid OID"
        assert len(response.bindings) == 1, "Should return one binding"
        
        oid, value_type, value = response.bindings[0]
        assert oid == '1.3.6.1.2.1.1.1.0', "OID should match request"
        assert isinstance(value, str), "sysDescr should be a string"
    
    @pytest.mark.bundle(1)
    @pytest.mark.points(3)
    def test_agent_get_request_multiple_oids(self):
        """Test GET request with multiple OIDs."""
        from src.snmp_agent import SNMPAgent
        from src.snmp_protocol import ErrorCode, GetRequest
        
        agent = SNMPAgent()
        
        # Test multiple OID GET request
        test_oids = [
            '1.3.6.1.2.1.1.1.0',  # sysDescr
            '1.3.6.1.2.1.1.5.0',  # sysName
            '1.3.6.1.2.1.1.6.0'   # sysLocation
        ]
        
        request = GetRequest(request_id=5678, oids=test_oids)
        response = agent._handle_get_request(request)
        
        assert response.request_id == 5678, "Request ID should match"
        assert response.error_code == ErrorCode.SUCCESS, "Should succeed"
        assert len(response.bindings) == 3, "Should return three bindings"
        
        # Verify all requested OIDs are present
        returned_oids = [binding[0] for binding in response.bindings]
        for oid in test_oids:
            assert oid in returned_oids, f"OID {oid} should be in response"
    
    @pytest.mark.bundle(1)
    @pytest.mark.points(3)
    def test_agent_get_request_nonexistent_oid(self):
        """Test GET request with non-existent OID returns proper error."""
        from src.snmp_agent import SNMPAgent
        from src.snmp_protocol import ErrorCode, GetRequest
        
        agent = SNMPAgent()
        
        # Request non-existent OID
        request = GetRequest(request_id=9999, oids=['1.2.3.4.5.6.7.8.9.0'])
        response = agent._handle_get_request(request)
        
        assert response.request_id == 9999, "Request ID should match"
        assert response.error_code == ErrorCode.NO_SUCH_OID, "Should return NO_SUCH_OID error"
        assert len(response.bindings) == 0, "Should return empty bindings on error"
    
    @pytest.mark.bundle(1)
    @pytest.mark.points(2)
    def test_agent_get_request_partial_failure(self):
        """Test all-or-nothing principle: if any OID fails, entire request fails."""
        from src.snmp_agent import SNMPAgent
        from src.snmp_protocol import ErrorCode, GetRequest
        
        agent = SNMPAgent()
        
        # Mix valid and invalid OIDs
        mixed_oids = [
            '1.3.6.1.2.1.1.1.0',     # Valid
            '1.2.3.4.5.6.7.8.9.0',   # Invalid
            '1.3.6.1.2.1.1.5.0'      # Valid
        ]
        
        request = GetRequest(request_id=4444, oids=mixed_oids)
        response = agent._handle_get_request(request)
        
        assert response.request_id == 4444, "Request ID should match"
        assert response.error_code == ErrorCode.NO_SUCH_OID, "Should fail due to invalid OID"
        assert len(response.bindings) == 0, "Should return no bindings on error"
    
    @pytest.mark.bundle(1)
    @pytest.mark.points(3)
    def test_agent_dynamic_value_updates(self):
        """Test that dynamic values (like uptime) are updated correctly."""
        from src.snmp_agent import SNMPAgent
        from src.snmp_protocol import ErrorCode, GetRequest
        
        agent = SNMPAgent()
        
        # Get uptime initially
        request = GetRequest(request_id=1111, oids=['1.3.6.1.2.1.1.3.0'])
        response1 = agent._handle_get_request(request)
        
        assert response1.error_code == ErrorCode.SUCCESS, "Should succeed"
        assert len(response1.bindings) == 1, "Should return one binding"
        
        initial_uptime = response1.bindings[0][2]
        
        # Wait a short time and get uptime again
        time.sleep(0.1)
        
        request2 = GetRequest(request_id=2222, oids=['1.3.6.1.2.1.1.3.0'])
        response2 = agent._handle_get_request(request2)
        
        assert response2.error_code == ErrorCode.SUCCESS, "Should succeed"
        second_uptime = response2.bindings[0][2]
        
        # Uptime should have increased
        assert second_uptime >= initial_uptime, "Uptime should increase over time"
        
        # It should be reasonable (not more than a few seconds difference)
        time_diff = second_uptime - initial_uptime
        assert time_diff < 1000, "Time difference should be reasonable (< 10 seconds in timeticks)"
    
    @pytest.mark.bundle(1)
    @pytest.mark.points(2)
    def test_agent_message_processing(self):
        """Test the message processing dispatcher."""
        from src.snmp_agent import SNMPAgent
        from src.snmp_protocol import GetRequest, GetResponse
        
        agent = SNMPAgent()
        
        # Create a GET request and pack it
        request = GetRequest(request_id=7777, oids=['1.3.6.1.2.1.1.1.0'])
        request_bytes = request.pack()
        
        # Process through dispatcher
        response_bytes = agent._process_message(request_bytes)
        
        # Should return valid response bytes
        assert isinstance(response_bytes, bytes), "Should return bytes"
        assert len(response_bytes) > 10, "Response should be reasonable size"
        
        # Verify it's a valid GetResponse by unpacking
        from src.snmp_protocol import unpack_message
        response = unpack_message(response_bytes)
        assert isinstance(response, GetResponse), "Should be GetResponse"
        assert response.request_id == 7777, "Request ID should match"


# ============================================================================
# BUNDLE 2 (B GRADE) - INTERMEDIATE FEATURES
# SET operations, error handling, and validation logic
# ============================================================================

class TestBundleBAgentIntermediate:
    """Bundle B tests for intermediate SNMP agent features"""
    
    @pytest.mark.bundle(2)
    @pytest.mark.points(4)
    def test_agent_set_request_basic(self):
        """Test basic SET request processing."""
        from src.snmp_agent import SNMPAgent
        from src.snmp_protocol import (ErrorCode, GetResponse, SetRequest,
                                       ValueType)
        
        agent = SNMPAgent()
        
        # Test setting a writable OID (sysContact)
        bindings = [('1.3.6.1.2.1.1.4.0', ValueType.STRING, 'newadmin@test.com')]
        request = SetRequest(request_id=3333, bindings=bindings)
        response = agent._handle_set_request(request)
        
        assert isinstance(response, GetResponse), "SET should return GetResponse"
        assert response.request_id == 3333, "Request ID should match"
        assert response.error_code == ErrorCode.SUCCESS, "Should succeed for writable OID"
        assert len(response.bindings) == 1, "Should return one binding"
        
        # Verify the value was actually set
        oid, value_type, value = response.bindings[0]
        assert oid == '1.3.6.1.2.1.1.4.0', "OID should match"
        assert value == 'newadmin@test.com', "Value should be set correctly"
        
        # Verify it persists in MIB
        assert agent.mib['1.3.6.1.2.1.1.4.0'][1] == 'newadmin@test.com', "MIB should be updated"
    
    @pytest.mark.bundle(2)
    @pytest.mark.points(3)
    def test_agent_set_request_multiple_bindings(self):
        """Test SET request with multiple varbinds."""
        from src.snmp_agent import SNMPAgent
        from src.snmp_protocol import ErrorCode, SetRequest, ValueType
        
        agent = SNMPAgent()
        
        # Test setting multiple writable OIDs
        bindings = [
            ('1.3.6.1.2.1.1.4.0', ValueType.STRING, 'contact@example.org'),
            ('1.3.6.1.2.1.1.5.0', ValueType.STRING, 'test-router-42'),
            ('1.3.6.1.2.1.1.6.0', ValueType.STRING, 'Lab Building, Room 101')
        ]
        
        request = SetRequest(request_id=6666, bindings=bindings)
        response = agent._handle_set_request(request)
        
        assert response.request_id == 6666, "Request ID should match"
        assert response.error_code == ErrorCode.SUCCESS, "Should succeed"
        assert len(response.bindings) == 3, "Should return three bindings"
        
        # Verify all values were set
        for i, (orig_oid, orig_type, orig_value) in enumerate(bindings):
            resp_oid, resp_type, resp_value = response.bindings[i]
            assert resp_oid == orig_oid, f"OID {i} should match"
            assert resp_value == orig_value, f"Value {i} should be set correctly"
            
            # Verify in MIB
            assert agent.mib[orig_oid][1] == orig_value, f"MIB should be updated for {orig_oid}"
    
    @pytest.mark.bundle(2)
    @pytest.mark.points(3)
    def test_agent_set_request_read_only_error(self):
        """Test SET request on read-only OID returns proper error."""
        from src.snmp_agent import SNMPAgent
        from src.snmp_protocol import ErrorCode, SetRequest, ValueType
        
        agent = SNMPAgent()
        
        # Try to set a read-only OID (sysUpTime)
        bindings = [('1.3.6.1.2.1.1.3.0', ValueType.TIMETICKS, 999999)]
        request = SetRequest(request_id=8888, bindings=bindings)
        response = agent._handle_set_request(request)
        
        assert response.request_id == 8888, "Request ID should match"
        assert response.error_code == ErrorCode.READ_ONLY, "Should return READ_ONLY error"
        assert len(response.bindings) == 0, "Should return empty bindings on error"
    
    @pytest.mark.bundle(2)
    @pytest.mark.points(3)
    def test_agent_set_request_nonexistent_oid(self):
        """Test SET request on non-existent OID returns proper error."""
        from src.snmp_agent import SNMPAgent
        from src.snmp_protocol import ErrorCode, SetRequest, ValueType
        
        agent = SNMPAgent()
        
        # Try to set non-existent OID
        bindings = [('9.8.7.6.5.4.3.2.1.0', ValueType.STRING, 'test')]
        request = SetRequest(request_id=9999, bindings=bindings)
        response = agent._handle_set_request(request)
        
        assert response.request_id == 9999, "Request ID should match"
        assert response.error_code == ErrorCode.NO_SUCH_OID, "Should return NO_SUCH_OID error"
        assert len(response.bindings) == 0, "Should return empty bindings on error"
    
    @pytest.mark.bundle(2)
    @pytest.mark.points(4)
    def test_agent_set_request_type_validation(self):
        """Test SET request with wrong type returns proper error."""
        from src.snmp_agent import SNMPAgent
        from src.snmp_protocol import ErrorCode, SetRequest, ValueType
        
        agent = SNMPAgent()
        
        # Try to set string OID with integer type (sysContact expects STRING)
        bindings = [('1.3.6.1.2.1.1.4.0', ValueType.INTEGER, 12345)]
        request = SetRequest(request_id=7777, bindings=bindings)
        response = agent._handle_set_request(request)
        
        assert response.request_id == 7777, "Request ID should match"
        assert response.error_code == ErrorCode.BAD_VALUE, "Should return BAD_VALUE error"
        assert len(response.bindings) == 0, "Should return empty bindings on error"
    
    @pytest.mark.bundle(2)
    @pytest.mark.points(4)
    def test_agent_set_request_all_or_nothing(self):
        """Test all-or-nothing principle for SET operations."""
        from src.snmp_agent import SNMPAgent
        from src.snmp_protocol import ErrorCode, SetRequest, ValueType
        
        agent = SNMPAgent()
        
        # Store original values
        original_contact = agent.mib['1.3.6.1.2.1.1.4.0'][1]
        original_name = agent.mib['1.3.6.1.2.1.1.5.0'][1]
        
        # Mix valid and invalid operations
        bindings = [
            ('1.3.6.1.2.1.1.4.0', ValueType.STRING, 'should-not-be-set'),  # Valid
            ('1.3.6.1.2.1.1.3.0', ValueType.TIMETICKS, 999),  # Invalid (read-only)
            ('1.3.6.1.2.1.1.5.0', ValueType.STRING, 'also-should-not-be-set')  # Valid
        ]
        
        request = SetRequest(request_id=5555, bindings=bindings)
        response = agent._handle_set_request(request)
        
        assert response.request_id == 5555, "Request ID should match"
        assert response.error_code == ErrorCode.READ_ONLY, "Should fail due to read-only OID"
        assert len(response.bindings) == 0, "Should return no bindings on error"
        
        # Verify NO values were changed
        assert agent.mib['1.3.6.1.2.1.1.4.0'][1] == original_contact, "Contact should be unchanged"
        assert agent.mib['1.3.6.1.2.1.1.5.0'][1] == original_name, "Name should be unchanged"
    
    @pytest.mark.bundle(2)
    @pytest.mark.points(2)
    def test_agent_value_type_conversion(self):
        """Test helper method for value type conversion."""
        from src.snmp_agent import SNMPAgent
        from src.snmp_protocol import ValueType
        
        agent = SNMPAgent()
        
        # Test type string to ValueType conversions
        assert agent._get_value_type('INTEGER') == ValueType.INTEGER
        assert agent._get_value_type('STRING') == ValueType.STRING
        assert agent._get_value_type('COUNTER') == ValueType.COUNTER
        assert agent._get_value_type('TIMETICKS') == ValueType.TIMETICKS
        
        # Test default case (unknown type defaults to STRING)
        assert agent._get_value_type('UNKNOWN') == ValueType.STRING
    
    @pytest.mark.bundle(2)
    @pytest.mark.points(3)
    def test_agent_error_handling_in_message_processing(self):
        """Test error handling in the message processing dispatcher."""
        from src.snmp_agent import SNMPAgent
        
        agent = SNMPAgent()
        
        # Test with invalid message bytes
        with pytest.raises((ValueError, struct.error)):
            agent._process_message(b"invalid message data")
        
        # Test with truncated message
        with pytest.raises((ValueError, IndexError, struct.error)):
            agent._process_message(b"short")


# ============================================================================
# BUNDLE 3 (A GRADE) - ADVANCED FEATURES  
# Concurrent operations, edge cases, and production-ready features
# ============================================================================

class TestBundleAAgentAdvanced:
    """Bundle A tests for advanced SNMP agent features"""
    
    @pytest.mark.bundle(3)
    @pytest.mark.points(3)
    def test_agent_large_request_handling(self):
        """Test agent handling of large requests (many OIDs)."""
        from src.snmp_agent import SNMPAgent
        from src.snmp_protocol import ErrorCode, GetRequest
        
        agent = SNMPAgent()
        
        # Create a large request with many valid OIDs
        large_oid_list = []
        for i in range(15):  # 15 OIDs - reasonable for educational testing
            large_oid_list.append(f'1.3.6.1.4.1.99.1.{i+1}.0')  # Test OIDs from MIB
        
        request = GetRequest(request_id=8000, oids=large_oid_list)
        response = agent._handle_get_request(request)
        
        assert response.request_id == 8000, "Request ID should match"
        assert response.error_code == ErrorCode.SUCCESS, "Should handle large requests"
        assert len(response.bindings) == 15, "Should return all requested bindings"
        
        # Verify response structure
        for i, (oid, value_type, value) in enumerate(response.bindings):
            expected_oid = f'1.3.6.1.4.1.99.1.{i+1}.0'
            assert oid == expected_oid, f"OID {i} should match expected"
            assert isinstance(value, str), f"Value {i} should be string"
    
    @pytest.mark.bundle(3)
    @pytest.mark.points(3)
    def test_agent_stress_set_operations(self):
        """Test agent under stress with multiple SET operations."""
        from src.snmp_agent import SNMPAgent
        from src.snmp_protocol import ErrorCode, SetRequest, ValueType
        
        agent = SNMPAgent()
        
        # Perform multiple SET operations rapidly
        for i in range(10):  # Reduced from 20 to 10 for educational appropriateness
            bindings = [
                ('1.3.6.1.2.1.1.4.0', ValueType.STRING, f'contact-{i}@test.com'),
                ('1.3.6.1.2.1.1.5.0', ValueType.STRING, f'router-{i}'),
                ('1.3.6.1.2.1.1.6.0', ValueType.STRING, f'Location {i}')
            ]
            
            request = SetRequest(request_id=9000+i, bindings=bindings)
            response = agent._handle_set_request(request)
            
            assert response.request_id == 9000+i, f"Request ID should match for iteration {i}"
            assert response.error_code == ErrorCode.SUCCESS, f"SET should succeed for iteration {i}"
            
            # Verify values were set correctly
            for j, (oid, vtype, value) in enumerate(bindings):
                assert agent.mib[oid][1] == value, f"MIB should be updated correctly for {oid} in iteration {i}"
    
    @pytest.mark.bundle(3)
    @pytest.mark.points(3)
    def test_agent_edge_case_empty_requests(self):
        """Test agent handling of edge cases like empty requests."""
        from src.snmp_agent import SNMPAgent
        from src.snmp_protocol import ErrorCode, GetRequest, SetRequest
        
        agent = SNMPAgent()
        
        # Test GET request with empty OID list
        empty_get_request = GetRequest(request_id=1001, oids=[])
        response = agent._handle_get_request(empty_get_request)
        
        assert response.request_id == 1001, "Request ID should match"
        assert response.error_code == ErrorCode.SUCCESS, "Empty GET should succeed"
        assert len(response.bindings) == 0, "Should return empty bindings"
        
        # Test SET request with empty bindings list
        empty_set_request = SetRequest(request_id=1002, bindings=[])
        response = agent._handle_set_request(empty_set_request)
        
        assert response.request_id == 1002, "Request ID should match"
        assert response.error_code == ErrorCode.SUCCESS, "Empty SET should succeed"
        assert len(response.bindings) == 0, "Should return empty bindings"
    
    @pytest.mark.bundle(3)
    @pytest.mark.points(4)
    def test_agent_uptime_accuracy(self):
        """Test accuracy and consistency of uptime calculations."""
        from src.snmp_agent import SNMPAgent
        from src.snmp_protocol import ErrorCode, GetRequest
        
        agent = SNMPAgent()
        
        # Record initial time
        start_time = time.time()
        
        # Get multiple uptime readings
        uptimes = []
        timestamps = []
        
        for i in range(5):
            timestamp = time.time()
            request = GetRequest(request_id=1100+i, oids=['1.3.6.1.2.1.1.3.0'])
            response = agent._handle_get_request(request)
            
            assert response.error_code == ErrorCode.SUCCESS, "Should succeed"
            uptime_ticks = response.bindings[0][2]
            
            uptimes.append(uptime_ticks)
            timestamps.append(timestamp)
            
            time.sleep(0.05)  # 50ms between readings
        
        # Verify uptimes are monotonically increasing
        for i in range(1, len(uptimes)):
            assert uptimes[i] >= uptimes[i-1], f"Uptime should increase: {uptimes[i-1]} -> {uptimes[i]}"
        
        # Verify uptime is approximately correct (within reasonable tolerance)
        for i, (uptime_ticks, timestamp) in enumerate(zip(uptimes, timestamps)):
            expected_ticks = int((timestamp - agent.start_time) * 100)  # Convert to timeticks
            tolerance = 10  # Allow 10 timeticks (0.1 second) tolerance
            
            assert abs(uptime_ticks - expected_ticks) <= tolerance, \
                f"Uptime reading {i} should be accurate: got {uptime_ticks}, expected ~{expected_ticks}"
    
    @pytest.mark.bundle(3)
    @pytest.mark.points(3)
    def test_agent_mib_data_integrity(self):
        """Test that MIB data maintains integrity under various operations."""
        from src.snmp_agent import SNMPAgent
        from src.snmp_protocol import (ErrorCode, GetRequest, SetRequest,
                                       ValueType)
        
        agent = SNMPAgent()
        
        # Store original MIB state
        original_mib = dict(agent.mib)
        
        # Perform various SET operations
        test_values = [
            ('1.3.6.1.2.1.1.4.0', 'integrity-test-1'),
            ('1.3.6.1.2.1.1.5.0', 'integrity-test-2'),
            ('1.3.6.1.2.1.1.6.0', 'integrity-test-3')
        ]
        
        for oid, value in test_values:
            # SET the value
            bindings = [(oid, ValueType.STRING, value)]
            set_request = SetRequest(request_id=1200, bindings=bindings)
            set_response = agent._handle_set_request(set_request)
            
            assert set_response.error_code == ErrorCode.SUCCESS, f"SET should succeed for {oid}"
            
            # Verify with GET
            get_request = GetRequest(request_id=1201, oids=[oid])
            get_response = agent._handle_get_request(get_request)
            
            assert get_response.error_code == ErrorCode.SUCCESS, f"GET should succeed for {oid}"
            retrieved_value = get_response.bindings[0][2]
            assert retrieved_value == value, f"Retrieved value should match SET value for {oid}"
        
        # Verify read-only values haven't changed
        readonly_oids = ['1.3.6.1.2.1.1.1.0', '1.3.6.1.2.1.1.2.0', '1.3.6.1.2.1.1.7.0']
        for oid in readonly_oids:
            current_value = agent.mib[oid][1]
            original_value = original_mib[oid][1]
            # Skip uptime (1.3.6.1.2.1.1.3.0) as it legitimately changes
            if oid != '1.3.6.1.2.1.1.3.0':
                assert current_value == original_value, f"Read-only OID {oid} should not have changed"
    
    @pytest.mark.bundle(3)
    @pytest.mark.points(2)
    def test_agent_request_id_handling(self):
        """Test that agent correctly handles and preserves request IDs."""
        from src.snmp_agent import SNMPAgent
        from src.snmp_protocol import GetRequest, SetRequest, ValueType
        
        agent = SNMPAgent()
        
        # Test with various request ID values
        test_request_ids = [0, 1, 65535, 4294967295, 2147483647]  # Edge cases for 32-bit integers
        
        for req_id in test_request_ids:
            # Test GET request
            get_request = GetRequest(request_id=req_id, oids=['1.3.6.1.2.1.1.1.0'])
            get_response = agent._handle_get_request(get_request)
            assert get_response.request_id == req_id, f"GET request ID should be preserved: {req_id}"
            
            # Test SET request (on writable OID)
            bindings = [('1.3.6.1.2.1.1.4.0', ValueType.STRING, f'test-{req_id}')]
            set_request = SetRequest(request_id=req_id, bindings=bindings)
            set_response = agent._handle_set_request(set_request)
            assert set_response.request_id == req_id, f"SET request ID should be preserved: {req_id}"
    
    @pytest.mark.bundle(3)
    @pytest.mark.points(3)
    def test_agent_malformed_message_handling(self):
        """Test agent resilience against malformed messages."""
        from src.snmp_agent import SNMPAgent
        
        agent = SNMPAgent()
        
        # Test various malformed message scenarios
        malformed_messages = [
            b'',                           # Empty message
            b'short',                      # Too short
            b'\x00\x00\x00\x08\x00\x00\x00\x01\xFF',  # Invalid PDU type
            b'\x00\x00\x00\x05\x00\x00',  # Truncated message
        ]
        
        for malformed_msg in malformed_messages:
            with pytest.raises((ValueError, IndexError, struct.error)):
                agent._process_message(malformed_msg)