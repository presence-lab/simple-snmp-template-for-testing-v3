"""
Test suite for SNMP Manager Client functionality.
Organized by specification grading bundles for clear expectations.

Bundle 1 (C Grade): Core client functionality - socket lifecycle, GET operations
Bundle 2 (B Grade): Intermediate features - SET operations, timeout handling, error recovery
Bundle 3 (A Grade): Advanced features - connection management, display formatting, edge cases
"""

import random
import socket
import struct
import sys
import threading
import time
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


# ============================================================================
# BUNDLE 1 (C GRADE) - CORE CLIENT FUNCTIONALITY
# Basic socket operations and GET requests that all implementations must pass
# ============================================================================

class TestBundleCManagerCore:
    """Bundle C tests for core SNMP manager client functionality"""
    
    @pytest.mark.bundle(1)
    @pytest.mark.points(2)
    def test_manager_initialization(self):
        """Test that SNMPManager initializes correctly."""
        from src.snmp_manager import SNMPManager
        
        manager = SNMPManager()
        assert hasattr(manager, 'request_id'), "Manager should have request_id attribute"
        assert isinstance(manager.request_id, int), "Request ID should be integer"
        assert 1 <= manager.request_id <= 10000, "Initial request ID should be in valid range"
    
    @pytest.mark.bundle(1)
    @pytest.mark.points(4)
    def test_manager_get_operation_basic(self, mock_socket, capsys):
        """Test basic GET operation with single OID."""
        from src.snmp_manager import SNMPManager
        from src.snmp_protocol import ErrorCode, GetResponse, ValueType
        
        manager = SNMPManager()
        
        # Create dynamic response that matches sent request ID
        def custom_recv(size):
            if mock_socket.sent_data:
                sent_bytes = mock_socket.sent_data[0]
                if len(sent_bytes) >= 8:
                    _, _, _, request_id = struct.unpack('!BBHI', sent_bytes[:8])
                    test_response = GetResponse(
                        request_id=request_id,
                        error_code=ErrorCode.SUCCESS,
                        bindings=[('1.3.6.1.2.1.1.1.0', ValueType.STRING, 'Test System Description')]
                    )
                    return test_response.pack()
            return b''
        
        mock_socket.recv = custom_recv
        
        with patch('socket.socket', return_value=mock_socket):
            manager.get('localhost', 1161, ['1.3.6.1.2.1.1.1.0'])
        
        # Verify output
        captured = capsys.readouterr()
        assert '1.3.6.1.2.1.1.1.0 = Test System Description' in captured.out
    
    @pytest.mark.bundle(1)
    @pytest.mark.points(4)
    def test_manager_get_operation_multiple_oids(self, mock_socket, capsys):
        """Test GET operation with multiple OIDs."""
        from src.snmp_manager import SNMPManager
        from src.snmp_protocol import ErrorCode, GetResponse, ValueType
        
        manager = SNMPManager()
        
        # Create dynamic response with multiple bindings
        def custom_recv(size):
            if mock_socket.sent_data:
                sent_bytes = mock_socket.sent_data[0]
                if len(sent_bytes) >= 8:
                    _, _, _, request_id = struct.unpack('!BBHI', sent_bytes[:8])
                    test_response = GetResponse(
                        request_id=request_id,
                        error_code=ErrorCode.SUCCESS,
                        bindings=[
                            ('1.3.6.1.2.1.1.1.0', ValueType.STRING, 'Test Description'),
                            ('1.3.6.1.2.1.1.5.0', ValueType.STRING, 'test-host'),
                            ('1.3.6.1.2.1.1.3.0', ValueType.TIMETICKS, 123456)
                        ]
                    )
                    return test_response.pack()
            return b''
        
        mock_socket.recv = custom_recv
        
        with patch('socket.socket', return_value=mock_socket):
            manager.get('localhost', 1161, ['1.3.6.1.2.1.1.1.0', '1.3.6.1.2.1.1.5.0', '1.3.6.1.2.1.1.3.0'])
        
        # Verify all OIDs in output
        captured = capsys.readouterr()
        assert '1.3.6.1.2.1.1.1.0 = Test Description' in captured.out
        assert '1.3.6.1.2.1.1.5.0 = test-host' in captured.out
        assert '1.3.6.1.2.1.1.3.0 = 123456' in captured.out
    
    @pytest.mark.bundle(1)
    @pytest.mark.points(3)
    def test_manager_get_operation_error_response(self, mock_socket, capsys):
        """Test GET operation with error response."""
        from src.snmp_manager import SNMPManager
        from src.snmp_protocol import ErrorCode, GetResponse
        
        manager = SNMPManager()
        
        # Create dynamic error response
        def custom_recv(size):
            if mock_socket.sent_data:
                sent_bytes = mock_socket.sent_data[0]
                if len(sent_bytes) >= 8:
                    _, _, _, request_id = struct.unpack('!BBHI', sent_bytes[:8])
                    error_response = GetResponse(
                        request_id=request_id,
                        error_code=ErrorCode.NO_SUCH_OID,
                        bindings=[]
                    )
                    return error_response.pack()
            return b''
        
        mock_socket.recv = custom_recv
        
        with patch('socket.socket', return_value=mock_socket):
            manager.get('localhost', 1161, ['9.8.7.6.5.4.3.2.1.0'])
        
        # Verify error message
        captured = capsys.readouterr()
        assert 'Error: No such OID exists' in captured.out
    
    @pytest.mark.bundle(1)
    @pytest.mark.points(2)
    def test_manager_connection_error_handling(self, capsys):
        """Test connection error handling."""
        from src.snmp_manager import SNMPManager
        
        manager = SNMPManager()
        
        # Mock connection refused
        with patch('socket.socket') as mock_sock_class:
            mock_sock_class.return_value.connect.side_effect = ConnectionRefusedError
            
            manager.get('localhost', 9999, ['1.3.6.1.2.1.1.1.0'])
        
        # Verify error message
        captured = capsys.readouterr()
        assert 'Cannot connect to localhost:9999' in captured.out
        assert 'is the agent running?' in captured.out
    
    @pytest.mark.bundle(1)
    @pytest.mark.points(2)
    def test_manager_timeout_handling(self, capsys):
        """Test timeout error handling."""
        from src.snmp_manager import SNMPManager
        
        manager = SNMPManager()
        
        # Mock timeout
        with patch('socket.socket') as mock_sock_class:
            mock_socket = mock_sock_class.return_value
            mock_socket.connect = MagicMock()
            mock_socket.send = MagicMock()
            mock_socket.recv.side_effect = socket.timeout
            
            manager.get('localhost', 1161, ['1.3.6.1.2.1.1.1.0'])
        
        # Verify timeout message
        captured = capsys.readouterr()
        assert 'Request timed out' in captured.out
        assert '10' in captured.out  # Default timeout value


