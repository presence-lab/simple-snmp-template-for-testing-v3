# Protocol Reference

Deep-dive reference for the simplified SNMP wire format used in this assignment.
Code comments link here; the quick overview lives in the README.

---

## OID Encoding

An **OID** (Object Identifier) is a dotted-decimal path that names a piece of
data in the device's MIB — much like a filesystem path names a file.

```
1.3.6.1.2.1.1.5.0   →   b'\x01\x03\x06\x01\x02\x01\x01\x05\x00'
```

### Encoding rules

In our simplified protocol, each component in the OID is encoded as **one byte**:

- Each component must be in range `0`–`255`.
- The byte length of the encoded OID equals the number of components.
- Empty OIDs are invalid and should raise `ValueError`.
- Components outside `0`–`255` should raise `ValueError`.

Real SNMP uses a variable-length encoding (BER) where components can be larger
than a byte. We're skipping that complexity to focus on message framing.

### Worked example

| Step | Value |
|------|-------|
| Input string | `"1.3.6.1.2.1.1.5.0"` |
| Split by `.` | `["1", "3", "6", "1", "2", "1", "1", "5", "0"]` |
| Parse as int | `[1, 3, 6, 1, 2, 1, 1, 5, 0]` |
| Pack as bytes | `b'\x01\x03\x06\x01\x02\x01\x01\x05\x00'` |
| `.hex()` view | `"010306010201010500"` |

A reference implementation is three lines:

```python
def encode_oid(oid_string: str) -> bytes:
    return bytes(int(part) for part in oid_string.split("."))
```

### Common mistakes

- **`bytes(["1", "3", "6"])`** — fails; `bytes()` needs integers, not strings.
- **`oid_string.encode()`** — produces the ASCII bytes of the dotted string
  (`b'1.3.6.1...'`), not the encoded OID. UTF-8 encoding is never the right
  tool for OIDs.
- **Components > 255** — Python raises `ValueError: bytes must be in range(0, 256)`.
  Check your input; standard MIB-2 OIDs stay well under 255.

### Decoding

Decoding is the inverse. Python bytes iterate as integers, so the whole
function fits in one expression:

```python
def decode_oid(oid_bytes: bytes) -> str:
    return ".".join(str(b) for b in oid_bytes)
```

### Verifying your implementation

```python
>>> encode_oid("1.3.6.1.2.1.1.5.0").hex()
'010306010201010500'

>>> decode_oid(bytes.fromhex("010306010201010500"))
'1.3.6.1.2.1.1.5.0'

>>> decode_oid(encode_oid("1.3.6.1")) == "1.3.6.1"
True
```

Targeted test run:

```bash
python -m pytest tests/test_public_snmp_protocol.py -v -k "test_oid"
```

---

## Value Encoding

OIDs name the data; value encoding describes the data itself. Every SNMP
value carries a one-byte **type tag** on the wire, but `encode_value` and
`decode_value` only handle the payload bytes — the type tag is written and
read by the surrounding PDU format.

### The four value types

| Type | Code | Payload layout | Python type |
|------|------|----------------|-------------|
| `INTEGER` | `0x02` | 4 bytes, signed, big-endian | `int` (may be negative) |
| `STRING` | `0x04` | Variable UTF-8 bytes | `str` |
| `COUNTER` | `0x41` | 4 bytes, **unsigned**, big-endian | `int` (0 to 4,294,967,295) |
| `TIMETICKS` | `0x43` | 4 bytes, **unsigned**, big-endian | `int` (hundredths of a second) |

Network byte order is big-endian. `struct.pack('!i', x)` and `struct.pack('!I', x)`
both produce 4 bytes with the most significant byte first — the difference is
that lowercase `i` treats the value as signed and capital `I` treats it as
unsigned. Mixing them up is the most common bug in this section.

### Byte-level examples

