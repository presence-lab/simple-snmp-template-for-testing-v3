# SNMP Manager (Client)

Deep-dive reference for the client side of the simplified SNMP protocol — the
program a user runs to query or modify values on a running SNMP agent. Code
comments in `template/snmp_manager.py` link here when a function has
detail that would otherwise clutter the source.

For the wire format of the messages this client sends, see the
[Protocol Reference](protocol.html). Module-level constants
(`DEFAULT_TIMEOUT`, `TIMETICKS_PER_SECOND`) are documented in the
[Constants Reference](protocol.html#constants-reference).

---

## Command-Line Interface

The manager is a CLI tool. `main()` and `parse_host_port()` are provided —
your job is to implement the two commands they dispatch to.

### Synopsis

```
snmp_manager.py get <host:port> <oid> [<oid> ...]
snmp_manager.py set <host:port> <oid> <type> <value>
```

Where `<type>` is one of `integer`, `string`, `counter`, `timeticks`.

### Examples

```bash
# Single OID
python src/snmp_manager.py get localhost:1161 1.3.6.1.2.1.1.1.0

# Multiple OIDs in one request
python src/snmp_manager.py get localhost:1161 1.3.6.1.2.1.1.1.0 1.3.6.1.2.1.1.5.0

# Modify a writable OID
python src/snmp_manager.py set localhost:1161 1.3.6.1.2.1.1.5.0 string "new-router-name"
```

### Exit codes and output conventions

| Situation | Exit code | Output |
|-----------|-----------|--------|
| Usage error (bad argv) | `1` | Prints error + usage to stdout |
| Successful query | `0` | One `oid = value` line per binding |
| Successful set | `0` | `Set operation successful:` then the binding |
| Agent error (e.g. read-only) | `0` | `Error: <human-readable message>` |
| Network failure (timeout, refused) | `0` | `Error: <message>` |

The command handlers print errors rather than raising — the CLI is meant to be
friendly to students who have started the wrong port or forgotten to launch
the agent.

---

## Running Your First Request

Before studying the implementation, run the finished system end-to-end so you
know what success looks like. You need two terminals open to the same project
directory with the venv activated.

**Terminal A — start the agent** (leave this running):

```bash
python src/snmp_agent.py
```

You should see something like `SNMP Agent listening on port 1161...`. If you
see `[Errno 48] Address already in use`, another process is still holding
the port — see [Debugging: Address Already in Use](debugging.html#address-already-in-use).

**Terminal B — query the agent:**

```bash
# Read the system name (sysName.0)
python src/snmp_manager.py get localhost:1161 1.3.6.1.2.1.1.5.0
# => 1.3.6.1.2.1.1.5.0 = router-main
```

Try a few more reads:

```bash
# System description and uptime in one call
python src/snmp_manager.py get localhost:1161 1.3.6.1.2.1.1.1.0 1.3.6.1.2.1.1.3.0

# A non-existent OID — agent returns an error code, CLI prints it
python src/snmp_manager.py get localhost:1161 1.3.6.1.2.1.1.99.0
```

Write a value, then read it back to see state persist inside the agent:

```bash
python src/snmp_manager.py set localhost:1161 1.3.6.1.2.1.1.5.0 string "my-router"
python src/snmp_manager.py get localhost:1161 1.3.6.1.2.1.1.5.0
# => 1.3.6.1.2.1.1.5.0 = my-router
```

Writing a read-only OID should fail cleanly:

```bash
python src/snmp_manager.py set localhost:1161 1.3.6.1.2.1.1.3.0 integer 0
# => Error: Read-only OID
```

Stop the agent with `Ctrl+C` in Terminal A when you're done.

If any of the above hangs or returns gibberish, something upstream of the
manager is wrong — check [Debugging](debugging.html) before blaming the CLI.

---

## Connecting to the Agent

Both `get()` and `set()` need the same client-socket setup, so it lives in a
helper, `_connect_to_agent(host, port)`.

### Client socket lifecycle

```
create ──► settimeout ──► connect ──► (use) ──► close
```

Server sockets bind and listen; client sockets actively connect. For this
assignment, always use **IPv4 + TCP** (`AF_INET`, `SOCK_STREAM`).

### Reference implementation

```python
def _connect_to_agent(self, host: str, port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(DEFAULT_TIMEOUT)     # MUST be before connect()
    sock.connect((host, port))           # note the tuple: ((host, port))
    return sock
```

### Common mistakes

- **Forgetting `settimeout` before `connect`.** If the agent is down and you
  never set a timeout, `connect()` blocks until the OS gives up — often
  minutes. Always configure the timeout first.
- **`sock.connect(host, port)`** (two positional args) — this is a `TypeError`.
  `connect` takes a single address tuple: `sock.connect((host, port))`.
- **Reusing a closed socket.** A socket is one-shot: once closed, you must
  create a new one for the next request. This is why `get()` and `set()` each
  create their own.

### Expected failure modes

| Exception | Meaning | Typical cause |
|-----------|---------|---------------|
| `ConnectionRefusedError` | Port is closed | Agent isn't running |
| `socket.timeout` | No response in `DEFAULT_TIMEOUT` | Agent is hung, firewall, wrong host |
| `socket.gaierror` | DNS lookup failed | Typo in hostname |

The callers of `_connect_to_agent` (`get` and `set`) catch these and print a
friendly message — the helper itself should just let the exception propagate.

---

## Sending a Get Request

The `get` method executes one complete request/response cycle:

1. Connect to the agent (`_connect_to_agent`).
2. Generate a fresh request ID via `self._get_next_request_id()`.
3. Build a `GetRequest(request_id, oids)` and call `.pack()` to serialise.
4. `sock.send(data)`.
5. `receive_complete_message(sock)` to read the full response (handles the
   4-byte size prefix and partial recvs — see the
   [Protocol Reference](protocol.html)).
6. `unpack_message(response_data)` to get a `GetResponse` object.
7. Validate: `isinstance(response, GetResponse)` and
   `response.request_id == request_id`.
8. Print the bindings, or print the error if `response.error_code != SUCCESS`.

### Why request-ID correlation matters

Request IDs are tracking numbers. You send request `#1234`; the agent echoes
`#1234` in its response. If the IDs don't match, something is wrong —
possibly a leftover response from a previous request, a buggy agent, or a
network mix-up — and you should report an error rather than trust the
response.

### Reference implementation

```python
def get(self, host: str, port: int, oids: List[str]) -> None:
    sock = None
    try:
        sock = self._connect_to_agent(host, port)

        request_id = self._get_next_request_id()
        request = GetRequest(request_id, oids)
        sock.send(request.pack())

        response_data = receive_complete_message(sock)
        response = unpack_message(response_data)

        if not isinstance(response, GetResponse):
            print(f"Error: Expected GetResponse, got {type(response).__name__}")
            return
        if response.request_id != request_id:
            print(f"Error: Request ID mismatch - sent {request_id}, "
                  f"received {response.request_id}")
            return

        if response.error_code == ErrorCode.SUCCESS:
            for oid, value_type, value in response.bindings:
                print(f"{oid} = {format_value(value_type, value)}")
        else:
            print(f"Error: {format_error(response.error_code)}")

    except socket.timeout:
        print(f"Error: Request timed out after {DEFAULT_TIMEOUT} seconds")
    except ConnectionRefusedError:
        print(f"Error: Cannot connect to {host}:{port} - is the agent running?")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if sock:
            sock.close()
```

### Example runs

Single OID against a running agent:

```
$ python src/snmp_manager.py get localhost:1161 1.3.6.1.2.1.1.1.0
1.3.6.1.2.1.1.1.0 = Router Model X2000
```

Multiple OIDs:

```
$ python src/snmp_manager.py get localhost:1161 1.3.6.1.2.1.1.1.0 1.3.6.1.2.1.1.5.0
1.3.6.1.2.1.1.1.0 = Router Model X2000
1.3.6.1.2.1.1.5.0 = router-42
```

An OID the agent doesn't know about:

```
$ python src/snmp_manager.py get localhost:1161 1.3.6.1.2.1.1.99.0
Error: No such OID exists
```

### Common mistakes

- **Not validating `isinstance(response, GetResponse)`.** The agent should
  only ever send a `GetResponse`, but a faulty agent (or the private test
  suite) may not. Fail loudly instead of crashing on `.bindings`.
- **Not matching `request_id`.** See above — this is one of the private tests.
- **Parsing bindings on the error path.** When `error_code != SUCCESS`, the
  bindings list is typically empty. Print the error and return.

### Targeted tests

```bash
python -m pytest tests/test_public_manager_client.py::TestBundleCManagerCore -v
python -m pytest tests/test_public_agent_manager_integration.py::TestBundleCIntegrationCore -v
```

---

## Sending a Set Request

`set` is the same request/response shape as `get`, with one extra concern:
the CLI value is a *string*, but the SetRequest binding needs a properly
typed Python value.

Steps:

1. Validate the `value_type` string and look up the `ValueType` enum (the
   template provides the `type_map` dict).
2. Convert `value` to the right Python type (see
   [Value Type Conversion](#value-type-conversion) below).
3. Connect to the agent.
4. Build `SetRequest(request_id, [(oid, vtype, converted_value)])` and pack it.
5. Send, receive, unpack (identical to `get`).
6. Validate response type and request ID.
7. Print `Set operation successful:` and the binding on success, or
   `Error: <message>` on failure.

### Reference implementation (set body only)

```python
sock = None
try:
    sock = self._connect_to_agent(host, port)

    request_id = self._get_next_request_id()
    bindings = [(oid, vtype, converted_value)]
    request = SetRequest(request_id, bindings)
    sock.send(request.pack())

    response_data = receive_complete_message(sock)
    response = unpack_message(response_data)

    if not isinstance(response, GetResponse):
        print(f"Error: Expected GetResponse, got {type(response).__name__}")
        return
    if response.request_id != request_id:
        print(f"Error: Request ID mismatch - sent {request_id}, "
              f"received {response.request_id}")
        return

    if response.error_code == ErrorCode.SUCCESS:
        print("Set operation successful:")
        for oid, value_type, value in response.bindings:
            print(f"{oid} = {format_value(value_type, value)}")
    else:
        print(f"Error: {format_error(response.error_code)}")

except socket.timeout:
    print(f"Error: Request timed out after {DEFAULT_TIMEOUT} seconds")
except ConnectionRefusedError:
    print(f"Error: Cannot connect to {host}:{port} - is the agent running?")
except Exception as e:
    print(f"Error: {e}")
finally:
    if sock:
        sock.close()
```

Note the response type is still `GetResponse` — our simplified protocol reuses
`GetResponse` as the reply to both `GetRequest` and `SetRequest` (see the
[Protocol Reference](protocol.html)).

### Example runs

Successful set of a writable OID:

```
$ python src/snmp_manager.py set localhost:1161 1.3.6.1.2.1.1.5.0 string "new-router-name"
Set operation successful:
1.3.6.1.2.1.1.5.0 = new-router-name
```

Attempting to set a read-only OID:

```
$ python src/snmp_manager.py set localhost:1161 1.3.6.1.2.1.1.3.0 integer 0
Error: OID is read-only
```

Mismatched value type (agent rejects it):

```
$ python src/snmp_manager.py set localhost:1161 1.3.6.1.2.1.1.5.0 integer 42
Error: Bad value for OID type
```

### Targeted tests

```bash
python -m pytest tests/test_public_manager_client.py::TestBundleBManagerIntermediate -v
python -m pytest tests/test_public_agent_manager_integration.py::TestBundleBIntegrationIntermediate -v
```

---

## Value Type Conversion

`sys.argv` is always strings. Before building a `SetRequest`, convert the
incoming string to the Python type the protocol expects for each
`ValueType`.

| CLI `<type>` | `ValueType` enum | Python type | Validation |
|--------------|------------------|-------------|------------|
| `integer`    | `INTEGER`        | `int`       | signed; any 32-bit int |
| `string`     | `STRING`         | `str`       | pass through unchanged |
| `counter`    | `COUNTER`        | `int`       | must be `>= 0` |
| `timeticks`  | `TIMETICKS`      | `int`       | must be `>= 0` |

### Reference implementation

```python
try:
    if vtype == ValueType.INTEGER:
        converted_value = int(value)
    elif vtype == ValueType.STRING:
        converted_value = value
    elif vtype == ValueType.COUNTER:
        converted_value = int(value)
        if converted_value < 0:
            print("Error: Counter values must be >= 0")
            return
    elif vtype == ValueType.TIMETICKS:
        converted_value = int(value)
        if converted_value < 0:
            print("Error: Timeticks values must be >= 0")
            return
except ValueError:
    print(f"Error: Cannot convert '{value}' to {value_type.lower()}")
    return
```

### Worked examples

| CLI args | `vtype` | Python value |
|----------|---------|--------------|
| `integer 42` | `INTEGER` | `42` |
| `integer -7` | `INTEGER` | `-7` |
| `string hello` | `STRING` | `"hello"` |
| `counter 1000` | `COUNTER` | `1000` |
| `counter -1` | `COUNTER` | *error printed; `return` before sending* |
| `timeticks abc` | `TIMETICKS` | *`ValueError` → error printed; return* |

### Common mistakes

- **Not wrapping `int()` in `try/except`.** `int("abc")` raises `ValueError`
  and, without a handler, the CLI crashes with a traceback.
- **Skipping the `>= 0` check on counter/timeticks.** These types are
  semantically unsigned in SNMP. Students sometimes send `-1` and then
  spend time debugging the agent's response.
- **Sending before conversion fails.** Always `return` after printing the
  conversion error — never continue to open a socket.

---

## Displaying Responses

The manager has three provided helpers. You shouldn't need to modify them,
but you do need to call them from the right places.

| Helper | When to call |
|--------|-------------|
| `format_value(value_type, value)` | Per-binding value in a successful response |
| `format_timeticks(ticks)` | Called internally by `format_value` for TIMETICKS |
| `format_error(error_code)` | When `response.error_code != SUCCESS` |

### Success vs error output

```
# Success (get):
<oid> = <formatted value>
<oid> = <formatted value>
...

# Success (set):
Set operation successful:
<oid> = <formatted value>

# Error:
Error: <human-readable message>
```

### Iterating bindings

`response.bindings` is a list of `(oid, value_type, value)` tuples. Unpack
inside the loop:

```python
for oid, value_type, value in response.bindings:
    print(f"{oid} = {format_value(value_type, value)}")
```

### Request / response ID correlation

On every response, before printing anything, check:

```python
if response.request_id != request_id:
    print(f"Error: Request ID mismatch - sent {request_id}, "
          f"received {response.request_id}")
    return
```

This check catches agent bugs, stale data on the socket, and the occasional
test harness that deliberately corrupts the response ID.

### Common mistakes

- **Stringifying the whole tuple** — `print(binding)` prints something like
  `('1.3.6.1.2.1.1.1.0', <ValueType.STRING: 4>, 'Router Model X2000')`. That
  fails the grading regex. Always format explicitly.
- **Using `str(value)` directly for timeticks / counters** — skips the
  human-readable formatting. Go through `format_value`.
- **Printing the error code as an integer** — `format_error` exists for a
  reason.

### Verifying end-to-end

With the agent running (`python src/snmp_agent.py`):

```bash
python src/snmp_manager.py get localhost:1161 1.3.6.1.2.1.1.1.0
python src/snmp_manager.py get localhost:1161 1.3.6.1.2.1.1.1.0 1.3.6.1.2.1.1.5.0
python src/snmp_manager.py set localhost:1161 1.3.6.1.2.1.1.5.0 string "test-name"
python src/snmp_manager.py get localhost:1161 1.3.6.1.2.1.1.5.0
```

Each command should print either a clean set of bindings or a clear
`Error:` line — never a Python traceback.
