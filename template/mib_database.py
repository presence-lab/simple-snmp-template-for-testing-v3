#!/usr/bin/env python3
"""
MIB Database for SNMP Agent
Contains the Management Information Base structure and permissions

This file simulates the Management Information Base (MIB) that exists in real network
devices like routers, switches, and servers. In production environments, this data would
be dynamically gathered from the actual hardware and operating system.

=========================================================================================
MIB TREE STRUCTURE AND OID HIERARCHY
=========================================================================================

The MIB follows a hierarchical tree structure, similar to a filesystem or DNS:

                                     root
                                       |
                    iso(1) ------------|
                       |
                    org(3) ------------|
                       |
                    dod(6) ------------|
                       |
                 internet(1) ----------|
                       |
        +--------------+---------------+---------------+
        |              |               |               |
    directory(1)    mgmt(2)       experimental(3)   private(4)
                       |                               |
                    mib-2(1)                     enterprises(1)
                       |                               |
        +--------------+---------------+        (vendor-specific)
        |              |               |
    system(1)    interfaces(2)    ... snmp(11)

Each node is identified by an Object Identifier (OID) - a sequence of numbers:
- 1.3.6.1.2.1.1 = iso.org.dod.internet.mgmt.mib-2.system
- The trailing .0 indicates a scalar (single) value, not a table entry

OID FORMAT EXAMPLES:
- Scalar: 1.3.6.1.2.1.1.5.0 (sysName - single value for the whole system)
- Table:  1.3.6.1.2.1.2.2.1.2.1 (ifDescr for interface 1 - last digit is the index)

=========================================================================================
REAL-WORLD CONTEXT
=========================================================================================

Network administrators use SNMP to monitor thousands of devices across data centers.
Companies like Amazon, Google, and Microsoft rely on SNMP for:
- Detecting network outages before users notice
- Tracking bandwidth usage for capacity planning
- Monitoring device health (temperature, CPU, memory)
- Automating network configuration changes

This MIB simulates a high-performance edge router that might connect a corporate
network to the internet, handling millions of packets per second.

=========================================================================================
"""