| Python value | Type | Bytes (hex) | Notes |
|--------------|------|-------------|-------|
| `42` | `INTEGER` | `00 00 00 2a` | 42 = 0x2a |
| `-1` | `INTEGER` | `ff ff ff ff` | two's complement |
| `1234` | `INTEGER` | `00 00 04 d2` | 1234 = 0x04d2 |
| `"test"` | `STRING` | `74 65 73 74` | ASCII bytes |
| `""` | `STRING` | (empty) | length field handles emptiness |
| `"Hello 🌍"` | `STRING` | `48 65 6c 6c 6f 20 f0 9f 8c 8d` | UTF-8, emoji is 4 bytes |
| `1000000` | `COUNTER` | `00 0f 42 40` | 1,000,000 = 0x0f4240 |
| `4294967295` | `COUNTER` | `ff ff ff ff` | max unsigned |
| `360000` | `TIMETICKS` | `00 05 7e 40` | 360000 ticks = 3600 s = 1 hour |

### Reference implementation

```python
def encode_value(value, value_type):
    if value_type == ValueType.INTEGER:
        return struct.pack('!i', value)   # signed
    elif value_type == ValueType.STRING:
        if isinstance(value, bytes):
            return value                  # already bytes, pass through
        return value.encode('utf-8')
    elif value_type == ValueType.COUNTER:
        return struct.pack('!I', value)   # UNSIGNED
    elif value_type == ValueType.TIMETICKS:
        return struct.pack('!I', value)   # UNSIGNED
    else:
        raise ValueError(f"Unknown value type: {value_type}")


def decode_value(value_bytes, value_type):
    if value_type == ValueType.INTEGER:
        return struct.unpack('!i', value_bytes)[0]
    elif value_type == ValueType.STRING:
        return value_bytes.decode('utf-8')
    elif value_type == ValueType.COUNTER:
        return struct.unpack('!I', value_bytes)[0]
    elif value_type == ValueType.TIMETICKS:
        return struct.unpack('!I', value_bytes)[0]
    else:
        raise ValueError(f"Unknown value type: {value_type}")
```

### Common mistakes

- **Forgetting `[0]` after `struct.unpack`** — `unpack` returns a tuple even
  when you asked for a single value. `struct.unpack('!i', b)` returns `(42,)`;
  you want `struct.unpack('!i', b)[0]`.
- **Lowercase `i` for COUNTER/TIMETICKS** — `0xffffffff` decodes as `-1` with
  `!i` and as `4294967295` with `!I`. Use capital `I` for counters.
- **Calling `.encode()` on something that is already bytes** — if `value` is
  passed in as `bytes`, return it as-is for STRING. Otherwise
  `b'x'.encode('utf-8')` raises `AttributeError`.
- **Passing the wrong buffer length to `struct.unpack`** — integer types need
  exactly 4 bytes. If your slice is shorter, `struct.error: unpack requires a
  buffer of 4 bytes` appears.

### Verifying your implementation

```python
>>> encode_value(42, ValueType.INTEGER).hex()
'0000002a'

>>> decode_value(b'\xff\xff\xff\xff', ValueType.COUNTER)
4294967295

>>> decode_value(b'\xff\xff\xff\xff', ValueType.INTEGER)
-1

>>> decode_value(encode_value("router-1", ValueType.STRING), ValueType.STRING)
'router-1'
```

---

## Message Structure

Every SNMP message on the wire begins with a fixed **header** followed by a
variable-length PDU-specific payload. Requests use a 9-byte header; responses
use a 10-byte header because they include an `error_code` field.

### Header anatomy

```
Request header (GetRequest, SetRequest):
┌──────────────┬──────────────┬───────────┐
│ total_size   │ request_id   │ pdu_type  │
│ (4 bytes)    │ (4 bytes)    │ (1 byte)  │
└──────────────┴──────────────┴───────────┘

Response header (GetResponse):
┌──────────────┬──────────────┬───────────┬────────────┐
│ total_size   │ request_id   │ pdu_type  │ error_code │
│ (4 bytes)    │ (4 bytes)    │ (1 byte)  │ (1 byte)   │
└──────────────┴──────────────┴───────────┴────────────┘
```