# ============================================================================
# BUNDLE 2 (B GRADE) - INTERMEDIATE FEATURES
# SET operations, value type handling, and enhanced error handling
# ============================================================================

class TestBundleBManagerIntermediate:
    """Bundle B tests for intermediate SNMP manager features"""
    
    @pytest.mark.bundle(2)
    @pytest.mark.points(4)
    def test_manager_set_operation_basic(self, mock_socket, capsys):
        """Test basic SET operation."""
        from src.snmp_manager import SNMPManager
        from src.snmp_protocol import ErrorCode, GetResponse, ValueType
        
        manager = SNMPManager()
        
        # Create dynamic successful SET response
        def custom_recv(size):
            if mock_socket.sent_data:
                sent_bytes = mock_socket.sent_data[0]
                if len(sent_bytes) >= 8:
                    _, _, _, request_id = struct.unpack('!BBHI', sent_bytes[:8])
                    set_response = GetResponse(
                        request_id=request_id,
                        error_code=ErrorCode.SUCCESS,
                        bindings=[('1.3.6.1.2.1.1.4.0', ValueType.STRING, 'newadmin@test.com')]
                    )
                    return set_response.pack()
            return b''
        
        mock_socket.recv = custom_recv
        
        with patch('socket.socket', return_value=mock_socket):
            manager.set('localhost', 1161, '1.3.6.1.2.1.1.4.0', 'string', 'newadmin@test.com')
        
        # Verify successful SET output
        captured = capsys.readouterr()
        assert 'Set operation successful:' in captured.out
        assert '1.3.6.1.2.1.1.4.0 = newadmin@test.com' in captured.out
    
    @pytest.mark.bundle(2)
    @pytest.mark.points(3)
    def test_manager_set_operation_integer_values(self, mock_socket, capsys):
        """Test SET operation with integer values."""
        from src.snmp_manager import SNMPManager
        from src.snmp_protocol import ErrorCode, GetResponse, ValueType
        
        manager = SNMPManager()
        
        # Create dynamic integer SET response
        def custom_recv(size):
            if mock_socket.sent_data:
                sent_bytes = mock_socket.sent_data[0]
                if len(sent_bytes) >= 8:
                    _, _, _, request_id = struct.unpack('!BBHI', sent_bytes[:8])
                    set_response = GetResponse(
                        request_id=request_id,
                        error_code=ErrorCode.SUCCESS,
                        bindings=[('1.3.6.1.2.1.2.1.0', ValueType.INTEGER, 42)]
                    )
                    return set_response.pack()
            return b''
        
        mock_socket.recv = custom_recv
        
        with patch('socket.socket', return_value=mock_socket):
            manager.set('localhost', 1161, '1.3.6.1.2.1.2.1.0', 'integer', '42')
        
        # Verify output
        captured = capsys.readouterr()
        assert 'Set operation successful:' in captured.out
        assert '1.3.6.1.2.1.2.1.0 = 42' in captured.out
    
    @pytest.mark.bundle(2)
    @pytest.mark.points(3)
    def test_manager_set_operation_counter_values(self, mock_socket, capsys):
        """Test SET operation with counter values."""
        from src.snmp_manager import SNMPManager
        from src.snmp_protocol import ErrorCode, GetResponse, ValueType
        
        manager = SNMPManager()
        
        # Create dynamic counter SET response
        def custom_recv(size):
            if mock_socket.sent_data:
                sent_bytes = mock_socket.sent_data[0]
                if len(sent_bytes) >= 8:
                    _, _, _, request_id = struct.unpack('!BBHI', sent_bytes[:8])
                    set_response = GetResponse(
                        request_id=request_id,
                        error_code=ErrorCode.SUCCESS,
                        bindings=[('1.3.6.1.4.1.99.1.1.0', ValueType.COUNTER, 1234567)]
                    )
                    return set_response.pack()
            return b''
        
        mock_socket.recv = custom_recv
        
        with patch('socket.socket', return_value=mock_socket):
            manager.set('localhost', 1161, '1.3.6.1.4.1.99.1.1.0', 'counter', '1234567')
        
        # Verify output with proper formatting
        captured = capsys.readouterr()
        assert 'Set operation successful:' in captured.out
        assert '1,234,567' in captured.out  # Counter should have thousands separators
    
    @pytest.mark.bundle(2)
    @pytest.mark.points(3)
    def test_manager_set_operation_timeticks_values(self, mock_socket, capsys):
        """Test SET operation with timeticks values."""
        from src.snmp_manager import SNMPManager
        from src.snmp_protocol import ErrorCode, GetResponse, ValueType
        
        manager = SNMPManager()
        
        # Create dynamic timeticks SET response
        def custom_recv(size):
            if mock_socket.sent_data:
                sent_bytes = mock_socket.sent_data[0]
                if len(sent_bytes) >= 8:
                    _, _, _, request_id = struct.unpack('!BBHI', sent_bytes[:8])
                    set_response = GetResponse(
                        request_id=request_id,
                        error_code=ErrorCode.SUCCESS,
                        bindings=[('1.3.6.1.4.1.99.1.2.0', ValueType.TIMETICKS, 360000)]  # 1 hour
                    )
                    return set_response.pack()
            return b''
        
        mock_socket.recv = custom_recv
        
        with patch('socket.socket', return_value=mock_socket):
            manager.set('localhost', 1161, '1.3.6.1.4.1.99.1.2.0', 'timeticks', '360000')
        
        # Verify output with time formatting
        captured = capsys.readouterr()
        assert 'Set operation successful:' in captured.out
        assert '360000' in captured.out
        assert '1 hours' in captured.out  # Should show human-readable time
    
    @pytest.mark.bundle(2)
    @pytest.mark.points(3)
    def test_manager_set_operation_error_responses(self, mock_socket, capsys):
        """Test SET operation error handling."""
        from src.snmp_manager import SNMPManager
        from src.snmp_protocol import ErrorCode, GetResponse
        
        manager = SNMPManager()
        
        # Create dynamic READ_ONLY error response
        def custom_recv(size):
            if mock_socket.sent_data:
                sent_bytes = mock_socket.sent_data[0]
                if len(sent_bytes) >= 8:
                    _, _, _, request_id = struct.unpack('!BBHI', sent_bytes[:8])
                    readonly_response = GetResponse(
                        request_id=request_id,
                        error_code=ErrorCode.READ_ONLY,
                        bindings=[]
                    )
                    return readonly_response.pack()
            return b''
        
        mock_socket.recv = custom_recv
        
        with patch('socket.socket', return_value=mock_socket):
            manager.set('localhost', 1161, '1.3.6.1.2.1.1.3.0', 'timeticks', '12345')
        
        # Verify error message
        captured = capsys.readouterr()
        assert 'Error: OID is read-only' in captured.out
    
    @pytest.mark.bundle(2)
    @pytest.mark.points(3)
    def test_manager_set_value_type_validation(self, capsys):
        """Test SET operation value type validation."""
        from src.snmp_manager import SNMPManager
        
        manager = SNMPManager()
        
        # Test invalid value type
        manager.set('localhost', 1161, '1.3.6.1.2.1.1.4.0', 'invalid_type', 'value')
        
        captured = capsys.readouterr()
        assert 'Invalid value type' in captured.out
        assert 'invalid_type' in captured.out
    
    @pytest.mark.bundle(2)
    @pytest.mark.points(3)
    def test_manager_set_value_conversion_errors(self, capsys):
        """Test SET operation value conversion error handling."""
        from src.snmp_manager import SNMPManager
        
        manager = SNMPManager()
        
        # Test invalid integer conversion
        manager.set('localhost', 1161, '1.3.6.1.2.1.2.1.0', 'integer', 'not_a_number')
        
        captured = capsys.readouterr()
        assert 'Cannot convert' in captured.out
        assert 'not_a_number' in captured.out
        assert 'integer' in captured.out
    
    @pytest.mark.bundle(2)
    @pytest.mark.points(2)
    def test_manager_set_negative_counter_validation(self, capsys):
        """Test SET operation counter/timeticks negative value validation."""
        from src.snmp_manager import SNMPManager
        
        manager = SNMPManager()
        
        # Test negative counter value
        manager.set('localhost', 1161, '1.3.6.1.4.1.99.1.1.0', 'counter', '-123')
        
        captured = capsys.readouterr()
        assert 'Counter values must be >= 0' in captured.out
        
        # Test negative timeticks value
        manager.set('localhost', 1161, '1.3.6.1.4.1.99.1.2.0', 'timeticks', '-456')
        
        captured = capsys.readouterr()
        assert 'Timeticks values must be >= 0' in captured.out


