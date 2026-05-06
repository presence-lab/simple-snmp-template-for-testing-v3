# Simplified SNMP Protocol Implementation

**CPSC 3600 — Networks and Network Programming**

Build a subset of the Simple Network Management Protocol: a TCP-based
binary protocol with a client (*manager*) that queries and mutates named
values on a server (*agent*). You will learn length-prefix framing,
buffered reads over TCP, and client/server design — the same patterns
used by HTTP/2, WebSocket, MQTT, and most database wire formats.

---

## Quick Links

- [Background](docs/background.md) — what SNMP is and why this version is simplified
- [Protocol Reference](docs/protocol.md) — wire format, PDUs, framing (the spec)
- [Agent (Server)](docs/agent.md) — server lifecycle, GET/SET handling, state
- [Manager (Client)](docs/manager.md) — CLI, connection, value conversion, output
- [Debugging Guide](docs/debugging.md) — byte order, framing bugs, socket errors
- [Grading](GRADING.md) — specification grading bundles and criteria
- [Testing](TESTING.md) — running tests, VS Code integration, troubleshooting

Documentation is also rendered at
[clemson-cpsc-3600.github.io/simple-SNMP-template/](https://clemson-cpsc-3600.github.io/simple-SNMP-template/).

---

## Learning Objectives

By completing this project, you will be able to:

1. **Design and implement a binary network protocol** using Python's
   `struct` module for fixed-width integers and byte-level layouts.
2. **Implement length-prefix message framing** so variable-length messages
   survive TCP's byte-stream delivery.
3. **Handle buffered reads** where one `recv()` call may return less (or
   more) than one logical message.
4. **Build a client/server application** with correct socket lifecycle,
   timeouts, and graceful error handling.
5. **Debug binary protocols systematically** using hex dumps, worked
   examples, and targeted test harnesses.

---

## Getting Started

### 1. Verify Python

```bash
python --version    # need 3.8+; try python3 if python is not found
```

### 2. Create and activate a virtual environment

```bash
python -m venv venv
source venv/bin/activate         # Linux / macOS
venv\Scripts\activate            # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

If `pip` complains about permissions, add `--user`. If `python` doesn't
exist on your system, use `python3` throughout.

### 4. Copy the starter files into `src/`

Your implementation goes in `src/`; `template/` holds the unmodified
starter stubs. Copy, don't move:

```bash
cp template/*.py src/
ls src/                          # snmp_protocol.py, snmp_agent.py,
                                 # snmp_manager.py, mib_database.py
```

### 5. Run your first test

The starter stubs all raise `NotImplementedError`, so every test fails
until you fill them in. Start with `encode_oid` — it is three lines of
Python and gets your toolchain proven end-to-end:

```bash
python -m pytest tests/ -v -k "test_oid"
```

The full walkthrough (worked example, common mistakes, reference
implementation) is in the Protocol Reference: see
[OID Encoding](docs/protocol.md#oid-encoding). Once both OID tests
pass, you have a working development loop and can start the milestones
below.

---

## Project at a Glance

You implement three files. Each corresponds to one deep-dive docs page.

```
┌──────────────────┐          ┌──────────────────┐
│ snmp_manager.py  │ ───TCP── │  snmp_agent.py   │
│   (client/CLI)   │          │  (server/device) │
└──────────────────┘          └────────┬─────────┘
          │                            │
          └─────── snmp_protocol.py ───┘
                   (shared wire format)
```

- **`snmp_protocol.py`** — OID encoding, value encoding, three message
  classes (`GetRequest`, `SetRequest`, `GetResponse`), and the
  `receive_complete_message` buffered-read helper. This is the shared
  vocabulary both sides speak.
- **`snmp_agent.py`** — the long-running server. Binds a TCP port,
  accepts connections, reads an SNMP message, looks up or mutates values
  in the MIB (`mib_database.py`, provided and immutable), and sends a
  `GetResponse`.
- **`snmp_manager.py`** — the CLI client. Parses `get` / `set` commands,
  opens one connection per request, sends a message, prints the response
  or a friendly error.

The authoritative wire-format specification — every byte, every field,
every PDU layout — lives in [docs/protocol.md](docs/protocol.md). Read
that page before you start implementing.

---

## Milestones

The project is organised into three cumulative bundles. Each bundle
unlocks a letter grade (see [Grading](GRADING.md) for the full rules).

### Week 1 — Bundle C (C grade): Core GET

Goal: a manager can query a single OID against a running agent.

- [ ] Implement `encode_oid` / `decode_oid`
  ([protocol.md#oid-encoding](docs/protocol.md#oid-encoding))
- [ ] Implement `encode_value` / `decode_value`
  ([protocol.md#value-encoding](docs/protocol.md#value-encoding))
- [ ] Implement `GetRequest.pack` / `.unpack`
  ([protocol.md#get-request](docs/protocol.md#get-request))
- [ ] Implement `GetResponse.pack` / `.unpack`
  ([protocol.md#get-response](docs/protocol.md#get-response))
- [ ] Implement `receive_complete_message`
  ([protocol.md#message-framing](docs/protocol.md#message-framing))
- [ ] Implement `SNMPAgent.start` and `_handle_client` for single-OID GETs
  ([agent.md#server-lifecycle](docs/agent.md#server-lifecycle),
  [agent.md#handling-a-client](docs/agent.md#handling-a-client))
- [ ] Implement `SNMPManager.get` for a single OID
  ([manager.md#sending-a-get-request](docs/manager.md#sending-a-get-request))

Verify:

```bash
python -m src.snmp_agent &       # terminal 1
python -m src.snmp_manager get localhost:1161 1.3.6.1.2.1.1.1.0
python -m pytest tests/ -v -m "bundle_C"
```

### Week 2 — Bundle B (B grade): Multi-OID and error handling

Goal: multiple OIDs in one request, correct error codes, robust buffering.

- [ ] Extend `GetRequest` / `GetResponse` to handle multi-OID payloads
- [ ] Implement atomic all-or-nothing GET semantics in the agent
  ([agent.md#processing-getrequest](docs/agent.md#processing-getrequest))
- [ ] Return `NO_SUCH_OID` when any requested OID is missing
  ([agent.md#error-codes](docs/agent.md#error-codes))
- [ ] Make sure `receive_complete_message` survives fragmented sends and
  back-to-back messages
  ([protocol.md#message-framing](docs/protocol.md#message-framing))

Verify:

```bash
python -m src.snmp_manager get localhost:1161 1.3.6.1.2.1.1.1.0 1.3.6.1.2.1.1.3.0
python -m src.snmp_manager get localhost:1161 1.3.6.1.2.1.1.99.0     # error
python -m pytest tests/ -v -m "bundle_B"
```

### Week 3 — Bundle A (A grade): SET and state

Goal: the manager can mutate writable MIB entries; the agent validates and
persists changes for the lifetime of the process.

- [ ] Implement `SetRequest.pack` / `.unpack`
  ([protocol.md#set-request](docs/protocol.md#set-request))
- [ ] Implement the agent's two-phase SET handler (validate all, then apply)
  ([agent.md#processing-setrequest](docs/agent.md#processing-setrequest))
- [ ] Emit correct `READ_ONLY` and `BAD_VALUE` error codes
- [ ] Implement `SNMPManager.set` including CLI type conversion
  ([manager.md#value-type-conversion](docs/manager.md#value-type-conversion))
- [ ] Ensure `sysUpTime` increases between successive reads
  ([agent.md#concurrency-and-state](docs/agent.md#concurrency-and-state))

Verify:

```bash
python -m src.snmp_manager set localhost:1161 1.3.6.1.2.1.1.5.0 string "router-test"
python -m src.snmp_manager set localhost:1161 1.3.6.1.2.1.1.3.0 integer 0   # read-only
python -m pytest tests/ -v -m "bundle_A"
python run_tests.py              # full grading report
```

---

## Testing and Grading

This project uses **specification grading**: all tests in a bundle must
pass to earn that bundle. No partial credit within a bundle.

| Grade | Bundles required | Numeric equivalent |
|-------|------------------|--------------------|
| **C** | Bundle C         | 70                 |
| **B** | Bundles C + B    | 85                 |
| **A** | Bundles C + B + A| 100                |

The grading script reports which bundle you have completed:

```bash
python run_tests.py              # summary grade
python run_tests.py -v           # show failing test names
```

Pytest markers let you target a bundle directly:

```bash
python -m pytest tests/ -v -m "bundle_C"
python -m pytest tests/ -v -m "bundle_B"
python -m pytest tests/ -v -m "bundle_A"
```

Full instructions — VS Code integration, filtering tests by keyword,
coverage reports — are in [TESTING.md](TESTING.md).

---

## Submission

Submit exactly these three files to the autograder:

- `src/snmp_protocol.py`
- `src/snmp_agent.py`
- `src/snmp_manager.py`

**Do not submit** `mib_database.py` (provided, immutable), the `tests/`
directory, `venv/`, or `__pycache__/` directories.

### Pre-submission checklist

- [ ] All three files are present in `src/`
- [ ] `python -m src.snmp_agent` starts without errors
- [ ] `python -m src.snmp_manager get localhost:1161 1.3.6.1.2.1.1.1.0`
      returns a value from a running agent
- [ ] `python run_tests.py` reports your intended grade
- [ ] No stray `print()` debugging left in submitted code
- [ ] No hard-coded paths; the code runs from a clean checkout

---

## Getting Help

- **Stuck on a specific function?** Each `NotImplementedError` in the
  starter code links to the exact docs section for that function.
- **Bytes going wrong?** Start with the [Debugging
  Guide](docs/debugging.md) — it covers byte order, message size
  calculation, string/bytes confusion, and framing bugs.
- **Agent or manager won't connect?** See the [Connection
  Refused](docs/debugging.md#connection-refused) and [Address Already in
  Use](docs/debugging.md#address-already-in-use) sections.
- **Concept unclear?** The [Background page](docs/background.md) explains
  what SNMP is and why the assignment diverges from the real protocol.
- **Office hours and the course forum** are the right place for
  assignment-specific clarifications. Bring a failing test name and
  the relevant hex output; that makes debugging tractable over a
  shared terminal.

---

## License

This assignment is provided under the Creative Commons BY-NC-SA 4.0
license. You may share and adapt this material for non-commercial
purposes with appropriate attribution.

[![License: CC BY-NC-SA 4.0](https://img.shields.io/badge/License-CC%20BY--NC--SA%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc-sa/4.0/)