| Field | Size | Format | Notes |
|-------|------|--------|-------|
| `total_size` | 4 | `!I` (unsigned, big-endian) | Includes itself — a 20-byte message puts `20` here, not `16` |
| `request_id` | 4 | `!I` | Used by the manager to match responses to requests |
| `pdu_type` | 1 | `!B` | `0xA0` = GetRequest, `0xA1` = GetResponse, `0xA3` = SetRequest |
| `error_code` | 1 | `!B` | **Responses only**: 0 SUCCESS, 1 NO_SUCH_OID, 2 BAD_VALUE, 3 READ_ONLY |

### The `total_size` rule

`total_size` counts every byte in the message, including the four bytes used
to encode `total_size` itself. For a GetRequest:

```
total_size = 4 (size field) + 4 (request_id) + 1 (pdu_type) + len(payload)
```

For a GetResponse add one more byte for `error_code`:

```
total_size = 4 + 4 + 1 + 1 + len(payload)
```

A good self-check in `pack()`:

```python
assert len(message) == total_size, f"size mismatch: {total_size} vs {len(message)}"
```

### Abstract base class

`SNMPMessage` is an abstract base class; you never instantiate it directly.
It fixes `request_id` and `pdu_type` on every concrete message and declares
two abstract methods:

- `pack(self) -> bytes` — serialize to network bytes
- `unpack(cls, data: bytes) -> SNMPMessage` — deserialize from network bytes

The three concrete subclasses (`GetRequest`, `SetRequest`, `GetResponse`) each
have their own section below.

### Size limits

- Minimum message: 9 bytes (GetResponse with an error and no bindings).
- Maximum message: 65,536 bytes — enforced by `receive_complete_message` to
  keep a malformed size field from allocating gigabytes.
- Maximum OIDs or bindings per message: 255 (the count field is one byte).

---

## Get Request

A GetRequest asks the agent for the current value of one or more OIDs. It is
the simplest message in the protocol: the payload is an OID count followed by
length-prefixed OIDs.

### Payload layout

```
┌────────────┬─────────────────────────────────────┐
│ oid_count  │ oid_1, oid_2, ..., oid_n            │
│ (1 byte)   │ (variable)                          │
└────────────┴─────────────────────────────────────┘

Each OID:
┌─────────────┬────────────┐
│ oid_length  │ oid_bytes  │
│ (1 byte)    │ (variable) │
└─────────────┴────────────┘
```

### Worked example

Building `GetRequest(request_id=1234, oids=["1.3.6.1.2.1.1.5.0"])`:

| Step | Bytes (hex) | Meaning |
|------|-------------|---------|
| `total_size` | `00 00 00 14` | 20 bytes total |
| `request_id` | `00 00 04 d2` | 1234 |
| `pdu_type` | `a0` | GET_REQUEST |
| `oid_count` | `01` | 1 OID |
| `oid_length` | `09` | 9 bytes |
| `oid_bytes` | `01 03 06 01 02 01 01 05 00` | `1.3.6.1.2.1.1.5.0` |

Payload size = 1 + 1 + 9 = 11 bytes. `total_size` = 4 + 4 + 1 + 11 = 20.

### Reference implementation

```python
def pack(self) -> bytes:
    payload = struct.pack('!B', len(self.oids))
    for oid in self.oids:
        oid_bytes = encode_oid(oid)
        payload += struct.pack('!B', len(oid_bytes))
        payload += oid_bytes

    total_size = 4 + 4 + 1 + len(payload)
    message = b''
    message += struct.pack('!I', total_size)
    message += struct.pack('!I', self.request_id)
    message += struct.pack('!B', self.pdu_type)
    message += payload
    return message


@classmethod
def unpack(cls, data: bytes) -> 'GetRequest':
    if len(data) < 10:
        raise ValueError(f"GetRequest too short: {len(data)} bytes")

    request_id = struct.unpack('!I', data[4:8])[0]
    oid_count = struct.unpack('!B', data[9:10])[0]

    offset = 10
    oids = []
    for _ in range(oid_count):
        oid_length = data[offset]
        offset += 1
        oid_bytes = data[offset:offset + oid_length]
        offset += oid_length
        oids.append(decode_oid(oid_bytes))

    return cls(request_id, oids)
```

### Common mistakes

- **Omitting the size field itself from `total_size`** — it must include
  those first four bytes.
