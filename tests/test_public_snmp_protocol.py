"""
Public test cases for SNMP protocol implementation.
These tests are visible to students and do not contain implementation code.
Tests are organized by specification grading bundles.
"""

import struct
import sys
from pathlib import Path

import pytest

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from .test_utils import TestDataGenerator

# ============================================================================
# BUNDLE C (CORE PROTOCOL) - PUBLIC TESTS
# Total: 11 points
# ============================================================================

class TestBundleCPublic:
    """Public tests for Bundle C - Core Protocol Implementation"""
    
    @pytest.mark.bundle(1)
    @pytest.mark.points(1)
    def test_oid_encoding_multiple(self):
        """Test OID encoding with various OIDs."""
        from src.snmp_protocol import encode_oid
        
        test_cases = [
            ("1.3.6.1", b'\x01\x03\x06\x01'),
            ("1.3.6.1.2.1.1.1.0", b'\x01\x03\x06\x01\x02\x01\x01\x01\x00'),
            ("1.3.6.1.2.1.1.5.0", b'\x01\x03\x06\x01\x02\x01\x01\x05\x00'),
            ("1.3.6.1.4.1.9.9.23.1.2.1.1.6", b'\x01\x03\x06\x01\x04\x01\x09\x09\x17\x01\x02\x01\x01\x06'),
        ]
        
        for oid_str, expected in test_cases:
            result = encode_oid(oid_str)
            assert isinstance(result, bytes), f"encode_oid must return bytes for {oid_str}"
            assert result == expected, f"OID {oid_str}: expected {expected.hex()}, got {result.hex()}"
    
    @pytest.mark.bundle(1)
    @pytest.mark.points(1)
    def test_oid_decoding_multiple(self):
        """Test OID decoding with various encoded OIDs."""
        from src.snmp_protocol import decode_oid
        
        test_cases = [
            (b'\x01\x03\x06\x01', "1.3.6.1"),
            (b'\x01\x03\x06\x01\x02\x01\x01\x01\x00', "1.3.6.1.2.1.1.1.0"),
            (b'\x01\x03\x06\x01\x02\x01\x01\x05\x00', "1.3.6.1.2.1.1.5.0"),
            (b'\x01\x03\x06\x01\x04\x01\x09\x09\x17\x01\x02\x01\x01\x06', "1.3.6.1.4.1.9.9.23.1.2.1.1.6"),
        ]
        
        for encoded, expected in test_cases:
            result = decode_oid(encoded)
            assert isinstance(result, str), f"decode_oid must return a string for {encoded.hex()}"
            assert result == expected, f"Bytes {encoded.hex()}: expected '{expected}', got '{result}'"
    
    @pytest.mark.bundle(1)
    @pytest.mark.points(1)
    def test_encode_decode_oid_roundtrip(self):
        """Test that OID encoding and decoding are inverses."""
        from src.snmp_protocol import decode_oid, encode_oid

        # Test OIDs with components that fit in 1 byte (0-255)
        test_oids = [
            "1.3.6.1.2.1.1.1.0",
            "1.3.6.1.2.1.1.5.0",
            "1.3.6.1.4.1.9.9.23.1.2.1.1.6",
        ]
        
        for oid in test_oids:
            encoded = encode_oid(oid)
            decoded = decode_oid(encoded)
            assert decoded == oid, f"Roundtrip failed for {oid}: got {decoded}"
            
            # Also verify encoding is 1 byte per component
            expected_len = len(oid.split('.'))
            assert len(encoded) == expected_len, \
                f"OID {oid} should encode to {expected_len} bytes, got {len(encoded)}"
    
    @pytest.mark.bundle(1)
    @pytest.mark.points(1)
    def test_value_encoding_integers(self):
        """Test integer value encoding."""
        from src.snmp_protocol import ValueType, encode_value
        
        test_cases = [
            (0, b'\x00\x00\x00\x00'),
            (42, b'\x00\x00\x00\x2a'),
            (-1, b'\xff\xff\xff\xff'),
            (1234567, b'\x00\x12\xd6\x87'),
        ]
        
        for value, expected in test_cases:
            result = encode_value(value, ValueType.INTEGER)
            assert result == expected, \
                f"encode_value({value}, INTEGER) expected {expected.hex()}, got {result.hex()}"
    
    @pytest.mark.bundle(1)
    @pytest.mark.points(1)
    def test_value_encoding_strings(self):
        """Test string value encoding."""
        from src.snmp_protocol import ValueType, encode_value
        
        test_cases = [
            ("test", b"test"),
            ("", b""),
            ("Hello World", b"Hello World"),
            ("router-01", b"router-01"),
        ]
        
        for value, expected in test_cases:
            result = encode_value(value, ValueType.STRING)
            assert result == expected, \
                f"encode_value('{value}', STRING) expected {expected}, got {result}"
    
    @pytest.mark.bundle(1)
    @pytest.mark.points(1)
    def test_value_encoding_counters(self):
        """Test counter value encoding."""
        from src.snmp_protocol import ValueType, encode_value
        
        test_cases = [
            (0, b'\x00\x00\x00\x00'),
            (42, b'\x00\x00\x00\x2a'),
            (1234567, b'\x00\x12\xd6\x87'),
            (4294967295, b'\xff\xff\xff\xff'),  # Max 32-bit unsigned
        ]
        
        for value, expected in test_cases:
            result = encode_value(value, ValueType.COUNTER)
            assert result == expected, \
                f"encode_value({value}, COUNTER) expected {expected.hex()}, got {result.hex()}"
    
    @pytest.mark.bundle(1)
    @pytest.mark.points(1)
    def test_value_encoding_timeticks(self):
        """Test timeticks value encoding."""
        from src.snmp_protocol import ValueType, encode_value
        
        test_cases = [
            (0, b'\x00\x00\x00\x00'),  # 0 seconds
            (100, b'\x00\x00\x00\x64'),  # 1 second (100 hundredths)
            (360000, b'\x00\x05\x7e\x40'),  # 1 hour in hundredths
            (8640000, b'\x00\x83\xd6\x00'),  # 1 day in hundredths
        ]
        
        for value, expected in test_cases:
            result = encode_value(value, ValueType.TIMETICKS)
            assert result == expected, \
                f"encode_value({value}, TIMETICKS) expected {expected.hex()}, got {result.hex()}"
    
    @pytest.mark.bundle(1)
    @pytest.mark.points(1)
    def test_value_decoding_integers(self):
        """Test integer value decoding."""
        from src.snmp_protocol import ValueType, decode_value
        
        test_cases = [
            (b'\x00\x00\x00\x00', 0),
            (b'\x00\x00\x00\x2a', 42),
            (b'\xff\xff\xff\xff', -1),
            (b'\x00\x12\xd6\x87', 1234567),
            (b'\x80\x00\x00\x00', -2147483648),  # Min 32-bit signed
        ]
        
        for encoded, expected in test_cases:
            result = decode_value(encoded, ValueType.INTEGER)
            assert result == expected, \
                f"decode_value({encoded.hex()}, INTEGER) expected {expected}, got {result}"
    
    @pytest.mark.bundle(1)
    @pytest.mark.points(1)
    def test_value_decoding_strings(self):
        """Test string value decoding."""
        from src.snmp_protocol import ValueType, decode_value
        
        test_cases = [
            (b"test", "test"),
            (b"", ""),
            (b"Hello World", "Hello World"),
            (b"router-01", "router-01"),
            (b"System\x20Name", "System Name"),  # With space
        ]
        
        for encoded, expected in test_cases:
            result = decode_value(encoded, ValueType.STRING)
            assert result == expected, \
                f"decode_value({encoded}, STRING) expected '{expected}', got '{result}'"
    
    @pytest.mark.bundle(1)
    @pytest.mark.points(1)
    def test_value_decoding_counters(self):
        """Test counter value decoding."""
        from src.snmp_protocol import ValueType, decode_value
        
        test_cases = [
            (b'\x00\x00\x00\x00', 0),
            (b'\x00\x00\x00\x2a', 42),
            (b'\x00\x12\xd6\x87', 1234567),
            (b'\xff\xff\xff\xff', 4294967295),  # Max 32-bit unsigned
        ]
        
        for encoded, expected in test_cases:
            result = decode_value(encoded, ValueType.COUNTER)
            assert result == expected, \
                f"decode_value({encoded.hex()}, COUNTER) expected {expected}, got {result}"
    
    @pytest.mark.bundle(1)
    @pytest.mark.points(1)
    def test_value_decoding_timeticks(self):
        """Test timeticks value decoding."""
        from src.snmp_protocol import ValueType, decode_value
        
        test_cases = [
            (b'\x00\x00\x00\x00', 0),  # 0 seconds
            (b'\x00\x00\x00\x64', 100),  # 1 second
            (b'\x00\x05\x7e\x40', 360000),  # 1 hour
            (b'\x00\x83\xd6\x00', 8640000),  # 1 day
        ]
        
        for encoded, expected in test_cases:
            result = decode_value(encoded, ValueType.TIMETICKS)
            assert result == expected, \
                f"decode_value({encoded.hex()}, TIMETICKS) expected {expected}, got {result}"