# MIB Database - Each entry is a (type, value) tuple
# Types: STRING (text), INTEGER (number), COUNTER (always increasing), 
#        TIMETICKS (time in 1/100 seconds), OID (object identifier)
MIB_DATABASE = {
    # ===================================================================================
    # SYSTEM GROUP (1.3.6.1.2.1.1) - Basic device information
    # Real routers expose this info so administrators know what device they're managing
    # ===================================================================================
    '1.3.6.1.2.1.1.1.0': ('STRING', 'Router Model X2000 - High Performance Edge Router'),
    '1.3.6.1.2.1.1.2.0': ('OID', '1.3.6.1.4.1.9.1.1234'),  # Vendor's unique product ID
    '1.3.6.1.2.1.1.3.0': ('TIMETICKS', 0),  # Time since device booted (1/100 sec units)
    '1.3.6.1.2.1.1.4.0': ('STRING', 'admin@example.com'),  # Contact person (writable!)
    '1.3.6.1.2.1.1.5.0': ('STRING', 'router-main'),  # Device hostname (writable!)
    '1.3.6.1.2.1.1.6.0': ('STRING', 'Server Room, Building A, Floor 2'),  # Physical location (writable!)
    '1.3.6.1.2.1.1.7.0': ('INTEGER', 72),  # Binary flags for network services provided
    
    # ===================================================================================
    # INTERFACES GROUP (1.3.6.1.2.1.2) - Network interface statistics
    # Every network device has interfaces (ports) that connect to networks.
    # This router has 3 interfaces: WAN (internet), LAN (internal), and loopback (self)
    # ===================================================================================
    '1.3.6.1.2.1.2.1.0': ('INTEGER', 3),  # Total number of network interfaces
    
    # ---------------------------------------------------------------------------
    # Interface Table (1.3.6.1.2.1.2.2.1) - Each interface has multiple attributes
    # Table OIDs end with: ...column.row (e.g., ...1.1 = column 1, row 1)
    # ---------------------------------------------------------------------------
    
    # Interface 1 - WAN (Wide Area Network - connects to internet service provider)
    '1.3.6.1.2.1.2.2.1.1.1': ('INTEGER', 1),  # Unique interface identifier
    '1.3.6.1.2.1.2.2.1.2.1': ('STRING', 'eth0'),  # Interface name in operating system
    '1.3.6.1.2.1.2.2.1.3.1': ('INTEGER', 6),  # Type: 6=Ethernet, 24=loopback, 131=tunnel
    '1.3.6.1.2.1.2.2.1.4.1': ('INTEGER', 1500),  # Maximum packet size in bytes
    '1.3.6.1.2.1.2.2.1.5.1': ('COUNTER', 1000000000),  # Speed in bits per second (1 Gbps)
    '1.3.6.1.2.1.2.2.1.6.1': ('STRING', '00:1B:44:11:3A:B7'),  # MAC address
    '1.3.6.1.2.1.2.2.1.7.1': ('INTEGER', 1),  # Admin wants it: 1=up, 2=down, 3=testing
    '1.3.6.1.2.1.2.2.1.8.1': ('INTEGER', 1),  # Actual state: 1=up, 2=down, 3=testing
    '1.3.6.1.2.1.2.2.1.9.1': ('TIMETICKS', 0),  # When status last changed
    '1.3.6.1.2.1.2.2.1.10.1': ('COUNTER', 3456789012),  # Total bytes received
    '1.3.6.1.2.1.2.2.1.11.1': ('COUNTER', 23456789),  # Unicast packets received
    '1.3.6.1.2.1.2.2.1.12.1': ('COUNTER', 123456),  # Broadcast/multicast packets received
    '1.3.6.1.2.1.2.2.1.13.1': ('COUNTER', 234),  # Packets dropped (buffer full)
    '1.3.6.1.2.1.2.2.1.14.1': ('COUNTER', 12),  # Packets with errors (CRC, etc.)
    '1.3.6.1.2.1.2.2.1.15.1': ('COUNTER', 0),  # Unknown protocol packets
    '1.3.6.1.2.1.2.2.1.16.1': ('COUNTER', 2345678901),  # Total bytes sent
    '1.3.6.1.2.1.2.2.1.17.1': ('COUNTER', 12345678),  # Unicast packets sent
    '1.3.6.1.2.1.2.2.1.18.1': ('STRING', 'WAN Interface - ISP Connection'),  # Description (writable!)
    
    # Interface 2 - LAN (Local Area Network - connects to internal company network)
    '1.3.6.1.2.1.2.2.1.1.2': ('INTEGER', 2),  # Interface index 2
    '1.3.6.1.2.1.2.2.1.2.2': ('STRING', 'eth1'),  # Second ethernet port
    '1.3.6.1.2.1.2.2.1.3.2': ('INTEGER', 6),  # Ethernet type
    '1.3.6.1.2.1.2.2.1.4.2': ('INTEGER', 1500),  # Standard Ethernet MTU
    '1.3.6.1.2.1.2.2.1.5.2': ('COUNTER', 1000000000),  # 1 Gbps LAN speed
    '1.3.6.1.2.1.2.2.1.6.2': ('STRING', '00:1B:44:11:3A:B8'),  # Different MAC address
    '1.3.6.1.2.1.2.2.1.7.2': ('INTEGER', 1),  # Admin status: up
    '1.3.6.1.2.1.2.2.1.8.2': ('INTEGER', 1),  # Operational status: up
    '1.3.6.1.2.1.2.2.1.9.2': ('TIMETICKS', 0),  # Last status change
    '1.3.6.1.2.1.2.2.1.10.2': ('COUNTER', 1876543210),  # Bytes in
    '1.3.6.1.2.1.2.2.1.11.2': ('COUNTER', 8765432),  # Unicast packets in
    '1.3.6.1.2.1.2.2.1.12.2': ('COUNTER', 54321),  # Non-unicast packets in
    '1.3.6.1.2.1.2.2.1.13.2': ('COUNTER', 123),  # Discarded inbound
    '1.3.6.1.2.1.2.2.1.14.2': ('COUNTER', 5),  # Inbound errors
    '1.3.6.1.2.1.2.2.1.15.2': ('COUNTER', 0),  # Unknown protocols
    '1.3.6.1.2.1.2.2.1.16.2': ('COUNTER', 987654321),  # Bytes out
    '1.3.6.1.2.1.2.2.1.17.2': ('COUNTER', 4567890),  # Unicast packets out
    '1.3.6.1.2.1.2.2.1.18.2': ('STRING', 'LAN Interface - Internal Network'),  # Alias (writable!)
    
    # Interface 3 - Loopback (virtual interface for device to communicate with itself)
    # Used for testing and internal services - always up, no physical hardware
    '1.3.6.1.2.1.2.2.1.1.3': ('INTEGER', 3),  # Interface index 3
    '1.3.6.1.2.1.2.2.1.2.3': ('STRING', 'lo'),  # Standard loopback name
    '1.3.6.1.2.1.2.2.1.3.3': ('INTEGER', 24),  # Type 24 = software loopback
    '1.3.6.1.2.1.2.2.1.4.3': ('INTEGER', 65536),  # Larger MTU for local traffic
    '1.3.6.1.2.1.2.2.1.5.3': ('COUNTER', 0),  # No speed limit (it's virtual)
    '1.3.6.1.2.1.2.2.1.6.3': ('STRING', ''),  # No MAC address (not physical)
    '1.3.6.1.2.1.2.2.1.7.3': ('INTEGER', 1),  # Always administratively up
    '1.3.6.1.2.1.2.2.1.8.3': ('INTEGER', 1),  # Always operationally up
    '1.3.6.1.2.1.2.2.1.9.3': ('TIMETICKS', 0),  # Never changes
    '1.3.6.1.2.1.2.2.1.10.3': ('COUNTER', 567890),  # Some local traffic
    '1.3.6.1.2.1.2.2.1.11.3': ('COUNTER', 4567),  # Local packets
    '1.3.6.1.2.1.2.2.1.12.3': ('COUNTER', 0),  # No broadcasts on loopback
    '1.3.6.1.2.1.2.2.1.13.3': ('COUNTER', 0),  # Never discards (infinite buffer)
    '1.3.6.1.2.1.2.2.1.14.3': ('COUNTER', 0),  # No errors (it's virtual)
    '1.3.6.1.2.1.2.2.1.15.3': ('COUNTER', 0),  # All protocols known
    '1.3.6.1.2.1.2.2.1.16.3': ('COUNTER', 567890),  # Outbound = inbound (looped)
    '1.3.6.1.2.1.2.2.1.17.3': ('COUNTER', 4567),  # Same packet count
    '1.3.6.1.2.1.2.2.1.18.3': ('STRING', 'Loopback Interface'),  # Description (writable!)
    
    # ===================================================================================
    # IP GROUP (1.3.6.1.2.1.4) - Internet Protocol statistics
    # Tracks how the router handles IP packets - the foundation of internet communication
    # ===================================================================================
    '1.3.6.1.2.1.4.1.0': ('INTEGER', 1),  # Router forwards packets (1) vs host only (2)
    '1.3.6.1.2.1.4.2.0': ('INTEGER', 64),  # Time-to-live for new packets (hops)
    '1.3.6.1.2.1.4.3.0': ('COUNTER', 98765432),  # Total IP packets received
    '1.3.6.1.2.1.4.4.0': ('COUNTER', 1234),  # Packets with bad IP headers
    '1.3.6.1.2.1.4.5.0': ('COUNTER', 456),  # Packets with invalid addresses
    '1.3.6.1.2.1.4.6.0': ('COUNTER', 87654321),  # Packets forwarded to other networks
    '1.3.6.1.2.1.4.9.0': ('COUNTER', 76543210),  # Packets delivered to this device
    '1.3.6.1.2.1.4.10.0': ('COUNTER', 65432109),  # Packets this device sent
    
    # ===================================================================================
    # TCP GROUP (1.3.6.1.2.1.6) - Transmission Control Protocol statistics
    # TCP provides reliable, ordered delivery of data - used by web, email, file transfer
    # ===================================================================================
    '1.3.6.1.2.1.6.1.0': ('INTEGER', 2),  # Retransmission timeout algorithm (2=constant)
    '1.3.6.1.2.1.6.2.0': ('INTEGER', 200),  # Minimum retransmission timeout (milliseconds)
    '1.3.6.1.2.1.6.3.0': ('INTEGER', 120000),  # Maximum retransmission timeout (2 minutes)
    '1.3.6.1.2.1.6.4.0': ('INTEGER', -1),  # Max connections (-1 = dynamic/unlimited)
    '1.3.6.1.2.1.6.5.0': ('COUNTER', 234567),  # Outgoing connection attempts
    '1.3.6.1.2.1.6.6.0': ('COUNTER', 345678),  # Incoming connection requests
    '1.3.6.1.2.1.6.7.0': ('COUNTER', 123),  # Failed connection attempts
    '1.3.6.1.2.1.6.8.0': ('COUNTER', 234),  # Connections reset/dropped
    '1.3.6.1.2.1.6.9.0': ('INTEGER', 42),  # Currently established connections
    '1.3.6.1.2.1.6.10.0': ('COUNTER', 12345678),  # TCP segments received
    '1.3.6.1.2.1.6.11.0': ('COUNTER', 11234567),  # TCP segments sent
    '1.3.6.1.2.1.6.12.0': ('COUNTER', 456),  # Segments retransmitted (packet loss indicator)
    
    # ===================================================================================
    # UDP GROUP (1.3.6.1.2.1.7) - User Datagram Protocol statistics
    # UDP provides fast, unreliable delivery - used by DNS, gaming, video streaming
    # ===================================================================================
    '1.3.6.1.2.1.7.1.0': ('COUNTER', 3456789),  # UDP datagrams received
    '1.3.6.1.2.1.7.2.0': ('COUNTER', 789),  # Datagrams for closed ports (triggers ICMP)
    '1.3.6.1.2.1.7.3.0': ('COUNTER', 123),  # Datagrams with errors (checksum, etc.)
    '1.3.6.1.2.1.7.4.0': ('COUNTER', 2345678),  # UDP datagrams sent
    
    # ===================================================================================
    # SNMP GROUP (1.3.6.1.2.1.11) - SNMP protocol statistics
    # Meta-statistics: SNMP monitoring its own performance!
    # ===================================================================================
    '1.3.6.1.2.1.11.1.0': ('COUNTER', 54321),  # Total SNMP messages received
    '1.3.6.1.2.1.11.2.0': ('COUNTER', 43210),  # Total SNMP messages sent
    '1.3.6.1.2.1.11.3.0': ('COUNTER', 5),  # Wrong SNMP version (v1 vs v2c vs v3)
    '1.3.6.1.2.1.11.4.0': ('COUNTER', 2),  # Invalid community string (wrong password)
    '1.3.6.1.2.1.11.5.0': ('COUNTER', 1),  # Community string OK but no permission
    '1.3.6.1.2.1.11.6.0': ('COUNTER', 0),  # Malformed SNMP packet structure
}