# ============================================================================
# BUNDLE 3 (A GRADE) - ADVANCED FEATURES
# Advanced formatting, connection management, and comprehensive edge cases
# ============================================================================

class TestBundleAManagerAdvanced:
    """Bundle A tests for advanced SNMP manager features"""
    
    @pytest.mark.bundle(3)
    @pytest.mark.points(3)
    def test_manager_value_formatting_comprehensive(self, mock_socket, capsys):
        """Test comprehensive value formatting for all types."""
        from src.snmp_manager import SNMPManager
        from src.snmp_protocol import ErrorCode, GetResponse, ValueType, GetRequest
        
        manager = SNMPManager()
        
        # Create a custom recv method that extracts request ID from sent data
        def custom_recv(size):
            if mock_socket.sent_data:
                # Extract request ID from the sent request
                sent_bytes = mock_socket.sent_data[0]
                # Unpack just the first 8 bytes to get version, pdu_type, reserved, request_id
                if len(sent_bytes) >= 8:
                    _, _, _, request_id = struct.unpack('!BBHI', sent_bytes[:8])
                    # Create response with matching request ID
                    test_response = GetResponse(
                        request_id=request_id,
                        error_code=ErrorCode.SUCCESS,
                        bindings=[
                            ('1.3.6.1.2.1.1.1.0', ValueType.STRING, 'Test String'),
                            ('1.3.6.1.2.1.1.7.0', ValueType.INTEGER, 42),
                            ('1.3.6.1.2.1.2.2.1.10.1', ValueType.COUNTER, 123456789),
                            ('1.3.6.1.2.1.1.3.0', ValueType.TIMETICKS, 86400000),  # 1 day in timeticks
                        ]
                    )
                    return test_response.pack()
            return b''
        
        mock_socket.recv = custom_recv
        
        with patch('socket.socket', return_value=mock_socket):
            manager.get('localhost', 1161, ['1.3.6.1.2.1.1.1.0', '1.3.6.1.2.1.1.7.0', 
                                          '1.3.6.1.2.1.2.2.1.10.1', '1.3.6.1.2.1.1.3.0'])
        
        captured = capsys.readouterr()
        
        # Verify formatting
        assert 'Test String' in captured.out  # String as-is
        assert '42' in captured.out  # Integer as-is
        assert '123,456,789' in captured.out  # Counter with thousands separators
        assert '86400000 (10 days)' in captured.out  # Timeticks with human-readable format
    
    @pytest.mark.bundle(3)
    @pytest.mark.points(2)
    def test_manager_edge_case_empty_string_values(self, mock_socket, capsys):
        """Test manager handling of edge case values like empty strings."""
        from src.snmp_manager import SNMPManager
        from src.snmp_protocol import ErrorCode, GetResponse, ValueType
        
        manager = SNMPManager()
        
        # Create dynamic response with edge case values
        def custom_recv(size):
            if mock_socket.sent_data:
                sent_bytes = mock_socket.sent_data[0]
                if len(sent_bytes) >= 8:
                    _, _, _, request_id = struct.unpack('!BBHI', sent_bytes[:8])
                    edge_response = GetResponse(
                        request_id=request_id,
                        error_code=ErrorCode.SUCCESS,
                        bindings=[
                            ('1.3.6.1.4.1.99.1.1.0', ValueType.STRING, ''),  # Empty string
                            ('1.3.6.1.4.1.99.1.2.0', ValueType.INTEGER, 0),  # Zero
                            ('1.3.6.1.4.1.99.1.3.0', ValueType.INTEGER, -1), # Negative
                            ('1.3.6.1.4.1.99.1.4.0', ValueType.COUNTER, 0),  # Zero counter
                            ('1.3.6.1.4.1.99.1.5.0', ValueType.TIMETICKS, 0), # Zero timeticks
                        ]
                    )
                    return edge_response.pack()
            return b''
        
        mock_socket.recv = custom_recv
        
        oids = [f'1.3.6.1.4.1.99.1.{i}.0' for i in range(1, 6)]
        
        with patch('socket.socket', return_value=mock_socket):
            manager.get('localhost', 1161, oids)
        
        # Verify edge cases are handled correctly
        captured = capsys.readouterr()
        lines = captured.out.strip().split('\n')
        
        # Check each line contains the OID and properly formatted value
        assert any('1.3.6.1.4.1.99.1.1.0 = ' in line for line in lines), "Empty string should be displayed"
        assert any('1.3.6.1.4.1.99.1.2.0 = 0' in line for line in lines), "Zero integer should be displayed"
        assert any('1.3.6.1.4.1.99.1.3.0 = -1' in line for line in lines), "Negative integer should be displayed"
        assert any('1.3.6.1.4.1.99.1.4.0 = 0' in line for line in lines), "Zero counter should be displayed"
        assert any('1.3.6.1.4.1.99.1.5.0 = 0 (0.00 seconds)' in line for line in lines), "Zero timeticks should be formatted"