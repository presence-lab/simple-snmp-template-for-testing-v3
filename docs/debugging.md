# Debugging Guide

Practical patterns for diagnosing failures in your SNMP implementation.
Binary protocols do not fail gracefully — a single wrong byte produces
nonsense for every subsequent field. This page collects the bugs that
come up most often and the tools that make them easier to spot.

For the authoritative wire format, see the [Protocol Reference](protocol.html).

---

## Byte Order

Network protocols use **big-endian** ("network byte order"). Every `struct`
call in this assignment uses the `!` prefix to enforce it:

```python
struct.pack('!I', 22)   # b'\x00\x00\x00\x16'  — big-endian
struct.pack('<I', 22)   # b'\x16\x00\x00\x00'  — little-endian (WRONG)
```

### Symptom

Numbers arrive wildly different from what you sent. Classic case: you send
`22` and decode `369098752`, which is `0x16000000` interpreted as big-endian.
That's your own bytes, read back through the wrong lens.

### Quick self-check

```python
import struct
data = b'\x00\x00\x00\x16'
print(struct.unpack('!I', data)[0])   # 22   — correct
print(struct.unpack('<I', data)[0])   # 369098752  — clearly wrong
```

If both sides of a round-trip use `!I`, you will never see this bug. If
you ever see a huge suspicious number, the first question is always
"did someone drop the `!`?"

---

## Message Size Calculation

`total_size` **includes itself**. A 20-byte message has `20` in its size
field, not `16`. Forgetting the size field's own 4 bytes is the second most
common bug after byte order.

```python
# WRONG — header excludes the size field itself
total_size = 4 + 1 + len(payload)           # for GetRequest
total_size = 4 + 1 + 1 + len(payload)       # for GetResponse

# CORRECT — include all four size-field bytes
total_size = 4 + 4 + 1 + len(payload)       # GetRequest / SetRequest
total_size = 4 + 4 + 1 + 1 + len(payload)   # GetResponse
```

### Symptom

Receiver reports "size mismatch" or quietly truncates the last byte of
every message. Large messages work sporadically because TCP sometimes
coalesces the missing byte from the next packet.

### Self-check inside `pack()`

```python
assert len(message) == total_size, \
    f"size mismatch: declared {total_size}, actual {len(message)}"
```

Leave this assertion in during development; remove or comment out before
submission.

---

## String vs Bytes

`str` and `bytes` are not interchangeable in Python 3. `socket.send()` and
`struct.pack` both want bytes.

```python
# WRONG — mixing types
oid = "1.3.6.1.2.1.1.5.0"
sock.send(oid)                         # TypeError

# CORRECT — convert first
sock.send(encode_oid(oid))             # encode_oid returns bytes

# For user-supplied string values in a SetRequest:
payload += user_value.encode('utf-8')  # str → bytes
```

### Symptom

`TypeError: a bytes-like object is required, not 'str'`, typically raised
from `struct.pack` or `sock.send`. The fix is always to encode the string
before passing it on.

### The subtler case

`encode_oid("1.3.6.1.2.1.1.5.0")` is correct. `"1.3.6.1.2.1.1.5.0".encode('utf-8')`
is **wrong**: it produces the ASCII bytes of the dotted string (`b'1.3.6.1...'`),
not the encoded OID (`b'\x01\x03\x06...'`). UTF-8 encoding is the right tool
for user-supplied string values, never for OIDs.

---

## Incomplete Message Reception

