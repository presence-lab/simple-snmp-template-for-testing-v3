# Background: Understanding SNMP

Conceptual background on what SNMP is, what it's for, and why this
assignment's version is simpler than the real protocol. The wire format
itself lives in the [Protocol Reference](protocol.html).

---

## What SNMP Is

The **Simple Network Management Protocol** has been the backbone of network
monitoring since 1988, specified across RFCs 1155, 1157, 3411, and others.
It provides a universal language for querying and configuring network
devices — routers, switches, printers, UPSes, servers — through a
hierarchical naming scheme called a **Management Information Base (MIB)**.
Every piece of exposed data, from the device's hostname to an interface's
byte counter, has a unique dotted-decimal address called an **OID**.

Three versions are in production use today. SNMPv1 is the original; SNMPv2c
added bulk operations and 64-bit counters while keeping v1's plaintext
community-string authentication; SNMPv3 adds real authentication and
encryption. This assignment implements a subset of the v1/v2c message model.

---

## Building Intuition

Think of SNMP as a universal remote control for network devices: every
button press names a thing, and the device either reports back or acts on
a command.

| Real-world concept | SNMP equivalent | Example in this assignment |
|--------------------|-----------------|----------------------------|
| TV channel number  | OID             | `1.3.6.1.2.1.1.5.0` (system name) |
| "What channel?"    | GetRequest      | Ask the agent for the current system name |
| "Channel 5"        | GetResponse     | Agent replies with `"router-main"` |
| "Change to 7"      | SetRequest      | Tell the agent to update the system name |
| "Changed to 7"     | GetResponse     | Agent echoes the new value as confirmation |

In this model, the **manager** is the remote and the **agent** is the
device. One manager typically talks to many agents — a monitoring server
might poll thousands of switches every few minutes.

---

## Industry Context

SNMP is everywhere that a network team needs a single pane of glass across
heterogeneous hardware:

- **Data centers** poll thousands of servers, switches, and PDUs on short
  intervals to feed dashboards and alerting.
- **Internet service providers** track link utilisation, error counters,
  and fiber receive levels across core and edge routers.
- **Enterprises** collect interface stats, CPU load, and environmental
  data (temperature, fan speed) from switches and access points.
- **Cloud providers** expose SNMP-derived metrics from virtualised
  infrastructure so tenants can monitor their slice of shared hardware.

Tools such as Nagios, Zabbix, LibreNMS, SolarWinds, and Datadog all speak
SNMP natively. The protocol has been displaced in greenfield cloud
deployments by newer alternatives (streaming telemetry over gNMI, Prometheus
`node_exporter`), but it remains deployed on the vast majority of physical
network equipment and will be for years to come.

---

## Why This Version Is Simpler

Real SNMP on the wire is harder to implement than the version in this
assignment, primarily because it uses **ASN.1 / BER** encoding. In BER:

- Every field is a tag-length-value triple with variable-length encoding.
- OID components can exceed one byte using multi-byte continuation encoding.
- Integers use two's-complement with the shortest possible byte length.
- Authentication is a cleartext "community string" field (or, in SNMPv3,
  a USM security model with keyed hashes and encryption).

All of that is worth understanding — but the interesting engineering
lessons (binary protocol design, length-prefix framing, client/server
architecture, buffered reads over TCP) are the same with or without BER.
This assignment therefore strips the protocol down to:

- Fixed 4-byte big-endian integers where real SNMP uses variable-length.
- Single-byte OID components where real SNMP uses BER-encoded components.
- No authentication or community strings at all.
- TCP transport so you can practice length-prefix framing and buffering;
  real SNMP uses UDP for requests and TCP only for bulk transfers.

If you later implement the real protocol (or use a library such as
`pysnmp`), the concepts in this assignment carry over directly — you will
recognise the PDU types, the OID structure, and the request/response model.
Only the byte-level encoding changes.

---

## Further Reading

- **RFC 1157** — the original SNMPv1 specification.
- **RFC 3416** — current SNMP protocol operations.
- **Python `struct` module** — [docs.python.org/3/library/struct.html](https://docs.python.org/3/library/struct.html)
- **Python `socket` module** — [docs.python.org/3/library/socket.html](https://docs.python.org/3/library/socket.html)
