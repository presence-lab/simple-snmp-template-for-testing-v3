"""
SNMP Protocol Implementation
Contains message classes and encoding/decoding logic for simplified SNMP.

Tutorial walkthroughs for every function and class in this file live at:
https://clemson-cpsc-3600.github.io/simple-SNMP-template/protocol.html

The README is the authoritative wire-format specification; these docs are the
learning companion.
"""

import struct
import logging
from abc import ABC, abstractmethod
from typing import List, Tuple, Dict, Any, Optional
from enum import IntEnum

# Protocol Constants
MESSAGE_HEADER_SIZE = 9  # total_size(4) + request_id(4) + pdu_type(1)
RESPONSE_HEADER_SIZE = 10  # MESSAGE_HEADER_SIZE + error_code(1)
MAX_RECV_BUFFER = 4096  # Maximum bytes to receive at once
MIN_MESSAGE_SIZE = 9  # Minimum valid message size
MAX_MESSAGE_SIZE = 65536  # Maximum message size (64KB) to prevent memory exhaustion
SIZE_FIELD_LENGTH = 4  # Length of the size field in bytes
REQUEST_ID_LENGTH = 4  # Length of request ID field
PDU_TYPE_LENGTH = 1  # Length of PDU type field in bytes
ERROR_CODE_LENGTH = 1  # Length of error code field in bytes
OID_COUNT_LENGTH = 1  # Length of OID count field in bytes
OID_LENGTH_FIELD = 1  # Length of OID length field in bytes
VALUE_TYPE_LENGTH = 1  # Length of value type field in bytes
VALUE_LENGTH_FIELD = 2  # Length of value length field in bytes
MAX_REPETITIONS_LENGTH = 2  # Length of max repetitions field in bytes
OID_COUNT_MAX = 255  # Maximum OIDs in a single request
MAX_REPETITIONS_MAX = 65535  # Maximum repetitions for bulk request
PDU_TYPE_OFFSET = 8  # Offset where PDU type is located in message
REQUEST_ID_OFFSET = 4  # Offset where request ID starts in message

# Configure module logger
logger = logging.getLogger('snmp.protocol')

# PDU Types (Protocol Data Unit types - the different message types in SNMP)
class PDUType(IntEnum):
    GET_REQUEST = 0xA0
    GET_RESPONSE = 0xA1
    SET_REQUEST = 0xA3

# Value Types (Different data types that SNMP can handle)
class ValueType(IntEnum):
    INTEGER = 0x02      # Signed 32-bit integer
    STRING = 0x04       # UTF-8 text string
    COUNTER = 0x41      # Unsigned 32-bit counter (only goes up)
    TIMETICKS = 0x43    # Time in hundredths of seconds

# Error Codes (What can go wrong in SNMP operations)
class ErrorCode(IntEnum):
    SUCCESS = 0        # Everything worked!
    NO_SUCH_OID = 1    # The requested OID doesn't exist
    BAD_VALUE = 2      # Wrong type or invalid value for SET
    READ_ONLY = 3      # Tried to SET a read-only value

def encode_oid(oid_string: str) -> bytes:
    """Convert a dotted-decimal OID string to bytes for network transmission.

    Each component of the OID becomes one byte. Raises ValueError for empty
    input or components outside 0-255.

    Example:
        >>> encode_oid("1.3.6.1.2.1.1.5.0").hex()
        '010306010201010500'

    Bundle 1 requirement. Full walkthrough (worked example, common mistakes,
    reference implementation):
    https://clemson-cpsc-3600.github.io/simple-SNMP-template/protocol.html#oid-encoding
    """
    raise NotImplementedError(
        "Implement encode_oid — see "
        "https://clemson-cpsc-3600.github.io/simple-SNMP-template/protocol.html#oid-encoding"
    )

def decode_oid(oid_bytes: bytes) -> str:
    """Convert encoded OID bytes back to a dotted-decimal string.

    Inverse of `encode_oid`: each byte is one OID component.

    Example:
        >>> decode_oid(bytes.fromhex("010306010201010500"))
        '1.3.6.1.2.1.1.5.0'

    Bundle 1 requirement. Full walkthrough:
    https://clemson-cpsc-3600.github.io/simple-SNMP-template/protocol.html#oid-encoding
    """
    raise NotImplementedError(
        "Implement decode_oid — see "
        "https://clemson-cpsc-3600.github.io/simple-SNMP-template/protocol.html#oid-encoding"
    )

