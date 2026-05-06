# SNMP Agent (Server)

Reference for the server side of the assignment — the long-running process
that listens on a TCP port, receives SNMP messages, reads and mutates the
MIB, and sends `GetResponse` messages back. Wire format details live in the
[Protocol Reference](protocol.html); this page covers the agent's
responsibilities and control flow.

The agent is implemented as a single class, `SNMPAgent`, in `src/snmp_agent.py`.
Its public entry point is `start()`; everything else is an internal helper.

Module-level constants (`DEFAULT_PORT`, `LISTEN_BACKLOG`, `TIMEOUT_SECONDS`,
`TIMETICKS_PER_SECOND`) are all documented in the
[Constants Reference](protocol.html#constants-reference).

---

## Server Lifecycle

`SNMPAgent.start()` walks a fixed sequence: **create → configure → bind →
listen → accept loop → clean up**. This is the same sequence every TCP server
follows; only the per-request handler changes between applications.

### Required steps

1. Create a TCP socket: `socket.socket(socket.AF_INET, socket.SOCK_STREAM)`.
2. Set `SO_REUSEADDR` **before** `bind()` so a restarted agent can reclaim
   the port instead of waiting on TCP `TIME_WAIT`.
3. Bind to `('', self.port)` so the agent accepts on every interface.
4. Call `listen(LISTEN_BACKLOG)` to move the socket into the passive state.
5. Print a startup message so graders can see the agent came up.
6. Loop on `server_socket.accept()` while `self.running` is true; hand each
   accepted client socket to `_handle_client`.
7. On `KeyboardInterrupt`, set `self.running = False` and break out.
8. In a `finally` block, close the server socket — always, even on error.

### Reference implementation

```python
def start(self):
    try:
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind(('', self.port))
        self.server_socket.listen(LISTEN_BACKLOG)
        print(f"SNMP Agent listening on port {self.port}...")

        while self.running:
            try:
                client_socket, client_address = self.server_socket.accept()
                print(f"Connection from {client_address[0]}:{client_address[1]}")
                self._handle_client(client_socket, client_address)
            except KeyboardInterrupt:
                print("\nShutting down...")
                self.running = False
                break
    finally:
        if self.server_socket:
            self.server_socket.close()
```

### Common pitfalls

- **Forgetting `SO_REUSEADDR`.** Symptom: `OSError: [Errno 98] Address
  already in use` on the second run. Fix: set the option before `bind()`.
- **Binding to `'localhost'`.** This rejects connections from any other
  interface. Tests may connect via `127.0.0.1` or the loopback IP — `''`
  (meaning `0.0.0.0`) accepts both.
- **No `try/finally`.** If `accept()` or the handler raises, you leak the
  listening socket and the next run fails to bind.

---

## Handling a Client

`_handle_client(client_socket, client_address)` processes one TCP connection
from start to finish. Because our protocol allows persistent connections
(the manager may send several requests on one socket), this method runs a
loop: receive a complete message, process it, send the response, repeat
until the peer closes or we time out.

### Required behavior

- Call `client_socket.settimeout(TIMEOUT_SECONDS)` before the loop so a
  silent client cannot hold the handler open forever.
- Use `receive_complete_message(client_socket)` to reassemble a message
  from the TCP byte stream — see the [Protocol Reference, "Message
  Framing"](protocol.html#message-framing) for why partial reads matter.
- Pass the message bytes to `_process_message`, then `sendall` the result.
- Exit the loop cleanly on `ConnectionError` (client hung up) or
  `socket.timeout` (client went silent).
- Catch other exceptions, log them, and break — one bad client must never
  crash the agent.
- Always close `client_socket` in a `finally` block.

### Reference implementation

```python
def _handle_client(self, client_socket, client_address):
    try:
        client_socket.settimeout(TIMEOUT_SECONDS)
        while True:
            try:
                message_bytes = receive_complete_message(client_socket)
                response_bytes = self._process_message(message_bytes)
                client_socket.sendall(response_bytes)
            except ConnectionError:
                print(f"Client {client_address[0]} disconnected normally")
                break
            except socket.timeout:
                print(f"Client {client_address[0]} timed out after {TIMEOUT_SECONDS}s")
                break
            except Exception as e:
                print(f"ERROR with client {client_address[0]}: {type(e).__name__}: {e}")
                break
    finally:
        client_socket.close()
```

### Common pitfalls

- **Using `recv()` instead of `receive_complete_message()`.** TCP does not
  preserve message boundaries; one `recv()` may return part of a message,
  two messages, or a message plus part of the next.
- **No timeout.** A client that opens a socket and never sends a byte will
  pin the handler forever, which blocks every later connection because this
  assignment is single-threaded.
- **Catching `Exception` in the outer `try`.** You must still close the
  socket — keep the `finally` on the outer block, not inside the loop.

---

## Processing GetRequest

`_process_message` is a one-function dispatcher: unpack the incoming bytes,
route by message class, pack the response.

```python
def _process_message(self, message_bytes):
    message = unpack_message(message_bytes)
    if isinstance(message, GetRequest):
        response = self._handle_get_request(message)
    elif isinstance(message, SetRequest):
        response = self._handle_set_request(message)
    else:
        raise ValueError(f"Unknown message type: {type(message).__name__}")
    return response.pack()
```

### GetRequest semantics

A `GetRequest` carries a `request_id` and a list of OID strings. The agent
must reply with a `GetResponse` that:

1. **Echoes `request.request_id`.** The manager uses it to correlate
   request/response pairs.
2. **Succeeds atomically or fails atomically.** If any requested OID is not
   in the MIB, return a single `GetResponse` with
   `ErrorCode.NO_SUCH_OID` and an empty binding list. Never return partial
   results.
3. **Updates dynamic values first.** `sysUpTime` is computed on read;
   see [Concurrency and State](#concurrency-and-state).
4. **Emits bindings in request order** as `(oid, ValueType, value)` tuples.

### Reference implementation

```python
def _handle_get_request(self, request):
    self._update_dynamic_values()

    for oid in request.oids:
        if oid not in self.mib:
            return GetResponse(request.request_id, ErrorCode.NO_SUCH_OID, [])

    bindings = []
    for oid in request.oids:
        mib_type, mib_value = self.mib[oid]
        value_type = self._get_value_type(mib_type)
        bindings.append((oid, value_type, mib_value))

    return GetResponse(request.request_id, ErrorCode.SUCCESS, bindings)
```

### Common pitfalls

- **Forgetting to echo the request ID.** Graders check this on every
  response — a mismatched ID is treated as a protocol violation.
- **Returning partial data on a missing OID.** The all-or-nothing rule is
  what makes the client's error handling simple; partial responses force
  callers to guess which index failed.
- **Calling `_update_dynamic_values` too late.** If you run it after the
  existence check, the `sysUpTime` lookup reads stale data.

---

## Processing SetRequest

`SetRequest` is the only way a manager can mutate the MIB. The handler
runs a strict **two-phase** pattern: validate every binding before
applying any change.

### Required validations, in order

For every `(oid, value_type, value)` in `request.bindings`:

1. **Existence** — `oid in self.mib`. Failure: `ErrorCode.NO_SUCH_OID`.
2. **Writability** — `MIB_PERMISSIONS.get(oid, 'read-only') == 'read-write'`.
   Failure: `ErrorCode.READ_ONLY`. Default to read-only for any OID not
   listed explicitly (fail closed).
3. **Type match** — the supplied `value_type` must equal the `ValueType`
   that corresponds to the stored MIB type string. Failure:
   `ErrorCode.BAD_VALUE`.

On any failure, return immediately with an empty binding list. Do **not**
apply any of the changes — even the ones that passed so far.

### Apply phase

Once every binding passes validation, update `self.mib[oid] = (mib_type,
new_value)` for each one, preserving the original MIB type string. Echo
the bindings back in the success response so the client can confirm the
values that were stored.

### Reference implementation

```python
def _handle_set_request(self, request):
    for oid, value_type, value in request.bindings:
        if oid not in self.mib:
            return GetResponse(request.request_id, ErrorCode.NO_SUCH_OID, [])

        permission = MIB_PERMISSIONS.get(oid, 'read-only')
        if permission != 'read-write':
            return GetResponse(request.request_id, ErrorCode.READ_ONLY, [])

        mib_type, _ = self.mib[oid]
        expected_type = self._get_value_type(mib_type)
        if value_type != expected_type:
            return GetResponse(request.request_id, ErrorCode.BAD_VALUE, [])

    response_bindings = []
    for oid, value_type, value in request.bindings:
        mib_type, _ = self.mib[oid]
        self.mib[oid] = (mib_type, value)
        response_bindings.append((oid, value_type, value))

    return GetResponse(request.request_id, ErrorCode.SUCCESS, response_bindings)
```

### Common pitfalls

- **Mutating during validation.** If a later binding is invalid and you've
  already written an earlier one, the MIB is left in a half-applied state.
- **Overwriting the MIB type.** The MIB stores `(type_string, value)`.
  Writing just the value — e.g. `self.mib[oid] = value` — breaks every
  subsequent GET because the tuple unpack fails.
- **Defaulting unknown OIDs to writable.** Use `.get(oid, 'read-only')`,
  not `MIB_PERMISSIONS[oid]`; the latter raises `KeyError` on OIDs that
  happen to be missing from the permissions table.

---

## Error Codes

The `ErrorCode` enum is defined in `snmp_protocol.py`. The agent only ever
sends one of four values:

| Code | Name | When to send it |
|------|------|-----------------|
| 0 | `SUCCESS` | Every OID in the request was handled without issue. |
| 1 | `NO_SUCH_OID` | A requested OID is not present in `self.mib`. |
| 2 | `BAD_VALUE` | A SET binding's `value_type` does not match the MIB's stored type. |
| 3 | `READ_ONLY` | A SET targets an OID whose permission is `'read-only'`. |

Two rules apply to every error response:

- `request_id` still echoes the incoming request.
- `bindings` is an empty list (`[]`). The client assumes no data on error.

If more than one validation could fail (e.g. an OID is both missing and
would be read-only), return the code that matches the **first** check that
fails — this keeps the validation order in `_handle_set_request`
deterministic and makes failing tests easier to diagnose.

---

## Concurrency and State

This agent is **single-threaded**. `_handle_client` runs to completion for
one connection before `accept()` returns another. That simplification
means:

- Writes to `self.mib` never race.
- Multiple requests on one persistent connection see each other's SET
  results immediately.
- A slow or stuck client blocks every other client — which is why the
  handler-level timeout is mandatory, not optional.

### sysUpTime

`1.3.6.1.2.1.1.3.0` is computed on every GET, not stored. `_update_dynamic_values`
calculates `int((time.time() - self.start_time) * TIMETICKS_PER_SECOND)` and
writes it back into the MIB tuple before the GET handler reads values.
That means:

- Two successive GETs of `sysUpTime` must return monotonically increasing
  values (within timer resolution).
- `self.start_time` is captured once in `__init__` and never updated.
- The stored MIB type stays `'TIMETICKS'`; only the value changes.

### Persisted writes

SET-applied values live in `self.mib` for the lifetime of the process.
The starting state is a copy of `MIB_DATABASE` (made in `__init__` via
`dict(MIB_DATABASE)`) so test cases can mutate the agent's MIB without
leaking into the next test. Restarting the agent reverts to the module-level
defaults — there is no on-disk persistence in this assignment.

### Reference implementation for _update_dynamic_values

```python
def _update_dynamic_values(self):
    uptime_seconds = time.time() - self.start_time
    uptime_ticks = int(uptime_seconds * TIMETICKS_PER_SECOND)
    self.mib['1.3.6.1.2.1.1.3.0'] = ('TIMETICKS', uptime_ticks)
```

### Verifying your agent

With both `snmp_protocol.py` and `snmp_agent.py` implemented:

```bash
# Terminal 1
python -m src.snmp_agent

# Terminal 2
python -m src.snmp_manager get localhost:1161 1.3.6.1.2.1.1.5.0
python -m src.snmp_manager get localhost:1161 1.3.6.1.2.1.1.3.0
python -m src.snmp_manager set localhost:1161 1.3.6.1.2.1.1.5.0 string "router-test"
python -m src.snmp_manager get localhost:1161 1.3.6.1.2.1.1.5.0
```

Run the targeted test file:

```bash
python -m pytest tests/test_public_agent_manager_integration.py -v
```