# ============================================================================
# BUNDLE B (INTERMEDIATE FEATURES) - PUBLIC TESTS
# Total: 16 points
# ============================================================================

class TestBundleBPublic:
    """Public tests for Bundle B - GET/SET Operations"""
    
    @pytest.mark.bundle(2)
    @pytest.mark.points(2)
    def test_get_request_pack_multiple(self):
        """Test GetRequest message packing with various OID combinations."""
        from src.snmp_protocol import GetRequest
        
        test_cases = [
            # (request_id, oids)
            (1234, ["1.3.6.1.2.1.1.1.0"]),  # Single OID
            (5678, ["1.3.6.1.2.1.1.1.0", "1.3.6.1.2.1.1.5.0"]),  # Multiple OIDs
            (9999, ["1.3.6.1.2.1.1.3.0", "1.3.6.1.2.1.1.4.0", "1.3.6.1.2.1.1.5.0"]),  # Three OIDs
            (1, ["1.3"]),  # Short OID
        ]
        
        for request_id, oids in test_cases:
            req = GetRequest(request_id=request_id, oids=oids)
            result = req.pack()
            
            assert isinstance(result, bytes), f"pack() must return bytes for request_id={request_id}"
            assert len(result) >= 10, f"Packed message too short for request_id={request_id}"
            
            # Check basic structure per README
            # Total size at bytes 0-3
            total_size = struct.unpack('!I', result[0:4])[0]
            assert total_size == len(result), f"Total size mismatch: header says {total_size}, actual {len(result)}"
            
            # Request ID at bytes 4-8
            actual_id = struct.unpack('!I', result[4:8])[0]
            assert actual_id == request_id, f"Expected request ID {request_id}, got {actual_id}"
            
            # PDU type at byte 8
            assert result[8] == 160, "PDU type should be 160 (0xA0) for GetRequest"
            
            # OID count at byte 9 (1 byte per README)
            oid_count = struct.unpack('!B', result[9:10])[0]
            assert oid_count == len(oids), f"Expected {len(oids)} OIDs, got {oid_count}"
    
    @pytest.mark.bundle(2)
    @pytest.mark.points(2)
    def test_set_request_pack_multiple(self):
        """Test SetRequest message packing with various value types."""
        from src.snmp_protocol import SetRequest, ValueType
        
        test_cases = [
            # Single string value
            (1111, [("1.3.6.1.2.1.1.5.0", ValueType.STRING, "test-router")]),
            # Multiple values with different types
            (2222, [
                ("1.3.6.1.2.1.1.5.0", ValueType.STRING, "router-01"),
                ("1.3.6.1.2.1.1.3.0", ValueType.TIMETICKS, 360000),
            ]),
            # Integer and counter values
            (3333, [
                ("1.3.6.1.2.1.2.2.1.7.1", ValueType.INTEGER, 1),
                ("1.3.6.1.2.1.2.2.1.10.1", ValueType.COUNTER, 1234567),
            ]),
            # Empty string
            (4444, [("1.3.6.1.2.1.1.4.0", ValueType.STRING, "")]),
        ]
        
        for request_id, bindings in test_cases:
            req = SetRequest(request_id=request_id, bindings=bindings)
            result = req.pack()
            
            assert isinstance(result, bytes), f"pack() must return bytes for request_id={request_id}"
            assert len(result) >= 10, f"Packed message too short for request_id={request_id}"
            
            # Check basic structure per README
            # Total size at bytes 0-3
            total_size = struct.unpack('!I', result[0:4])[0]
            assert total_size == len(result), f"Total size mismatch: header says {total_size}, actual {len(result)}"
            
            # Request ID at bytes 4-8
            actual_id = struct.unpack('!I', result[4:8])[0]
            assert actual_id == request_id, f"Expected request ID {request_id}, got {actual_id}"
            
            # PDU type at byte 8
            assert result[8] == 163, "PDU type should be 163 (0xA3) for SetRequest"
            
            # Binding count at byte 9 (1 byte per README)
            binding_count = struct.unpack('!B', result[9:10])[0]
            assert binding_count == len(bindings), f"Expected {len(bindings)} bindings, got {binding_count}"
    
    @pytest.mark.bundle(2)
    @pytest.mark.points(2)
    def test_get_response_pack_multiple(self):
        """Test GetResponse message packing with various response types."""
        from src.snmp_protocol import ErrorCode, GetResponse, ValueType
        
        test_cases = [
            # Successful response with string
            (1234, ErrorCode.SUCCESS, [("1.3.6.1.2.1.1.1.0", ValueType.STRING, "Test System")]),
            # Successful response with multiple values
            (5678, ErrorCode.SUCCESS, [
                ("1.3.6.1.2.1.1.1.0", ValueType.STRING, "Linux router"),
                ("1.3.6.1.2.1.1.3.0", ValueType.TIMETICKS, 8640000),
                ("1.3.6.1.2.1.2.1.0", ValueType.INTEGER, 4),
            ]),
            # Error response (no bindings)
            (9999, ErrorCode.NO_SUCH_OID, []),
            # Error response with different error codes
            (1111, ErrorCode.BAD_VALUE, []),
            (2222, ErrorCode.READ_ONLY, []),
            # Response with counter
            (3333, ErrorCode.SUCCESS, [
                ("1.3.6.1.2.1.2.2.1.10.1", ValueType.COUNTER, 1234567890),
            ]),
        ]
        
        for request_id, error_code, bindings in test_cases:
            resp = GetResponse(request_id=request_id, error_code=error_code, bindings=bindings)
            result = resp.pack()
            
            assert isinstance(result, bytes), f"pack() must return bytes for request_id={request_id}"
            assert len(result) >= 11, f"Packed message too short for request_id={request_id}"
            
            # Check basic structure per README
            # Total size at bytes 0-3
            total_size = struct.unpack('!I', result[0:4])[0]
            assert total_size == len(result), f"Total size mismatch: header says {total_size}, actual {len(result)}"
            
            # Request ID at bytes 4-8
            actual_id = struct.unpack('!I', result[4:8])[0]
            assert actual_id == request_id, f"Expected request ID {request_id}, got {actual_id}"
            
            # PDU type at byte 8
            assert result[8] == 161, "PDU type should be 161 (0xA1) for GetResponse"
            
            # Error code at byte 9 (only in responses)
            assert result[9] == error_code.value, f"Expected error code {error_code.value}, got {result[9]}"
    
    @pytest.mark.bundle(2)
    @pytest.mark.points(2)
    def test_unpack_get_request_multiple(self):
        """Test unpacking GetRequest messages with various OID combinations."""
        from src.snmp_protocol import GetRequest, unpack_message
        
        test_cases = [
            # Single OID
            (9999, [b'\x01\x03\x06\x01\x02\x01\x01\x01\x00']),  # 1.3.6.1.2.1.1.1.0
            # Multiple OIDs
            (1234, [
                b'\x01\x03\x06\x01\x02\x01\x01\x01\x00',  # 1.3.6.1.2.1.1.1.0
                b'\x01\x03\x06\x01\x02\x01\x01\x05\x00',  # 1.3.6.1.2.1.1.5.0
            ]),
            # Three OIDs
            (5678, [
                b'\x01\x03\x06\x01',  # 1.3.6.1
                b'\x01\x03',  # 1.3
                b'\x01\x03\x06\x01\x02\x01',  # 1.3.6.1.2.1
            ]),
        ]
        
        for request_id, oid_bytes_list in test_cases:
            # Create a valid GetRequest message per README format
            payload = bytearray()
            payload.append(len(oid_bytes_list))  # OID count (1 byte)
            
            # Add OIDs
            for oid_bytes in oid_bytes_list:
                payload.append(len(oid_bytes))  # OID length (1 byte)
                payload.extend(oid_bytes)
            
            # Build complete message with header
            total_size = 9 + len(payload)  # 4+4+1 header + payload
            message = bytearray()
            message.extend(struct.pack('!I', total_size))  # Total size
            message.extend(struct.pack('!I', request_id))  # Request ID
            message.append(160)  # PDU type: GetRequest (0xA0)
            message.extend(payload)
            
            # Unpack the message
            result = unpack_message(bytes(message))
            
            assert isinstance(result, GetRequest), f"Should return GetRequest for request_id={request_id}"
            assert result.request_id == request_id, f"Expected request ID {request_id}, got {result.request_id}"
            assert len(result.oids) == len(oid_bytes_list), f"Expected {len(oid_bytes_list)} OIDs, got {len(result.oids)}"
    
    @pytest.mark.bundle(2)
    @pytest.mark.points(2)
    def test_unpack_set_request_multiple(self):
        """Test unpacking SetRequest messages with various value types."""
        from src.snmp_protocol import SetRequest, ValueType, unpack_message
        
        test_cases = [
            # Single string binding
            (1111, [(b'\x01\x03\x06\x01\x02\x01\x01\x05\x00', ValueType.STRING.value, b'router-01')]),
            # Multiple bindings with different types
            (2222, [
                (b'\x01\x03\x06\x01\x02\x01\x01\x05\x00', ValueType.STRING.value, b'test'),
                (b'\x01\x03\x06\x01\x02\x01\x01\x03\x00', ValueType.TIMETICKS.value, struct.pack('!I', 360000)),
            ]),
            # Integer and counter bindings
            (3333, [
                (b'\x01\x03\x06\x01\x02\x01\x02\x02\x01\x07\x01', ValueType.INTEGER.value, struct.pack('!i', 1)),
                (b'\x01\x03\x06\x01\x02\x01\x02\x02\x01\x0a\x01', ValueType.COUNTER.value, struct.pack('!I', 1234567)),
            ]),
        ]
        
        for request_id, bindings in test_cases:
            # Create a valid SetRequest message per README format
            payload = bytearray()
            payload.append(len(bindings))  # Binding count (1 byte)
            
            # Add bindings
            for oid_bytes, value_type, value_bytes in bindings:
                payload.append(len(oid_bytes))  # OID length (1 byte)
                payload.extend(oid_bytes)
                payload.append(value_type)  # Value type
                payload.extend(struct.pack('!H', len(value_bytes)))  # Value length (2 bytes per README)
                payload.extend(value_bytes)
            
            # Build complete message with header
            total_size = 9 + len(payload)  # 4+4+1 header + payload
            message = bytearray()
            message.extend(struct.pack('!I', total_size))  # Total size
            message.extend(struct.pack('!I', request_id))  # Request ID
            message.append(163)  # PDU type: SetRequest (0xA3)
            message.extend(payload)
            
            # Unpack the message
            result = unpack_message(bytes(message))
            
            assert isinstance(result, SetRequest), f"Should return SetRequest for request_id={request_id}"
            assert result.request_id == request_id, f"Expected request ID {request_id}, got {result.request_id}"
            assert len(result.bindings) == len(bindings), f"Expected {len(bindings)} bindings, got {len(result.bindings)}"
    
    @pytest.mark.bundle(2)
    @pytest.mark.points(2)
    def test_unpack_get_response_multiple(self):
        """Test unpacking GetResponse messages with various response types."""
        from src.snmp_protocol import (ErrorCode, GetResponse, ValueType,
                                       unpack_message)
        
        test_cases = [
            # Successful response with bindings
            (4444, ErrorCode.SUCCESS.value, [
                (b'\x01\x03\x06\x01\x02\x01\x01\x01\x00', ValueType.STRING.value, b'Test System'),
            ]),
            # Error response with no bindings
            (5555, ErrorCode.NO_SUCH_OID.value, []),
            # Multiple bindings response
            (6666, ErrorCode.SUCCESS.value, [
                (b'\x01\x03\x06\x01\x02\x01\x01\x01\x00', ValueType.STRING.value, b'Linux'),
                (b'\x01\x03\x06\x01\x02\x01\x01\x03\x00', ValueType.TIMETICKS.value, struct.pack('!I', 8640000)),
                (b'\x01\x03\x06\x01\x02\x01\x02\x01\x00', ValueType.INTEGER.value, struct.pack('!i', 4)),
            ]),
        ]
        
        for request_id, error_code, bindings in test_cases:
            # Create a valid GetResponse message per README format
            payload = bytearray()
            payload.append(len(bindings))  # Binding count (1 byte)
            
            # Add bindings
            for oid_bytes, value_type, value_bytes in bindings:
                payload.append(len(oid_bytes))  # OID length (1 byte)
                payload.extend(oid_bytes)
                payload.append(value_type)  # Value type
                payload.extend(struct.pack('!H', len(value_bytes)))  # Value length (2 bytes per README)
                payload.extend(value_bytes)
            
            # Build complete message with header (includes error_code)
            total_size = 10 + len(payload)  # 4+4+1+1 header + payload
            message = bytearray()
            message.extend(struct.pack('!I', total_size))  # Total size
            message.extend(struct.pack('!I', request_id))  # Request ID
            message.append(161)  # PDU type: GetResponse (0xA1)
            message.append(error_code)  # Error code
            message.extend(payload)
            
            # Unpack the message
            result = unpack_message(bytes(message))
            
            assert isinstance(result, GetResponse), f"Should return GetResponse for request_id={request_id}"
            assert result.request_id == request_id, f"Expected request ID {request_id}, got {result.request_id}"
            assert result.error_code.value == error_code, f"Expected error code {error_code}, got {result.error_code.value}"
            assert len(result.bindings) == len(bindings), f"Expected {len(bindings)} bindings, got {len(result.bindings)}"
    
    @pytest.mark.bundle(2)
    @pytest.mark.points(2)
    def test_unpack_message_type_detection(self):
        """Test that unpack_message correctly identifies and returns the right message type."""
        from src.snmp_protocol import (GetRequest, GetResponse, PDUType,
                                       SetRequest, ValueType, unpack_message)

        # Test cases with different PDU types
        test_cases = [
            # (pdu_type, expected_class_name, description)
            (PDUType.GET_REQUEST.value, "GetRequest", "GET request"),
            (PDUType.SET_REQUEST.value, "SetRequest", "SET request"),
            (PDUType.GET_RESPONSE.value, "GetResponse", "GET response"),
        ]
        
        for pdu_type, expected_class, description in test_cases:
            # Create a minimal valid message for each type per README format
            payload = bytearray()
            
            if pdu_type == PDUType.GET_REQUEST.value:
                # GetRequest needs OID count and at least one OID
                payload.append(1)  # OID count (1 byte)
                oid_bytes = b'\x01\x03\x06\x01'
                payload.append(len(oid_bytes))  # OID length (1 byte)
                payload.extend(oid_bytes)
                # Build complete message
                total_size = 9 + len(payload)
                message = bytearray()
                message.extend(struct.pack('!I', total_size))
                message.extend(struct.pack('!I', 12345))
                message.append(pdu_type)
                message.extend(payload)
            elif pdu_type == PDUType.SET_REQUEST.value:
                # SetRequest needs binding count and at least one binding
                payload.append(1)  # Binding count (1 byte)
                oid_bytes = b'\x01\x03\x06\x01'
                payload.append(len(oid_bytes))  # OID length (1 byte)
                payload.extend(oid_bytes)
                payload.append(ValueType.INTEGER.value)  # Value type
                value_bytes = struct.pack('!i', 42)
                payload.extend(struct.pack('!H', len(value_bytes)))  # Value length (2 bytes)
                payload.extend(value_bytes)
                # Build complete message
                total_size = 9 + len(payload)
                message = bytearray()
                message.extend(struct.pack('!I', total_size))
                message.extend(struct.pack('!I', 12345))
                message.append(pdu_type)
                message.extend(payload)
            elif pdu_type == PDUType.GET_RESPONSE.value:
                # GetResponse needs error code and binding count
                payload.append(0)  # No bindings for simplicity
                # Build complete message (with error code)
                total_size = 10 + len(payload)
                message = bytearray()
                message.extend(struct.pack('!I', total_size))
                message.extend(struct.pack('!I', 12345))
                message.append(pdu_type)
                message.append(0)  # Error code (SUCCESS)
                message.extend(payload)
            
            # Test unpacking
            result = unpack_message(bytes(message))
            
            # Check that the correct message type was returned
            assert result.__class__.__name__ == expected_class, \
                f"Expected {expected_class} for {description}, got {result.__class__.__name__}"
            assert result.request_id == 12345, \
                f"Request ID should be preserved for {description}"
    
    @pytest.mark.bundle(2)
    @pytest.mark.points(1)
    def test_unpack_message_invalid_inputs(self):
        """Test that unpack_message handles invalid inputs appropriately."""
        from src.snmp_protocol import unpack_message

        # Test message that's too short (less than minimum 9 bytes)
        too_short = bytearray()
        too_short.extend(struct.pack('!I', 8))  # Total size claiming 8 bytes
        too_short.extend(b'\x00\x00\x00\x00')  # Only 8 bytes total
        
        try:
            result = unpack_message(bytes(too_short))
            assert False, "Should have raised an error for message too short"
        except ValueError as e:
            # Expected behavior - message too short should be rejected
            pass
        
        # Test unknown PDU type
        unknown_pdu = bytearray()
        unknown_pdu.extend(struct.pack('!I', 10))  # Total size
        unknown_pdu.extend(struct.pack('!I', 1234))  # Request ID
        unknown_pdu.append(99)  # Invalid PDU type
        unknown_pdu.append(0)  # Payload
        
        try:
            result = unpack_message(bytes(unknown_pdu))
            assert False, "Should have raised an error for unknown PDU type"
        except (ValueError, KeyError) as e:
            # Expected behavior - unknown PDU type should be rejected
            pass
        
        # Test truncated message (size field says more bytes than provided)
        truncated = bytearray()
        truncated.extend(struct.pack('!I', 100))  # Claims 100 bytes
        truncated.extend(struct.pack('!I', 1234))  # Request ID
        truncated.append(160)  # PDU type
        # But message is only 9 bytes, not 100
        
        try:
            # This should fail during unpacking due to missing data
            result = unpack_message(bytes(truncated))
            # If it doesn't fail immediately, it should fail when trying to parse payload
            assert False, "Should have raised an error for truncated message"
        except (struct.error, IndexError, ValueError) as e:
            # Expected behavior - truncated message should be rejected
            pass
    
    @pytest.mark.bundle(2)
    @pytest.mark.points(1)
    def test_message_roundtrip_all_types(self):
        """Test that pack and unpack are inverses for all message types."""
        from src.snmp_protocol import (ErrorCode, GetRequest, GetResponse,
                                       SetRequest, ValueType, unpack_message)

        # Test GetRequest roundtrip
        get_req = GetRequest(request_id=12345, oids=["1.3.6.1.2.1.1.5.0", "1.3.6.1.2.1.1.1.0"])
        packed = get_req.pack()
        unpacked = unpack_message(packed)
        assert isinstance(unpacked, GetRequest), "GetRequest roundtrip failed"
        assert unpacked.request_id == get_req.request_id
        assert unpacked.oids == get_req.oids
        
        # Test SetRequest roundtrip
        set_req = SetRequest(request_id=54321, bindings=[
            ("1.3.6.1.2.1.1.5.0", ValueType.STRING, "test"),
            ("1.3.6.1.2.1.2.1.0", ValueType.INTEGER, 42),
        ])
        packed = set_req.pack()
        unpacked = unpack_message(packed)
        assert isinstance(unpacked, SetRequest), "SetRequest roundtrip failed"
        assert unpacked.request_id == set_req.request_id
        assert len(unpacked.bindings) == len(set_req.bindings)
        
        # Test GetResponse roundtrip
        get_resp = GetResponse(request_id=11111, error_code=ErrorCode.SUCCESS, bindings=[
            ("1.3.6.1.2.1.1.1.0", ValueType.STRING, "System"),
            ("1.3.6.1.2.1.1.3.0", ValueType.TIMETICKS, 100000),
        ])
        packed = get_resp.pack()
        unpacked = unpack_message(packed)
        assert isinstance(unpacked, GetResponse), "GetResponse roundtrip failed"
        assert unpacked.request_id == get_resp.request_id
        assert unpacked.error_code == get_resp.error_code