# ===================================================================================
# ENTERPRISE/VENDOR-SPECIFIC OIDs (1.3.6.1.4.1)
# Real devices have thousands of vendor-specific OIDs for proprietary features.
# We simulate this with test data to practice handling large responses.
# ===================================================================================
for i in range(1, 51):
    # These simulate vendor-specific monitoring data that doesn't fit standard MIBs
    MIB_DATABASE[f'1.3.6.1.4.1.99.1.{i}.0'] = ('STRING', f'Test OID {i} - This is a longer string to help test buffering of large SNMP messages')

# ===================================================================================
# PERMISSIONS MODEL
# ===================================================================================
# SNMP distinguishes between read-only and read-write access.
# In production, this would be controlled by SNMPv3 user-based security or
# SNMPv2c community strings with different privileges.
#
# WHY CERTAIN OIDs ARE WRITABLE:
# - sysContact, sysName, sysLocation: Administrators need to update these when
#   devices are relocated, ownership changes, or naming conventions update
# - Interface aliases: Network teams add descriptions to identify circuit IDs,
#   connection purposes, or link to documentation
#
# WHY MOST OIDs ARE READ-ONLY:
# - Statistics and counters must reflect actual system state
# - Hardware information cannot be changed via software
# - Changing operational parameters could destabilize the network
# ===================================================================================