def encode_value(value: Any, value_type: ValueType) -> bytes:
    """Encode a Python value as bytes according to its SNMP ValueType.

    Supports INTEGER (signed 4 bytes), STRING (UTF-8), COUNTER and TIMETICKS
    (unsigned 4 bytes). Raises ValueError for unknown types.

    Example:
        >>> encode_value(42, ValueType.INTEGER).hex()
        '0000002a'

    Bundle 1 requirement. Full walkthrough (byte layouts per type, signed vs.
    unsigned pitfalls, reference implementation):
    https://clemson-cpsc-3600.github.io/simple-SNMP-template/protocol.html#value-encoding
    """
    raise NotImplementedError(
        "Implement encode_value — see "
        "https://clemson-cpsc-3600.github.io/simple-SNMP-template/protocol.html#value-encoding"
    )

def decode_value(value_bytes: bytes, value_type: ValueType) -> Any:
    """Decode bytes into a Python value for the given SNMP ValueType.

    Inverse of `encode_value`. Integer types require exactly 4 bytes; STRING
    accepts any valid UTF-8.

    Example:
        >>> decode_value(bytes.fromhex('0000002a'), ValueType.INTEGER)
        42

    Bundle 1 requirement. Full walkthrough:
    https://clemson-cpsc-3600.github.io/simple-SNMP-template/protocol.html#value-encoding
    """
    raise NotImplementedError(
        "Implement decode_value — see "
        "https://clemson-cpsc-3600.github.io/simple-SNMP-template/protocol.html#value-encoding"
    )

class SNMPMessage(ABC):
    """Abstract base for all SNMP messages (GetRequest, SetRequest, GetResponse).

    Every concrete subclass carries a request_id and a pdu_type, and must
    implement `pack()` to serialize to bytes and `unpack()` to deserialize.

    Header anatomy and per-PDU payload formats:
    https://clemson-cpsc-3600.github.io/simple-SNMP-template/protocol.html#message-structure
    """

    def __init__(self, request_id: int, pdu_type: PDUType):
        self.request_id = request_id
        self.pdu_type = pdu_type

    @abstractmethod
    def pack(self) -> bytes:
        """Convert message to bytes for transmission."""
        pass

    @classmethod
    @abstractmethod
    def unpack(cls, data: bytes) -> 'SNMPMessage':
        """Create message instance from received bytes."""
        pass

class GetRequest(SNMPMessage):
    """SNMP GetRequest message - requests values from the agent."""

    def __init__(self, request_id: int, oids: List[str]):
        super().__init__(request_id, PDUType.GET_REQUEST)
        self.oids = oids

    def pack(self) -> bytes:
        """Serialize this GetRequest to wire bytes.

        Layout: 9-byte header (total_size, request_id, pdu_type=0xA0) followed
        by a payload of `oid_count` and length-prefixed OIDs.

        Bundle 1 requirement. Full walkthrough (byte-by-byte example, size
        calculation, reference implementation):
        https://clemson-cpsc-3600.github.io/simple-SNMP-template/protocol.html#get-request
        """
        raise NotImplementedError(
            "Implement GetRequest.pack — see "
            "https://clemson-cpsc-3600.github.io/simple-SNMP-template/protocol.html#get-request"
        )

    @classmethod
    def unpack(cls, data: bytes) -> 'GetRequest':
        """Construct a GetRequest from received bytes.

        The caller (usually `unpack_message`) has already verified that
        `data[8] == PDUType.GET_REQUEST`.

        Bundle 2 requirement. Full walkthrough:
        https://clemson-cpsc-3600.github.io/simple-SNMP-template/protocol.html#get-request
        """
        raise NotImplementedError(
            "Implement GetRequest.unpack — see "
            "https://clemson-cpsc-3600.github.io/simple-SNMP-template/protocol.html#get-request"
        )

class SetRequest(SNMPMessage):
    """SNMP SetRequest message - updates values on the agent."""

    def __init__(self, request_id: int, bindings: List[Tuple[str, ValueType, Any]]):
        super().__init__(request_id, PDUType.SET_REQUEST)
        self.bindings = bindings  # List of (oid, value_type, value) tuples

    def pack(self) -> bytes:
        """Serialize this SetRequest to wire bytes.

        Like GetRequest but each payload entry is an OID-value binding:
        oid_length, oid_bytes, value_type, value_length (2 bytes!), value_data.

        Bundle 2 requirement. Full walkthrough:
        https://clemson-cpsc-3600.github.io/simple-SNMP-template/protocol.html#set-request
        """
        raise NotImplementedError(
            "Implement SetRequest.pack — see "
            "https://clemson-cpsc-3600.github.io/simple-SNMP-template/protocol.html#set-request"
        )

    @classmethod
    def unpack(cls, data: bytes) -> 'SetRequest':
        """Construct a SetRequest from received bytes.

        Value length is 2 bytes (!H), not 1.

        Bundle 2 requirement. Full walkthrough:
        https://clemson-cpsc-3600.github.io/simple-SNMP-template/protocol.html#set-request
        """
        raise NotImplementedError(
            "Implement SetRequest.unpack — see "
            "https://clemson-cpsc-3600.github.io/simple-SNMP-template/protocol.html#set-request"
        )