- **Using `!H` or `!B` for `total_size`** — the spec says `!I` (4 bytes).
- **Passing `self.pdu_type` instead of `int(self.pdu_type)` to `struct.pack`** —
  this works because `PDUType` is an `IntEnum`, but if you ever subclass or
  strip the `IntEnum` base, it will break.

### Verifying your implementation

```python
>>> req = GetRequest(1234, ["1.3.6.1.2.1.1.5.0"])
>>> req.pack().hex()
'0000001400000400000000d2a001090103060102010105...'   # abbreviated
>>> len(req.pack())
20

>>> GetRequest.unpack(req.pack()).oids
['1.3.6.1.2.1.1.5.0']
```

---

## Set Request

A SetRequest asks the agent to update one or more OIDs. The payload looks like
GetRequest plus a value after each OID.

### Payload layout

```
┌────────────┬─────────────────────────────────────┐
│ oid_count  │ binding_1, binding_2, ..., binding_n│
│ (1 byte)   │ (variable)                          │
└────────────┴─────────────────────────────────────┘

Each binding:
┌─────────────┬────────────┬────────────┬──────────────┬────────────┐
│ oid_length  │ oid_bytes  │ value_type │ value_length │ value_data │
│ (1 byte)    │ (variable) │ (1 byte)   │ (2 bytes)    │ (variable) │
└─────────────┴────────────┴────────────┴──────────────┴────────────┘
```

Note that `value_length` is **2 bytes** (`!H`), not 1 — strings can be up to
65,535 bytes long.

### Worked example

Setting `sysName` to `"router1"`:

```
01                                 # 1 binding
09                                 # OID length
01 03 06 01 02 01 01 05 00         # OID 1.3.6.1.2.1.1.5.0
04                                 # value_type = STRING
00 07                              # value_length = 7 (TWO BYTES)
72 6f 75 74 65 72 31               # "router1"
```

Payload = 1 + 1 + 9 + 1 + 2 + 7 = 21 bytes. `total_size` = 4 + 4 + 1 + 21 = 30.

### Reference implementation

```python
def pack(self) -> bytes:
    payload = struct.pack('!B', len(self.bindings))
    for oid, value_type, value in self.bindings:
        oid_bytes = encode_oid(oid)
        payload += struct.pack('!B', len(oid_bytes))
        payload += oid_bytes

        value_bytes = encode_value(value, value_type)
        payload += struct.pack('!B', value_type)
        payload += struct.pack('!H', len(value_bytes))   # 2 bytes!
        payload += value_bytes

    total_size = 4 + 4 + 1 + len(payload)
    message = struct.pack('!I', total_size)
    message += struct.pack('!I', self.request_id)
    message += struct.pack('!B', self.pdu_type)
    message += payload
    return message


@classmethod
def unpack(cls, data: bytes) -> 'SetRequest':
    if len(data) < 10:
        raise ValueError(f"SetRequest too short: {len(data)} bytes")

    request_id = struct.unpack('!I', data[4:8])[0]
    binding_count = data[9]

    offset = 10
    bindings = []
    for _ in range(binding_count):
        oid_length = data[offset]; offset += 1
        oid = decode_oid(data[offset:offset + oid_length])
        offset += oid_length

        value_type = ValueType(data[offset]); offset += 1
        value_length = struct.unpack('!H', data[offset:offset + 2])[0]
        offset += 2
        value = decode_value(data[offset:offset + value_length], value_type)
        offset += value_length

        bindings.append((oid, value_type, value))

    return cls(request_id, bindings)
```

### Common mistakes

- **Using `!B` for `value_length`** — it's 2 bytes. A 1-byte field caps
  strings at 255 characters and desynchronizes the parser on longer values.
- **Forgetting to advance `offset` by 2 after reading `value_length`** — off-by-one
  bugs in `unpack` cascade into misaligned parsing of the next binding.
- **Calling `encode_value(value, value_type)` then `struct.pack('!H', value)`** —
  the 2-byte length field describes `len(value_bytes)`, not the Python value.

---

## Get Response

A GetResponse is how the agent replies to both GetRequest and SetRequest. It
has the same binding payload as SetRequest, but adds a one-byte `error_code`
between the PDU type and the payload.

