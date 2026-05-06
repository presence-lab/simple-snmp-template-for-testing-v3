#!/usr/bin/env python3
"""SNMP Agent — the server that listens for SNMP requests and responds.

Implements the server half of the assignment: socket lifecycle, per-client
message dispatch, GET/SET handling against the MIB, and sysUpTime upkeep.

Walkthrough (server lifecycle, handler structure, error-code table,
reference implementation, common mistakes):
https://clemson-cpsc-3600.github.io/simple-SNMP-template/agent.html
"""

import socket
import sys
import struct
import time
import signal
from typing import Dict, Any, List, Tuple, Optional

# Import protocol components (you'll implement these in snmp_protocol.py)
from .snmp_protocol import (
    PDUType, ValueType, ErrorCode,
    GetRequest, SetRequest, GetResponse,
    unpack_message, receive_complete_message,
    encode_oid, decode_oid
)

# ============================================================================
# CONSTANTS (PROVIDED - DO NOT MODIFY)
# ============================================================================

DEFAULT_PORT = 1161  # We use 1161 instead of standard 161 (no root required)
LISTEN_BACKLOG = 5   # Maximum pending connections in the accept queue
TIMEOUT_SECONDS = 10.0  # Socket timeout to prevent hanging
TIMETICKS_PER_SECOND = 100  # SNMP timeticks are 1/100 second

# ============================================================================
# MIB DATABASE (PROVIDED - DO NOT MODIFY)
# ============================================================================

# Import the MIB database (Management Information Base)
# This contains all the data our agent can serve
from mib_database import MIB_DATABASE, MIB_PERMISSIONS

# ============================================================================
# SNMP AGENT CLASS
# ============================================================================