# ============================================================================
# BUNDLE A (ADVANCED FEATURES) - PUBLIC TESTS
# Total: 25 points (reduced from excessive production testing)
# ============================================================================

class TestBundleAPublic:
    """Public tests for Bundle A - Advanced Features"""
    
    @pytest.mark.bundle(3)
    @pytest.mark.points(3)
    def test_receive_complete_message_simple(self):
        """Test receiving a complete message in one chunk."""
        from src.snmp_protocol import GetRequest, receive_complete_message

        # Create a simple GetRequest message
        req = GetRequest(request_id=1111, oids=["1.3.6.1"])
        message_bytes = req.pack()
        
        # Create a mock socket that returns the whole message
        class MockSocket:
            def __init__(self, data):
                self.data = data
                self.calls = 0
            
            def recv(self, size):
                if self.calls == 0:
                    self.calls += 1
                    return self.data
                return b''
        
        mock_sock = MockSocket(message_bytes)
        result = receive_complete_message(mock_sock)
        
        assert result == message_bytes, "Should return the complete message"
    
    @pytest.mark.bundle(3)
    @pytest.mark.points(3)
    def test_receive_complete_message_fragmented(self):
        """Test receiving a message in multiple chunks."""
        from src.snmp_protocol import SetRequest, ValueType, receive_complete_message

        # Create a larger message to ensure fragmentation
        bindings = [
            ("1.3.6.1.2.1.1.4.0", ValueType.STRING, "Test fragmentation"),
            ("1.3.6.1.2.1.1.5.0", ValueType.STRING, "Another value"),
            ("1.3.6.1.2.1.2.1.0", ValueType.INTEGER, 42),
        ]
        req = SetRequest(request_id=5678, bindings=bindings)
        message_bytes = req.pack()
        
        # Create a mock socket that returns data in small chunks
        class MockSocket:
            def __init__(self, data, chunk_size=5):
                self.data = data
                self.pos = 0
                self.chunk_size = chunk_size
            
            def recv(self, size):
                if self.pos >= len(self.data):
                    return b''
                chunk = self.data[self.pos:self.pos + self.chunk_size]
                self.pos += self.chunk_size
                return chunk
        
        mock_sock = MockSocket(message_bytes, chunk_size=5)
        result = receive_complete_message(mock_sock)
        
        assert result == message_bytes, "Should reassemble fragmented message"
    
    @pytest.mark.bundle(3)
    @pytest.mark.points(2)
    def test_receive_message_boundary_cases(self):
        """Test receiving messages with specific fragmentation patterns."""
        from src.snmp_protocol import GetRequest, receive_complete_message
        
        # Create test message
        req = GetRequest(request_id=5678, oids=["1.3.6.1.2.1.1.5.0"])
        test_message = req.pack()
        
        # Test 1-byte-at-a-time reception (extreme fragmentation)
        class OneByteSocket:
            def __init__(self, data):
                self.data = data
                self.pos = 0
            
            def recv(self, size):
                if self.pos >= len(self.data):
                    return b''
                byte = self.data[self.pos:self.pos+1]
                self.pos += 1
                return byte
        
        result = receive_complete_message(OneByteSocket(test_message))
        assert result == test_message, "Should handle byte-by-byte reception"
        
        # Test size field split across recv calls
        class SizeSplitSocket:
            def __init__(self, data):
                self.data = data
                self.call_count = 0
            
            def recv(self, size):
                self.call_count += 1
                if self.call_count == 1:
                    return self.data[0:2]  # First 2 bytes of size
                elif self.call_count == 2:
                    return self.data[2:4]  # Last 2 bytes of size
                elif self.call_count == 3:
                    return self.data[4:]   # Rest of message
                return b''
        
        result = receive_complete_message(SizeSplitSocket(test_message))
        assert result == test_message, "Should handle size field fragmentation"
    
    @pytest.mark.bundle(3)
    @pytest.mark.points(3)
    def test_receive_network_failures(self):
        """Test message reception with network failure scenarios."""
        from src.snmp_protocol import GetRequest, receive_complete_message
        import struct
        
        # Create test message
        req = GetRequest(request_id=1234, oids=["1.3.6.1.2.1.1.1.0"])
        test_message = req.pack()
        
        # Test connection closed during size reception
        class ClosedDuringSizeSocket:
            def __init__(self):
                self.call_count = 0
            
            def recv(self, size):
                self.call_count += 1
                if self.call_count == 1:
                    return b'\x00\x00'  # Return partial size
                return b''  # Connection closed
        
        try:
            receive_complete_message(ClosedDuringSizeSocket())
            assert False, "Should raise ConnectionError when connection closes during size"
        except ConnectionError:
            pass  # Expected
        
        # Test connection closed during message body
        class ClosedDuringMessageSocket:
            def __init__(self, message_bytes):
                self.data = message_bytes
                self.call_count = 0
            
            def recv(self, size):
                self.call_count += 1
                if self.call_count == 1:
                    return self.data[:4]  # Return size field
                elif self.call_count == 2:
                    return self.data[4:8]  # Return partial message
                return b''  # Connection closed
        
        try:
            receive_complete_message(ClosedDuringMessageSocket(test_message))
            assert False, "Should raise ConnectionError when connection closes during body"
        except ConnectionError:
            pass  # Expected
        
        # Test invalid message size (too small)
        class InvalidSizeSocket:
            def __init__(self, fake_size):
                self.fake_size = fake_size
                self.call_count = 0
            
            def recv(self, size):
                self.call_count += 1
                if self.call_count == 1:
                    return struct.pack('!I', self.fake_size)
                return b'x' * size  # Dummy data
        
        # Test message too small (README specifies minimum 9 bytes)
        try:
            receive_complete_message(InvalidSizeSocket(8))
            assert False, "Should raise ValueError for size < 9"
        except ValueError:
            pass  # Expected
        
        # Test zero size
        try:
            receive_complete_message(InvalidSizeSocket(0))
            assert False, "Should raise ValueError for zero size"
        except ValueError:
            pass  # Expected
    
    @pytest.mark.bundle(3)
    @pytest.mark.points(3)
    def test_error_handling(self):
        """Test error response generation and handling."""
        from src.snmp_protocol import ErrorCode, GetResponse, unpack_message
        
        # Test all error codes
        error_cases = [
            (ErrorCode.SUCCESS, "Success"),
            (ErrorCode.NO_SUCH_OID, "No such OID"),
            (ErrorCode.BAD_VALUE, "Bad value"),
            (ErrorCode.READ_ONLY, "Read only"),
        ]
        
        for error_code, description in error_cases:
            resp = GetResponse(
                request_id=3333,
                error_code=error_code,
                bindings=[]  # Empty bindings for error
            )
            
            packed = resp.pack()
            
            # Verify error code at correct position
            assert packed[9] == error_code.value, \
                f"Error code for {description} should be {error_code.value}"
            
            # Verify message can be unpacked
            unpacked = unpack_message(packed)
            assert unpacked.error_code == error_code, \
                f"Unpacked error code should match for {description}"
            assert unpacked.bindings == [], \
                f"Error response should have empty bindings"
    
    @pytest.mark.bundle(3)
    @pytest.mark.points(2)
    def test_message_unpacking_truncated(self):
        """Test unpacking messages with truncated or incomplete data."""
        from src.snmp_protocol import GetRequest, unpack_message
        
        # Create a valid message first
        req = GetRequest(request_id=5678, oids=["1.3.6.1.2.1.1.1.0", "1.3.6.1.2.1.1.5.0"])
        full_message = req.pack()
        
        # Test truncation at various points
        truncation_points = [
            0,   # Empty message
            4,   # Only size field
            8,   # Size + request_id
            9,   # Size + request_id + pdu_type
            len(full_message) - 1,  # Missing last byte
        ]
        
        for truncate_at in truncation_points:
            truncated = full_message[:truncate_at]
            
            # Should raise error for truncated messages
            try:
                unpack_message(truncated)
                assert False, f"Should raise error for truncation at byte {truncate_at}"
            except (ValueError, IndexError, struct.error):
                pass  # Expected
    
    @pytest.mark.bundle(3)
    @pytest.mark.points(2)
    def test_message_unpacking_invalid(self):
        """Test unpacking messages with invalid field values."""
        from src.snmp_protocol import unpack_message
        import struct
        
        # Test invalid PDU type (README specifies: 0xA0, 0xA1, 0xA3)
        invalid_pdu_msg = bytearray()
        invalid_pdu_msg.extend(struct.pack('!I', 10))    # Size
        invalid_pdu_msg.extend(struct.pack('!I', 1234))  # Request ID
        invalid_pdu_msg.append(0x99)                      # Invalid PDU type
        invalid_pdu_msg.append(1)                         # OID count
        
        try:
            unpack_message(bytes(invalid_pdu_msg))
            assert False, "Should raise ValueError for invalid PDU type"
        except (ValueError, KeyError):
            pass  # Expected
        
        # Test message with declared size not matching actual
        size_mismatch = bytearray()
        size_mismatch.extend(struct.pack('!I', 100))     # Claim 100 bytes
        size_mismatch.extend(struct.pack('!I', 1234))    # Request ID
        size_mismatch.append(0xA0)                        # Valid PDU type
        size_mismatch.append(0)                           # No OIDs
        # Actual size is only 10 bytes, not 100
        
        # Should detect size mismatch
        try:
            unpack_message(bytes(size_mismatch))
            assert False, "Should raise error for size mismatch"
        except (ValueError, IndexError):
            pass  # Expected
    
    @pytest.mark.bundle(3)
    @pytest.mark.points(2)
    def test_oid_encoding_edge_cases(self):
        """Test OID encoding with boundary conditions."""
        from src.snmp_protocol import encode_oid
        import struct
        
        # Test empty OID handling
        try:
            encode_oid("")
            assert False, "Should raise error for empty OID"
        except (ValueError, AttributeError):
            pass  # Expected
        
        # Test single component
        result = encode_oid("0")
        assert result == b'\x00', f"Single component OID failed: got {result.hex()}"
        
        # Test maximum byte value components (README: "Numbers must be 0-255")
        result = encode_oid("255.255.255")
        assert result == b'\xff\xff\xff', f"Max byte values failed: got {result.hex()}"
        
        # Test component overflow (README: "Numbers must be 0-255")
        try:
            encode_oid("256.1.2")
            assert False, "Should raise error for component > 255"
        except (ValueError, OverflowError, struct.error):
            pass  # Expected
        
        # Test negative component (not allowed per README)
        try:
            encode_oid("-1.2.3")
            assert False, "Should raise error for negative component"
        except ValueError:
            pass  # Expected
    
    @pytest.mark.bundle(3)
    @pytest.mark.points(2)
    def test_value_encoding_boundaries(self):
        """Test value encoding with boundary conditions."""
        from src.snmp_protocol import ValueType, encode_value
        import struct
        
        # Test INTEGER boundaries (32-bit signed)
        test_integers = [
            (0, b'\x00\x00\x00\x00'),
            (-1, b'\xff\xff\xff\xff'),
            (2147483647, b'\x7f\xff\xff\xff'),   # Max 32-bit signed
            (-2147483648, b'\x80\x00\x00\x00'),  # Min 32-bit signed
        ]
        
        for value, expected in test_integers:
            result = encode_value(value, ValueType.INTEGER)
            assert result == expected, \
                f"INTEGER encoding failed for {value}: got {result.hex()}, expected {expected.hex()}"
        
        # Test INTEGER overflow
        try:
            encode_value(2147483648, ValueType.INTEGER)  # Too large for signed 32-bit
            assert False, "Should raise error for INTEGER overflow"
        except (OverflowError, struct.error):
            pass  # Expected
        
        # Test COUNTER boundaries (32-bit unsigned)
        test_counters = [
            (0, b'\x00\x00\x00\x00'),
            (4294967295, b'\xff\xff\xff\xff'),  # Max 32-bit unsigned
        ]
        
        for value, expected in test_counters:
            result = encode_value(value, ValueType.COUNTER)
            assert result == expected, \
                f"COUNTER encoding failed for {value}: got {result.hex()}, expected {expected.hex()}"
        
        # Test negative counter (should fail - counters are unsigned)
        try:
            encode_value(-1, ValueType.COUNTER)
            assert False, "Should raise error for negative COUNTER"
        except (OverflowError, struct.error):
            pass  # Expected
        
        # Test STRING edge cases (reasonable sizes)
        test_strings = [
            "",                # Empty string
            "A",               # Single character
            "A" * 100,         # Reasonable size string
            "Hello\nWorld",    # Newlines
        ]
        
        for value in test_strings:
            encoded = encode_value(value, ValueType.STRING)
            decoded = encoded.decode('utf-8')
            assert decoded == value, f"STRING encoding failed for '{value}'"
    
    @pytest.mark.bundle(3)
    @pytest.mark.points(2)
    def test_message_packing_limits(self):
        """Test message packing with various OID/binding counts."""
        from src.snmp_protocol import GetRequest, SetRequest, ValueType
        
        # Test empty OID list
        req = GetRequest(request_id=1234, oids=[])
        packed = req.pack()
        assert packed[9] == 0, f"Empty OID list should have count 0, got {packed[9]}"
        
        # Test single OID
        req = GetRequest(request_id=1234, oids=["1.3.6.1"])
        packed = req.pack()
        assert packed[9] == 1, f"Single OID should have count 1, got {packed[9]}"
        
        # Test reasonable number of OIDs (10)
        oids = [f"1.3.6.1.2.1.2.2.1.1.{i}" for i in range(10)]
        req = GetRequest(request_id=1234, oids=oids)
        packed = req.pack()
        assert packed[9] == 10, f"Should handle 10 OIDs, got count {packed[9]}"
        
        # Test SetRequest with reasonable bindings
        bindings = [(f"1.3.6.1.2.1.1.{i}.0", ValueType.INTEGER, i) for i in range(5)]
        set_req = SetRequest(request_id=5678, bindings=bindings)
        packed = set_req.pack()
        assert packed[9] == 5, f"Should handle 5 bindings, got count {packed[9]}"
    
    @pytest.mark.bundle(3)
    @pytest.mark.points(2)
    def test_reasonable_message_sizes(self):
        """Test message handling with realistic sizes."""
        from src.snmp_protocol import SetRequest, GetResponse, ValueType, ErrorCode, unpack_message
        
        # Test with reasonable string sizes (up to 1KB)
        test_cases = [
            ("", ValueType.STRING),                      # Empty string
            ("A" * 100, ValueType.STRING),               # 100 chars
            ("Test" * 250, ValueType.STRING),            # 1KB string
        ]
        
        for value, value_type in test_cases:
            bindings = [("1.3.6.1.2.1.1.5.0", value_type, value)]
            
            # Test SetRequest
            set_req = SetRequest(request_id=1234, bindings=bindings)
            packed = set_req.pack()
            
            # Verify size field matches
            total_size = struct.unpack('!I', packed[0:4])[0]
            assert total_size == len(packed), \
                f"Size mismatch for value length {len(value)}"
            
            # Test GetResponse
            resp = GetResponse(request_id=1234, error_code=ErrorCode.SUCCESS, bindings=bindings)
            packed_resp = resp.pack()
            
            total_size = struct.unpack('!I', packed_resp[0:4])[0]
            assert total_size == len(packed_resp), \
                f"Response size mismatch for value length {len(value)}"
            
            # Verify can unpack
            unpacked = unpack_message(packed_resp)
            assert len(unpacked.bindings) == 1, "Should have one binding"