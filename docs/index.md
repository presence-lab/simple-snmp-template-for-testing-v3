# Simple SNMP — Project Documentation

This site mirrors the project's `docs/` folder. In-code comments link here
when a function has deep-dive detail that would otherwise clutter the source.

## Contents

- [Background](background.html) — what SNMP is, why it matters, how this
  simplified version differs from the real protocol
- [Protocol Reference](protocol.html) — wire format, OID encoding, value types,
  message structure, PDU layouts, buffering
- [SNMP Agent (Server)](agent.html) — server lifecycle, request dispatch,
  GET/SET semantics, error codes, state management
- [SNMP Manager (Client)](manager.html) — CLI contract, connection, value
  type conversion, response display
- [Debugging Guide](debugging.html) — byte-order, framing, and socket
  pitfalls with diagnostic snippets and a throwaway-harness pattern

The project overview, setup instructions, and grading rules live in the
[README](https://github.com/Clemson-CPSC-3600/simple-SNMP-template#readme).