class GetResponse(SNMPMessage):
    """SNMP GetResponse message - the agent's reply to GET and SET requests."""

    def __init__(self, request_id: int, error_code: ErrorCode,
                 bindings: List[Tuple[str, ValueType, Any]]):
        super().__init__(request_id, PDUType.GET_RESPONSE)
        self.error_code = error_code
        self.bindings = bindings  # List of (oid, value_type, value) tuples

    def pack(self) -> bytes:
        """Serialize this GetResponse to wire bytes.

        GetResponse has a 10-byte header (one extra `error_code` byte between
        `pdu_type` and the payload). Bindings are encoded like SetRequest.

        Bundle 1 requirement. Full walkthrough:
        https://clemson-cpsc-3600.github.io/simple-SNMP-template/protocol.html#get-response
        """
        raise NotImplementedError(
            "Implement GetResponse.pack — see "
            "https://clemson-cpsc-3600.github.io/simple-SNMP-template/protocol.html#get-response"
        )

    @classmethod
    def unpack(cls, data: bytes) -> 'GetResponse':
        """Construct a GetResponse from received bytes.

        Remember: error_code sits at `data[9]`, and bindings start at byte 10.

        Bundle 2 requirement. Full walkthrough:
        https://clemson-cpsc-3600.github.io/simple-SNMP-template/protocol.html#get-response
        """
        raise NotImplementedError(
            "Implement GetResponse.unpack — see "
            "https://clemson-cpsc-3600.github.io/simple-SNMP-template/protocol.html#get-response"
        )

def unpack_message(data: bytes) -> SNMPMessage:
    """Dispatch a raw SNMP message to the correct concrete class based on PDU type.

    Peeks at byte 8 (pdu_type) and delegates to `GetRequest.unpack`,
    `SetRequest.unpack`, or `GetResponse.unpack`. Raises ValueError for
    truncated or unknown messages.

    Full walkthrough:
    https://clemson-cpsc-3600.github.io/simple-SNMP-template/protocol.html#unpacking-messages
    """
    if len(data) < MIN_MESSAGE_SIZE:
        logger.error("Message too short: %d bytes, minimum %d", len(data), MIN_MESSAGE_SIZE)
        raise ValueError(f"Message too short: {len(data)} bytes, minimum {MIN_MESSAGE_SIZE}")

    pdu_type = struct.unpack('!B', data[PDU_TYPE_OFFSET:PDU_TYPE_OFFSET+PDU_TYPE_LENGTH])[0]
    logger.debug("Unpacking message with PDU type 0x%02X", pdu_type)

    if pdu_type == PDUType.GET_REQUEST:
        return GetRequest.unpack(data)
    elif pdu_type == PDUType.SET_REQUEST:
        return SetRequest.unpack(data)
    elif pdu_type == PDUType.GET_RESPONSE:
        return GetResponse.unpack(data)
    else:
        logger.error("Unknown PDU type: 0x%02X", pdu_type)
        raise ValueError(f"Unknown PDU type: {pdu_type}")

def receive_complete_message(sock) -> bytes:
    """Receive exactly one complete SNMP message from a TCP socket.

    Two-phase algorithm: first read 4 bytes to learn the total message size,
    then loop until that many bytes have arrived. Chunks are capped at
    MAX_RECV_BUFFER (4096 bytes). Raises ConnectionError if the peer closes
    mid-message, ValueError for out-of-range sizes.

    Bundle 1 requirement - every network test depends on this. Full walkthrough
    (the TCP streaming problem, flowchart, reference implementation, common
    bugs):
    https://clemson-cpsc-3600.github.io/simple-SNMP-template/protocol.html#message-framing
    """
    raise NotImplementedError(
        "Implement receive_complete_message — see "
        "https://clemson-cpsc-3600.github.io/simple-SNMP-template/protocol.html#message-framing"
    )