class SNMPAgent:
    """SNMP Agent that responds to management requests."""

    def __init__(self, port: int = DEFAULT_PORT):
        self.port = port
        self.mib = dict(MIB_DATABASE)  # Create a mutable copy
        self.start_time = time.time()  # Track when agent started for uptime
        self.server_socket = None
        self.running = True

    def start(self):
        """Run the SNMP agent server: create socket, bind, listen, accept forever.

        Side effects: binds self.server_socket to self.port, prints status,
        blocks in an accept loop until KeyboardInterrupt, closes the socket on exit.

        Bundle 1 requirement. Walkthrough (socket lifecycle, SO_REUSEADDR,
        accept loop, reference implementation):
        https://clemson-cpsc-3600.github.io/simple-SNMP-template/agent.html#server-lifecycle
        """
        # TODO: Create server socket, set SO_REUSEADDR, bind to self.port, listen.
        # TODO: Loop on accept() while self.running; dispatch to _handle_client.
        # TODO: On KeyboardInterrupt, set self.running=False and break cleanly.
        # TODO: Always close self.server_socket in a finally block.
        raise NotImplementedError(
            "Implement start() - see "
            "https://clemson-cpsc-3600.github.io/simple-SNMP-template/agent.html#server-lifecycle"
        )

    def _handle_client(self, client_socket: socket.socket, client_address: Tuple[str, int]):
        """Process requests from one connected client until they disconnect or time out.

        Receives a complete message, processes it, sends the response, repeats.
        Always closes client_socket before returning.

        Bundle 1 requirement. Walkthrough (persistent-connection loop, timeouts,
        error handling, reference implementation):
        https://clemson-cpsc-3600.github.io/simple-SNMP-template/agent.html#handling-a-client
        """
        try:
            # TODO: Set client_socket.settimeout(TIMEOUT_SECONDS).
            # TODO: Loop: receive_complete_message -> _process_message -> sendall.
            # TODO: Break on ConnectionError (normal close) or socket.timeout (idle).
            # TODO: Catch other Exception, log it, and break (one bad client != crash).
            raise NotImplementedError(
                "Implement _handle_client - see "
                "https://clemson-cpsc-3600.github.io/simple-SNMP-template/agent.html#handling-a-client"
            )
        finally:
            client_socket.close()

    def _process_message(self, message_bytes: bytes) -> bytes:
        """Dispatch a raw message to the right handler and return response bytes.

        Unpacks the message, routes by class (GetRequest / SetRequest), then
        packs the GetResponse for transmission.

        Bundle 1 requirement. Walkthrough (bytes->object->object->bytes pattern,
        dispatcher, reference implementation):
        https://clemson-cpsc-3600.github.io/simple-SNMP-template/agent.html#processing-getrequest
        """
        # TODO: message = unpack_message(message_bytes)
        # TODO: isinstance check -> _handle_get_request / _handle_set_request
        # TODO: return response.pack()
        raise NotImplementedError(
            "Implement _process_message - see "
            "https://clemson-cpsc-3600.github.io/simple-SNMP-template/agent.html#processing-getrequest"
        )

    def _handle_get_request(self, request: GetRequest) -> GetResponse:
        """Return a GetResponse with values for every requested OID, or an error.

        Rules: echo request.request_id, update dynamic values first, all-or-nothing
        (one missing OID => NO_SUCH_OID for the whole request with empty bindings).

        Bundle 1 requirement. Walkthrough (all-or-nothing principle, request-id
        echo, reference implementation, common mistakes):
        https://clemson-cpsc-3600.github.io/simple-SNMP-template/agent.html#processing-getrequest
        """
        self._update_dynamic_values()

        # TODO: First pass: verify every oid in request.oids is in self.mib.
        #       On first miss, return GetResponse(request.request_id,
        #                                         ErrorCode.NO_SUCH_OID, []).
        # TODO: Second pass: build bindings as (oid, ValueType, value) using
        #       self._get_value_type(type_string) for the type.
        # TODO: Return GetResponse(request.request_id, ErrorCode.SUCCESS, bindings).
        raise NotImplementedError(
            "Implement _handle_get_request - see "
            "https://clemson-cpsc-3600.github.io/simple-SNMP-template/agent.html#processing-getrequest"
        )

    def _handle_set_request(self, request: SetRequest) -> GetResponse:
        """Validate every binding, then apply all of them atomically.

        Two-phase pattern: check existence + writability + type match for every
        binding before mutating self.mib. On any failure return the matching
        error code with an empty binding list and change nothing.

        Bundle 2 requirement. Walkthrough (validation order, error-code table,
        reference implementation, transactional integrity):
        https://clemson-cpsc-3600.github.io/simple-SNMP-template/agent.html#processing-setrequest
        """
        # TODO: PHASE 1 - validate every (oid, value_type, value) in request.bindings:
        #       - oid in self.mib?              -> NO_SUCH_OID on miss
        #       - MIB_PERMISSIONS.get(oid, 'read-only') == 'read-write'? -> READ_ONLY
        #       - value_type == self._get_value_type(stored_type_string)? -> BAD_VALUE
        # TODO: PHASE 2 - only if every binding passed: update self.mib[oid] to
        #       (original_type_string, new_value); append (oid, value_type, value)
        #       to response_bindings.
        # TODO: Return GetResponse(request.request_id, ErrorCode.SUCCESS, response_bindings).
        raise NotImplementedError(
            "Implement _handle_set_request - see "
            "https://clemson-cpsc-3600.github.io/simple-SNMP-template/agent.html#processing-setrequest"
        )

    def _update_dynamic_values(self):
        """Refresh MIB entries whose values are computed on read.

        Currently updates only sysUpTime (1.3.6.1.2.1.1.3.0) to
        int((time.time() - self.start_time) * TIMETICKS_PER_SECOND), preserving
        the stored type string 'TIMETICKS'.

        Bundle 1 requirement. Walkthrough (timeticks units, update-before-read
        pattern, reference implementation):
        https://clemson-cpsc-3600.github.io/simple-SNMP-template/agent.html#concurrency-and-state
        """
        # TODO: Compute uptime_seconds from self.start_time and time.time().
        # TODO: Convert to timeticks (uptime_seconds * TIMETICKS_PER_SECOND, int()).
        # TODO: Write self.mib['1.3.6.1.2.1.1.3.0'] = ('TIMETICKS', uptime_ticks).
        raise NotImplementedError(
            "Implement _update_dynamic_values - see "
            "https://clemson-cpsc-3600.github.io/simple-SNMP-template/agent.html#concurrency-and-state"
        )

    def _get_value_type(self, type_str: str) -> ValueType:
        """PROVIDED: map MIB type string ('INTEGER', 'STRING', ...) to ValueType enum."""
        mapping = {
            'INTEGER': ValueType.INTEGER,
            'STRING': ValueType.STRING,
            'COUNTER': ValueType.COUNTER,
            'TIMETICKS': ValueType.TIMETICKS,
        }
        return mapping.get(type_str, ValueType.STRING)

# ============================================================================
# MAIN ENTRY POINT (PROVIDED)
# ============================================================================

def main():
    """PROVIDED: main entry point with command-line parsing.

    Usage: python -m src.snmp_agent [port]
    Default port: 1161
    """
    # Parse command line arguments
    port = DEFAULT_PORT
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
            if not 1 <= port <= 65535:
                print(f"Error: Port must be between 1 and 65535")
                sys.exit(1)
        except ValueError:
            print(f"Error: Invalid port number: {sys.argv[1]}")
            sys.exit(1)

    # Create and start the agent
    agent = SNMPAgent(port)
    try:
        agent.start()
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