### Header difference

```
┌──────────────┬──────────────┬───────────┬────────────┬──────────────┐
│ total_size   │ request_id   │ pdu_type  │ error_code │ payload      │
│ (4 bytes)    │ (4 bytes)    │ (1 byte)  │ (1 byte)   │ (variable)   │
└──────────────┴──────────────┴───────────┴────────────┴──────────────┘
                                           ↑
                                   THIS EXTRA BYTE
```

The header is 10 bytes instead of 9, so:

```
total_size = 4 + 4 + 1 + 1 + len(payload)
```

### Error codes

| Name | Value | Meaning |
|------|-------|---------|
| `SUCCESS` | 0 | Bindings contain the requested values |
| `NO_SUCH_OID` | 1 | One or more OIDs are not in the MIB |
| `BAD_VALUE` | 2 | SetRequest value rejected (wrong type, out of range) |
| `READ_ONLY` | 3 | SetRequest targeted a read-only OID |

Even error responses may include bindings (or an empty list) — always include
a `binding_count`, even if it is 0.

### Worked example

`GetResponse(request_id=1234, error_code=SUCCESS, bindings=[("1.3.6.1.2.1.1.5.0", STRING, "test")])`:

```
00 00 00 1c           # total_size = 28
00 00 04 d2           # request_id = 1234
a1                    # pdu_type   = GET_RESPONSE
00                    # error_code = SUCCESS
01                    # binding_count
09                    # oid_length
01 03 06 01 02 01 01 05 00   # OID bytes
04                    # value_type = STRING
00 04                 # value_length = 4
74 65 73 74           # "test"
```

### Reference implementation

```python
def pack(self) -> bytes:
    payload = struct.pack('!B', len(self.bindings))
    for oid, value_type, value in self.bindings:
        oid_bytes = encode_oid(oid)
        payload += struct.pack('!B', len(oid_bytes))
        payload += oid_bytes

        value_bytes = encode_value(value, value_type)
        payload += struct.pack('!B', value_type)
        payload += struct.pack('!H', len(value_bytes))
        payload += value_bytes

    total_size = 4 + 4 + 1 + 1 + len(payload)      # note the extra +1
    message = struct.pack('!I', total_size)
    message += struct.pack('!I', self.request_id)
    message += struct.pack('!B', self.pdu_type)
    message += struct.pack('!B', self.error_code)  # EXTRA FIELD
    message += payload
    return message


@classmethod
def unpack(cls, data: bytes) -> 'GetResponse':
    request_id = struct.unpack('!I', data[4:8])[0]
    error_code = ErrorCode(data[9])                # byte 9
    binding_count = data[10]                       # bindings start at 10

    offset = 11
    bindings = []
    for _ in range(binding_count):
        oid_length = data[offset]; offset += 1
        oid = decode_oid(data[offset:offset + oid_length])
        offset += oid_length

        value_type = ValueType(data[offset]); offset += 1
        value_length = struct.unpack('!H', data[offset:offset + 2])[0]
        offset += 2
        value = decode_value(data[offset:offset + value_length], value_type)
        offset += value_length

        bindings.append((oid, value_type, value))

    return cls(request_id, error_code, bindings)
```

### Common mistakes

- **Using `4 + 4 + 1 + len(payload)` for `total_size`** — you forgot the
  `error_code` byte; the receiver will think the message is one byte shorter
  than it actually is and mis-parse everything.
- **Reading `binding_count` from `data[9]`** — that is the error code! Bindings
  start at `data[10]`; the first binding's `oid_length` is `data[11]`.
- **Sending no payload on errors** — always send `binding_count = 0` (one byte),
  not zero bytes. A missing byte makes `total_size` not match.

---

## Unpacking Messages

`unpack_message(data)` is the dispatcher: it peeks at the PDU type byte and
hands the bytes off to the right subclass. The test suite and the manager's
receive loop both call this instead of picking a subclass directly.

### Algorithm

