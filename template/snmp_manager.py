#!/usr/bin/env python3
"""SNMP Manager — the client that sends requests to SNMP agents.

Client-side socket lifecycle: create → configure → connect → send → recv → close.

Full walkthrough (CLI contract, worked examples, reference implementation):
https://clemson-cpsc-3600.github.io/simple-SNMP-template/manager.html
"""

import socket
import sys
import struct
import random
import time
from typing import List, Tuple, Optional, Any

# Import protocol components (you'll implement these in snmp_protocol.py)
from .snmp_protocol import (
    PDUType, ValueType, ErrorCode,
    GetRequest, SetRequest, GetResponse,
    receive_complete_message, unpack_message
)

# ============================================================================
# CONSTANTS (PROVIDED - DO NOT MODIFY)
# ============================================================================

DEFAULT_TIMEOUT = 10.0  # Socket timeout in seconds
TIMETICKS_PER_SECOND = 100  # SNMP timeticks are 1/100 second

# ============================================================================
# PROVIDED: Display formatting functions
# ============================================================================

def format_timeticks(ticks: int) -> str:
    """PROVIDED: Convert timeticks to a human-readable uptime string."""
    total_seconds = ticks / TIMETICKS_PER_SECOND
    days = int(total_seconds // 86400)
    hours = int((total_seconds % 86400) // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = total_seconds % 60

    parts = []
    if days > 0:
        parts.append(f"{days} days")
    if hours > 0:
        parts.append(f"{hours} hours")
    if minutes > 0:
        parts.append(f"{minutes} minutes")
    if seconds > 0 or len(parts) == 0:
        parts.append(f"{seconds:.2f} seconds")

    return f"{ticks} ({', '.join(parts)})"

def format_value(value_type: ValueType, value: Any) -> str:
    """PROVIDED: Format any value for display based on its type."""
    if value_type == ValueType.TIMETICKS:
        return format_timeticks(value)
    elif value_type == ValueType.COUNTER:
        # Add thousands separators for readability
        return f"{value:,}"
    else:
        return str(value)

def format_error(error_code: ErrorCode) -> str:
    """PROVIDED: Convert error codes to human-readable messages."""
    error_messages = {
        ErrorCode.NO_SUCH_OID: "No such OID exists",
        ErrorCode.BAD_VALUE: "Bad value for OID type",
        ErrorCode.READ_ONLY: "OID is read-only"
    }
    return error_messages.get(error_code, f"Unknown error ({error_code})")

# ============================================================================
# SNMP MANAGER CLASS
# ============================================================================

class SNMPManager:
    """SNMP client that sends GetRequest / SetRequest messages to an agent.

    See https://clemson-cpsc-3600.github.io/simple-SNMP-template/manager.html
    """

    def __init__(self):
        # Random starting request ID reduces collisions across manager restarts.
        self.request_id = random.randint(1, 10000)

    def _get_next_request_id(self) -> int:
        """PROVIDED: Return a fresh request ID for correlating a response."""
        self.request_id += 1
        return self.request_id

    # ========================================================================
    # STUDENT IMPLEMENTATION: Core operations
    # ========================================================================

    def get(self, host: str, port: int, oids: List[str]) -> None:
        """Send a GetRequest for one or more OIDs and print the response.

        Args:
            host: agent hostname or IP.
            port: agent TCP port.
            oids: list of dotted-decimal OID strings.

        On success, prints one ``oid = value`` line per binding. On error,
        prints ``Error: <message>``. Socket is always closed via ``finally``.

        Bundle 1 requirement. Full walkthrough (lifecycle, display format,
        common mistakes):
        https://clemson-cpsc-3600.github.io/simple-SNMP-template/manager.html#sending-a-get-request
        """
        sock = None
        try:
            # TODO: connect, send GetRequest, receive + unpack response,
            # verify type + request_id match, then display bindings or error.
            raise NotImplementedError(
                "Implement get — see "
                "https://clemson-cpsc-3600.github.io/simple-SNMP-template/manager.html#sending-a-get-request"
            )

        except socket.timeout:
            print(f"Error: Request timed out after {DEFAULT_TIMEOUT} seconds")
        except ConnectionRefusedError:
            print(f"Error: Cannot connect to {host}:{port} - is the agent running?")
        except Exception as e:
            print(f"Error: {e}")
        finally:
            # Always close the socket to avoid resource leaks.
            if sock:
                sock.close()

    def set(self, host: str, port: int, oid: str, value_type: str, value: str) -> None:
        """Send a SetRequest to modify an OID's value and print the response.

        Args:
            host: agent hostname or IP.
            port: agent TCP port.
            oid: dotted-decimal OID to modify.
            value_type: one of ``integer``, ``string``, ``counter``, ``timeticks``.
            value: raw CLI string; converted to the correct Python type below.

        Bundle 2 requirement. Full walkthrough (value conversion, error cases):
        https://clemson-cpsc-3600.github.io/simple-SNMP-template/manager.html#sending-a-set-request
        """
        # PROVIDED: Parse value type
        type_map = {
            'integer': ValueType.INTEGER,
            'string': ValueType.STRING,
            'counter': ValueType.COUNTER,
            'timeticks': ValueType.TIMETICKS
        }

        if value_type.lower() not in type_map:
            print(f"Error: Invalid value type '{value_type}'. Must be one of: {', '.join(type_map.keys())}")
            return

        vtype = type_map[value_type.lower()]

        # TODO: Convert `value` (string) to the Python type for `vtype`.
        #       integer -> int, string -> str, counter/timeticks -> int >= 0.
        # TODO: Connect, send SetRequest, receive + unpack response, display.

        raise NotImplementedError(
            "Implement set — see "
            "https://clemson-cpsc-3600.github.io/simple-SNMP-template/manager.html#sending-a-set-request"
        )

    # ========================================================================
    # STUDENT IMPLEMENTATION: Helper methods
    # ========================================================================

    def _connect_to_agent(self, host: str, port: int) -> socket.socket:
        """Create a TCP socket, set a timeout, connect to (host, port), return it.

        Both :meth:`get` and :meth:`set` use this helper so connection setup
        lives in one place. Must set ``settimeout(DEFAULT_TIMEOUT)`` BEFORE
        calling ``connect``.

        https://clemson-cpsc-3600.github.io/simple-SNMP-template/manager.html#connecting-to-the-agent
        """
        # TODO: socket.socket(AF_INET, SOCK_STREAM) -> settimeout -> connect -> return
        raise NotImplementedError(
            "Implement _connect_to_agent — see "
            "https://clemson-cpsc-3600.github.io/simple-SNMP-template/manager.html#connecting-to-the-agent"
        )

# ============================================================================
# PROVIDED: Command-line interface
# ============================================================================

def print_usage():
    """PROVIDED: Print usage information"""
    print("Usage:")
    print("  snmp_manager.py get <host:port> <oid> [<oid> ...]")
    print("  snmp_manager.py set <host:port> <oid> <type> <value>")
    print("  snmp_manager.py bulk <host:port> <start_oid> <max_repetitions>")
    print()
    print("Examples:")
    print("  snmp_manager.py get localhost:1161 1.3.6.1.2.1.1.1.0")
    print("  snmp_manager.py get localhost:1161 1.3.6.1.2.1.1.1.0 1.3.6.1.2.1.1.5.0")
    print("  snmp_manager.py set localhost:1161 1.3.6.1.2.1.1.5.0 string 'new-router-name'")
    print("  snmp_manager.py bulk localhost:1161 1.3.6.1.2.1.2.2.1 50")
    print()
    print("Types: integer, string, counter, timeticks")

def parse_host_port(host_port: str) -> Tuple[str, int]:
    """PROVIDED: Parse host:port string"""
    parts = host_port.split(':')
    if len(parts) != 2:
        raise ValueError("Invalid host:port format. Use 'hostname:port' or 'ip:port'")

    host = parts[0]
    try:
        port = int(parts[1])
        if not 1 <= port <= 65535:
            raise ValueError("Port must be between 1 and 65535")
    except ValueError:
        raise ValueError(f"Invalid port number: {parts[1]}")

    return host, port

def main():
    """PROVIDED: Main entry point. Parses argv and dispatches to get/set."""
    if len(sys.argv) < 3:
        print_usage()
        sys.exit(1)

    command = sys.argv[1].lower()

    try:
        host, port = parse_host_port(sys.argv[2])
    except ValueError as e:
        print(f"Error: {e}")
        print_usage()
        sys.exit(1)

    manager = SNMPManager()

    if command == 'get':
        if len(sys.argv) < 4:
            print("Error: No OIDs specified")
            print_usage()
            sys.exit(1)

        oids = sys.argv[3:]
        manager.get(host, port, oids)

    elif command == 'set':
        if len(sys.argv) != 6:
            print("Error: Set requires exactly 4 arguments: host:port oid type value")
            print_usage()
            sys.exit(1)

        oid = sys.argv[3]
        value_type = sys.argv[4]
        value = sys.argv[5]
        manager.set(host, port, oid, value_type, value)

    else:
        print(f"Error: Unknown command '{command}'")
        print_usage()
        sys.exit(1)

if __name__ == "__main__":
    main()