TCP is a byte stream. A single `sock.recv(4096)` may return the first
fragment of a message, a complete message, or a complete message plus the
first bytes of the next one. You must loop until you have exactly the
number of bytes the size field promised. See the [Protocol Reference,
"Message Framing"](protocol.html#message-framing) for the full algorithm.

```python
# WRONG — assumes one recv is one message
data = sock.recv(4096)

# CORRECT — loop until complete
def recv_exactly(sock, n):
    received = b''
    while len(received) < n:
        chunk = sock.recv(n - len(received))
        if not chunk:                     # empty means peer closed
            raise ConnectionError("socket closed mid-message")
        received += chunk
    return received
```

### Symptom

Tests pass on small messages and fail on large ones, or the parser dies
partway through a binding list with "unpack requires a buffer of N bytes".
Fragmented sends are happening and you are reading past the end of the
buffer into bytes that haven't arrived yet.

### The two-phase read

1. Loop until you have 4 bytes, then decode `total_size`.
2. Loop until your buffer length equals `total_size`, capping each
   `recv()` at 4096 bytes.

### Empty `recv()`

`sock.recv()` returning `b''` always means the peer closed the connection.
Without a check, your loop spins forever on a dead socket. Raise
`ConnectionError` instead.

---

## Address Already in Use

On Linux: `OSError: [Errno 98] Address already in use`. On macOS and
Windows: similar wording. The cause is that a socket you closed is still
in TCP `TIME_WAIT` holding the port.

```python
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # BEFORE bind
server_socket.bind(('', self.port))
```

`SO_REUSEADDR` must be set **before** `bind()`. Setting it afterwards is
silent no-op on some platforms. See the [Agent reference](agent.html#server-lifecycle)
for the full lifecycle.

---

## Connection Refused

`ConnectionRefusedError: [Errno 111] Connection refused` means the TCP
SYN packet reached the destination host but nothing is listening on that
port. Three things to check, in order:

1. **Is the agent running?** Start it explicitly in a second terminal:
   `python src/snmp_agent.py`.
2. **Right port?** Default is 1161. Check your manager's CLI args.
3. **Right host?** `localhost` resolves to `127.0.0.1`; if the agent binds
   to a specific external IP it will refuse loopback connections. The
   reference agent binds to `''` (all interfaces) to avoid this.

If the agent logs "listening on port 1161" and the manager still gets
refused, confirm no firewall is blocking loopback connections.

---

## Debug Helper Functions

Two small helpers worth keeping in a scratch module while you are developing.

### Hex viewer

```python
import struct

def debug_bytes(label, data):
    """Print bytes in every format useful for debugging."""
    print(f"\n{label}:")
    print(f"  Length: {len(data)} bytes")
    print(f"  Raw:    {data!r}")
    print(f"  Hex:    {data.hex()}")
    print(f"  Spaced: {' '.join(f'{b:02x}' for b in data)}")

    if len(data) >= 9:
        size   = struct.unpack('!I', data[0:4])[0]
        req_id = struct.unpack('!I', data[4:8])[0]
        pdu    = data[8]
        print(f"  Header: size={size}, req_id={req_id}, pdu=0x{pdu:02x}")
```

### Message validator

```python
def validate_message(data):
    """Sanity-check a packed message before sending."""
    if len(data) < 9:
        print(f"ERROR: too short ({len(data)} bytes, need >=9)")
        return False

    declared = struct.unpack('!I', data[0:4])[0]
    if declared != len(data):
        print(f"ERROR: size field says {declared}, actual length {len(data)}")
        return False

    pdu = data[8]
    if pdu not in (0xA0, 0xA1, 0xA3):
        print(f"ERROR: invalid PDU type 0x{pdu:02x}")
        return False

    print("Message structure looks valid.")
    return True
```

Call `validate_message(request.pack())` as the last step of development.
If `pack` built the message right, this passes; if `unpack` fails on the
same bytes, the bug is in `unpack`, not `pack`.

---

## A Throwaway Test Harness

When a specific test fails, the fastest diagnostic is often a five-line
script that drives your code directly, prints the bytes, and exits. Drop
this into `scratch.py` at the project root (gitignored) and edit freely:

```python
# scratch.py — not committed, not graded, purely for poking
import struct
from src.snmp_protocol import GetRequest, GetResponse, unpack_message, encode_oid

# 1. Build and inspect a request
req = GetRequest(request_id=1234, oids=["1.3.6.1.2.1.1.5.0"])
data = req.pack()
print("Packed:", data.hex())
print("Length:", len(data))

# 2. Round-trip through unpack
decoded = unpack_message(data)
print("Round-tripped OIDs:", decoded.oids)

# 3. Hand-build a message to verify unpack independently
manual = (
    struct.pack('!I', 20) +                          # total_size
    struct.pack('!I', 1234) +                        # request_id
    struct.pack('!B', 0xA0) +                        # pdu_type
    struct.pack('!B', 1) +                           # oid_count
    struct.pack('!B', 9) +                           # oid_length
    encode_oid("1.3.6.1.2.1.1.5.0")
)
assert manual == data, "packed output diverges from the spec"
```

Principles for throwaway scripts:

- Print bytes as `.hex()` — `repr` truncates on non-printable characters.
- Build a known-good message by hand with `struct.pack` as a reference.
  If your `pack()` output diverges, the spec lies on the hand-built side.
- Exercise `pack` and `unpack` independently before testing them together;
  if the round-trip succeeds but network tests fail, the bug is in the
  socket handling, not the protocol layer.
- Delete the file before you submit, or add it to `.gitignore`.

---

## When All Else Fails

- **Compare against the protocol reference's worked examples.** Every PDU
  section in [protocol.md](protocol.html) contains a byte-level breakdown
  of a complete message. Print your output in the same format and diff them.
- **Check the MIB for a successful response.** If your GET returns bindings
  but the value looks wrong, confirm the MIB actually contains what you
  expect with `python -c "from src.mib_database import MIB_DATABASE; print(MIB_DATABASE['1.3.6.1.2.1.1.5.0'])"`.
- **Add temporary `print()` at every `pack`/`unpack` boundary.** Two prints —
  one after `pack()`, one before `unpack()` — bracket the bug. If both
  show the same bytes and unpack still fails, the bug is in `unpack`. If
  the bytes differ, the transport is at fault.
- **Run a single failing test with `pytest -x -vv`.** Full tracebacks and
  assertion diffs make binary protocol failures legible.