1. Verify the message is at least `MIN_MESSAGE_SIZE` (9 bytes) long.
2. Read `data[8]` as the `pdu_type`.
3. Dispatch:

   | Byte value | Class |
   |-----------|-------|
   | `0xA0` | `GetRequest.unpack(data)` |
   | `0xA1` | `GetResponse.unpack(data)` |
   | `0xA3` | `SetRequest.unpack(data)` |
   | anything else | `raise ValueError` |

4. Return the resulting `SNMPMessage` subclass instance.

### Reference implementation

```python
def unpack_message(data: bytes) -> SNMPMessage:
    if len(data) < MIN_MESSAGE_SIZE:
        raise ValueError(f"Message too short: {len(data)} bytes")

    pdu_type = data[PDU_TYPE_OFFSET]  # byte 8

    if pdu_type == PDUType.GET_REQUEST:
        return GetRequest.unpack(data)
    elif pdu_type == PDUType.SET_REQUEST:
        return SetRequest.unpack(data)
    elif pdu_type == PDUType.GET_RESPONSE:
        return GetResponse.unpack(data)
    else:
        raise ValueError(f"Unknown PDU type: 0x{pdu_type:02X}")
```

The provided template already handles this; you generally do not need to
change it, but knowing how it works helps when tracing a test failure from a
socket up through `unpack_message` into a specific `.unpack()`.

---

## Message Framing

TCP is a **byte stream**, not a message-oriented protocol. A single
`sock.recv(n)` call may return anywhere from 1 byte to `n` bytes — never zero
unless the connection has closed. Your code has to reassemble the stream into
discrete SNMP messages. `receive_complete_message` is where that happens, and
every other networking test depends on it being correct.

### The problem

If the server sends a 100-byte message, the client might see:

```
recv() -> 40 bytes
recv() -> 35 bytes
recv() -> 25 bytes
```

Three chunks, one logical message. The *next* `recv()` could return bytes
from the **next** message. A single `sock.recv(4096)` is therefore almost
never the right call.

### The two-phase algorithm

Our protocol solves this by putting the message's total length in its first
four bytes, so the receiver can read in two phases:

**Phase 1 — read the size field (4 bytes).** Loop until the buffer has exactly
4 bytes, then decode them as `!I`.

**Phase 2 — read the remainder.** Loop until the buffer length equals the
declared `total_size`. Cap each `recv()` at `MAX_RECV_BUFFER` (4096 bytes).

```
start
  │
  ▼
  buffer = b''
  │
  ▼
┌─────────────────────────────┐
│ while len(buffer) < 4:      │  ◄── phase 1
│     chunk = recv(4 - len)   │
│     if not chunk: raise     │
│     buffer += chunk         │
└─────────────────────────────┘
  │
  ▼
  size = struct.unpack('!I', buffer[:4])[0]
  validate MIN <= size <= MAX
  │
  ▼
┌─────────────────────────────────────────────┐
│ while len(buffer) < size:                   │  ◄── phase 2
│     remaining = size - len(buffer)          │
│     chunk = recv(min(remaining, 4096))      │
│     if not chunk: raise                     │
│     buffer += chunk                         │
└─────────────────────────────────────────────┘
  │
  ▼
  return buffer
```

### Reference implementation

```python
def receive_complete_message(sock) -> bytes:
    received = b''

    # Phase 1: read the 4-byte size field
    while len(received) < 4:
        chunk = sock.recv(4 - len(received))
        if not chunk:
            raise ConnectionError("Connection closed while reading size")
        received += chunk

    message_size = struct.unpack('!I', received[:4])[0]
    if message_size < MIN_MESSAGE_SIZE or message_size > MAX_MESSAGE_SIZE:
        raise ValueError(f"Invalid message size: {message_size}")

    # Phase 2: read the rest of the message
    while len(received) < message_size:
        remaining = message_size - len(received)
        chunk = sock.recv(min(remaining, MAX_RECV_BUFFER))
        if not chunk:
            raise ConnectionError("Connection closed while reading message")
        received += chunk

    return received
```

### Common mistakes

- **Calling `sock.recv(4096)` unconditionally** — if there are two messages
  queued, you will read the start of the next message into the current one.
  Cap each `recv()` at exactly the bytes you still need.
- **Skipping the empty-chunk check** — `sock.recv()` returning `b''` means
  the peer closed the connection. Without a check, the loop spins forever.