# Define which OIDs can be modified via SNMP SET operations
MIB_PERMISSIONS = {
    # System group - administrative information that changes over time
    '1.3.6.1.2.1.1.1.0': 'read-only',     # Device description - fixed hardware info
    '1.3.6.1.2.1.1.2.0': 'read-only',     # Object ID - fixed vendor identifier  
    '1.3.6.1.2.1.1.3.0': 'read-only',     # Uptime - system controlled
    '1.3.6.1.2.1.1.4.0': 'read-write',    # Contact person - needs updating
    '1.3.6.1.2.1.1.5.0': 'read-write',    # Device name - may change
    '1.3.6.1.2.1.1.6.0': 'read-write',    # Physical location - devices move
    '1.3.6.1.2.1.1.7.0': 'read-only',     # Services - fixed capabilities
    
    # Interface alias fields - network admins add circuit descriptions
    '1.3.6.1.2.1.2.2.1.18.1': 'read-write',  # WAN interface description
    '1.3.6.1.2.1.2.2.1.18.2': 'read-write',  # LAN interface description  
    '1.3.6.1.2.1.2.2.1.18.3': 'read-write',  # Loopback interface description
}

# Set default permissions for all remaining OIDs
# In production, this would be more granular based on security policies
for oid in MIB_DATABASE:
    if oid not in MIB_PERMISSIONS:
        MIB_PERMISSIONS[oid] = 'read-only'