- **Using little-endian to decode the size** — `int.from_bytes(..., 'little')`
  or `struct.unpack('<I', ...)` will give you garbage. The wire uses
  big-endian (`!I`).
- **Allocating the full `message_size` up front** — a malicious peer could
  send `0xFFFFFFFF` as the size. Always validate against `MAX_MESSAGE_SIZE`
  before trusting it.

### Why this matters

This same pattern — a length prefix and a two-phase read — is used by HTTP/2
frames, WebSocket payloads, MySQL and PostgreSQL packet handling, most video
streaming protocols, and many IoT protocols (MQTT, CoAP). Getting it right
here pays off for the rest of your career.

### Verifying your implementation

```bash
python -m pytest tests/test_public_snmp_protocol.py -v -k "buffer or partial or framing"
```

Key scenarios the test suite exercises:

- Single small message arriving in one `recv()`.
- Partial sends — the 4-byte size field spread across multiple chunks.
- Consecutive messages back-to-back — your implementation must stop at the
  correct boundary.
- Large messages that require multiple 4096-byte chunks.
- Connection closed mid-message — should raise `ConnectionError`.

---

## Constants Reference

One table showing every module-level constant the implementation refers to.
If you see a symbol in a code sample and want to know its value without
greping, start here.

### `template/snmp_protocol.py` — wire format

| Constant | Value | What it governs |
|----------|-------|-----------------|
| `MESSAGE_HEADER_SIZE` | `9` | Bytes before payload in a request (`total_size + request_id + pdu_type`) |
| `RESPONSE_HEADER_SIZE` | `10` | Bytes before payload in a response (adds `error_code`) |
| `MIN_MESSAGE_SIZE` | `9` | Smallest legal message — reject anything shorter |
| `MAX_MESSAGE_SIZE` | `65536` | Hard cap in `receive_complete_message`; stops a malformed `total_size` from allocating gigabytes |
| `MAX_RECV_BUFFER` | `4096` | Upper bound for a single `recv()` chunk |
| `SIZE_FIELD_LENGTH` | `4` | Width of the `total_size` field |
| `REQUEST_ID_LENGTH` | `4` | Width of the `request_id` field |
| `PDU_TYPE_LENGTH` | `1` | Width of the `pdu_type` field |
| `ERROR_CODE_LENGTH` | `1` | Width of the response-only `error_code` field |
| `OID_COUNT_LENGTH` | `1` | Width of the per-PDU `oid_count` / `binding_count` field |
| `OID_LENGTH_FIELD` | `1` | Width of each OID's length prefix |
| `VALUE_TYPE_LENGTH` | `1` | Width of the per-value type tag |
| `VALUE_LENGTH_FIELD` | `2` | Width of each value's length prefix |
| `OID_COUNT_MAX` | `255` | Maximum OIDs or bindings in one message (1-byte count field) |
| `PDU_TYPE_OFFSET` | `8` | Byte offset where `pdu_type` lives — useful for early dispatch without full unpack |
| `REQUEST_ID_OFFSET` | `4` | Byte offset where `request_id` lives |

### `template/snmp_agent.py` — server-side

| Constant | Value | What it governs |
|----------|-------|-----------------|
| `DEFAULT_PORT` | `1161` | Non-privileged port. The real SNMP port (161) requires root; 1161 doesn't |
| `LISTEN_BACKLOG` | `5` | Accept-queue depth passed to `socket.listen()` |
| `TIMEOUT_SECONDS` | `10.0` | Per-connection socket timeout on the agent side |
| `TIMETICKS_PER_SECOND` | `100` | SNMP timeticks are 1/100s — used when reporting `sysUpTime` |

### `template/snmp_manager.py` — client-side

| Constant | Value | What it governs |
|----------|-------|-----------------|
| `DEFAULT_TIMEOUT` | `10.0` | Socket timeout on the client side |
| `TIMETICKS_PER_SECOND` | `100` | Same as agent — used when formatting timetick values for display |

These values are all tuned for the assignment, not the real SNMP standard.
Do not change them; the tests depend on the protocol behaving the way this
table describes.
