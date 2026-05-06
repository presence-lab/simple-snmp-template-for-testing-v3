# Specification Grading for SNMP Protocol Implementation

## Overview

This course uses **specification grading** (or "specs grading"), a mastery-based approach where:
- Work is evaluated as **satisfactory/unsatisfactory** (complete/incomplete)
- You must pass **ALL tests** in a bundle to receive credit for that bundle
- Your grade is determined by **which bundles you complete**, not averages or percentages
- **No partial credit** within bundles—your implementation either meets the specification or it doesn't

This approach mirrors professional software development where "mostly working" isn't acceptable. Your code must meet all specifications, just like production software.

---

## Grade Determination

### Bundle Requirements

| Grade | Required Bundles | Learning Focus |
|-------|-----------------|----------------|
| **C** | Bundle C only | Core protocol implementation and basic operations |
| **B** | Bundles C + B | Complete GET/SET operations with error handling |
| **A** | Bundles C + B + A | Production-ready with buffering and robustness |

**Important:** Bundles are cumulative. To earn a B, you must pass ALL tests in both Bundle C and Bundle B.

---

## Bundle C: Core Protocol Implementation (C Grade)

### Learning Objectives
- Implement binary protocol encoding/decoding
- Build a functional TCP client-server system
- Handle basic SNMP GET operations
- Parse and generate protocol-compliant messages

### Required Functionality
You must pass **100% of tests** in these categories:

#### Protocol Structure Tests
- ✅ OID encoding (string → bytes)
- ✅ OID decoding (bytes → string)
- ✅ Message header structure (size, request_id, pdu_type)
- ✅ GetRequest message packing
- ✅ GetResponse message unpacking
- ✅ Proper byte ordering (big-endian)

#### Basic Operations Tests
- ✅ Agent starts and listens on port 1161
- ✅ Manager connects and sends requests
- ✅ Single OID GET queries work
- ✅ Response includes correct request ID
- ✅ Values are properly encoded

#### Implementation Requirements
```python
# Your agent must handle:
def handle_get_request(oid):
    # Look up OID in MIB
    # Return proper GetResponse
    # Include correct value type

# Your manager must:
def get(host, port, oid):
    # Create GetRequest
    # Send to agent
    # Receive response
    # Display result
```

### How to Verify
```bash
# Run C-level tests only
python run_tests.py -m "bundle_C"

# Or using pytest directly
python -m pytest tests/ -m "bundle_C" -v
```

---

## Bundle B: Complete GET/SET Implementation (B Grade)

### Learning Objectives
- Handle multiple OIDs in single request
- Implement SET operations with validation
- Provide comprehensive error handling
- Maintain persistent state across requests

### Required Functionality
You must ALSO pass **100% of tests** in these categories:

#### Advanced GET Operations
- ✅ Multiple OID queries in single request
- ✅ Non-existent OID error handling (error code 1)
- ✅ Empty OID list handling
- ✅ Duplicate OID handling
- ✅ System uptime updates between queries

#### SET Operations
- ✅ SetRequest message encoding/decoding
- ✅ Writable OID modifications
- ✅ Read-only OID rejection (error code 3)
- ✅ Type validation (STRING, INTEGER, etc.)
- ✅ Value persistence across connections
- ✅ Invalid type rejection (error code 2)

#### Error Handling
- ✅ Proper error codes in responses
- ✅ Request ID preservation in errors
- ✅ Graceful handling of malformed requests
- ✅ Connection error recovery

#### Implementation Requirements
```python
# Your agent must handle:
def handle_set_request(oid, value_type, value):
    # Check if OID is writable
    # Validate value type
    # Update MIB if allowed
    # Return error if not

# Your manager must:
def set(host, port, oid, value_type, value):
    # Create SetRequest
    # Handle type conversion
    # Display success or error
```

### How to Verify
```bash
# Run B-level tests only
python run_tests.py -m "bundle_B"

# Test specific functionality
python snmp_manager.py set localhost:1161 1.3.6.1.2.1.1.5.0 string "test"
python snmp_manager.py get localhost:1161 1.3.6.1.2.1.1.1.0 1.3.6.1.2.1.1.5.0
```

---

## Bundle A: Production-Ready Implementation (A Grade)

### Learning Objectives
- Handle message fragmentation over TCP
- Implement robust buffering for large messages
- Recover from network and protocol errors
- Build production-quality network software

### Required Functionality
You must ALSO pass **100% of tests** in these categories:

#### Message Buffering
- ✅ Messages larger than socket buffer (>4096 bytes)
- ✅ Proper reassembly of fragmented messages
- ✅ Handling partial message reception
- ✅ Multiple consecutive messages
- ✅ Size field validation

#### Advanced Error Handling
- ✅ Malformed message rejection
- ✅ Invalid size field handling
- ✅ Connection interruption recovery
- ✅ Timeout handling
- ✅ Resource cleanup on errors

#### Robustness Tests
- ✅ Stress testing with many OIDs
- ✅ Large value handling (long strings)
- ✅ Rapid successive connections
- ✅ Invalid PDU type rejection
- ✅ Buffer overflow prevention

#### Implementation Requirements
```python
def receive_complete_message(sock):
    # Read size field first
    # Continue reading until complete
    # Handle partial receives
    # Validate total size
    # Never read beyond message boundary

def handle_large_response(bindings):
    # Build response that may exceed 4096 bytes
    # Ensure proper transmission
    # Client must reassemble correctly
```

### How to Verify
```bash
# Run A-level tests only
python run_tests.py -m "bundle_A"

# Run all tests
python run_tests.py
```

---

## Checking Your Progress

### Quick Grade Check
```bash
# See your current grade level
python run_tests.py

# Output will show:
# Bundle C: PASSED/FAILED (X/Y tests)
# Bundle B: PASSED/FAILED (X/Y tests)  
# Bundle A: PASSED/FAILED (X/Y tests)
# 
# Current Grade: C/B/A/F
```

### Detailed Test Results
```bash
# See which specific tests are failing
python run_tests.py -v

# See only failing tests
python run_tests.py --failed
```

### Test Categories
```bash
# Test by category
python -m pytest tests/ -k "protocol" -v     # Protocol tests
python -m pytest tests/ -k "buffering" -v   # Buffering tests
python -m pytest tests/ -k "get" -v         # GET operation tests
python -m pytest tests/ -k "set" -v         # SET operation tests
```

---

## Common Pitfalls and Solutions

### Bundle C Pitfalls

**Problem:** "My OID encoding works manually but fails tests"
- **Cause:** Not handling edge cases (empty OID, single number)
- **Solution:** Test with various OID lengths

**Problem:** "Agent crashes when manager connects"
- **Cause:** Not setting SO_REUSEADDR or handling exceptions
- **Solution:** Add proper socket options and try-except blocks

### Bundle B Pitfalls

**Problem:** "SET works once but fails on second attempt"
- **Cause:** Not persisting changes in MIB
- **Solution:** Ensure MIB updates are stored, not just returned

**Problem:** "Multiple OID query returns wrong values"
- **Cause:** Incorrect parsing of request or response building
- **Solution:** Debug byte-by-byte with hex output

### Bundle A Pitfalls

**Problem:** "Large messages arrive corrupted"
- **Cause:** Not handling message fragmentation
- **Solution:** Implement proper buffering loop

**Problem:** "Tests timeout on large messages"
- **Cause:** Infinite loop in receive or deadlock
- **Solution:** Add logging to trace execution flow

---

## Tips for Success

### Start with Bundle C
1. Implement OID encoding/decoding first
2. Get basic message structure working
3. Test with single OID queries
4. Ensure agent accepts connections
5. Verify manager can display responses

### Progress to Bundle B
1. Add multiple OID support incrementally
2. Implement error codes one at a time
3. Test SET with different value types
4. Verify persistence with consecutive gets

### Complete with Bundle A
1. Test with increasingly large messages
2. Simulate network delays and interruptions
3. Verify no data loss or corruption
4. Stress test with many rapid requests

### General Advice
- **Read specifications carefully:** Every byte matters in binary protocols
- **Test after each feature:** Don't implement everything before testing
- **Use version control:** Commit working versions before adding features
- **Collaborate wisely:** Discuss approaches but write your own code
- **Start early:** Network debugging takes more time than expected

---

## Grade Calculation Example

### Scenario 1: All Bundle C tests pass, some Bundle B tests fail
- Bundle C: ✅ PASSED (25/25 tests)
- Bundle B: ❌ FAILED (18/20 tests)
- Bundle A: ❌ NOT ATTEMPTED
- **Grade: C** (Bundle B requires 100% of tests)

### Scenario 2: All C and B tests pass, A tests not attempted
- Bundle C: ✅ PASSED (25/25 tests)
- Bundle B: ✅ PASSED (20/20 tests)
- Bundle A: ❌ NOT ATTEMPTED
- **Grade: B**

### Scenario 3: All tests pass
- Bundle C: ✅ PASSED (25/25 tests)
- Bundle B: ✅ PASSED (20/20 tests)
- Bundle A: ✅ PASSED (15/15 tests)
- **Grade: A**

---

## Academic Integrity

While collaboration on understanding concepts is encouraged:
- **Write your own code:** Don't copy from others or online sources
- **Document resources:** Cite any references you use
- **Test your own work:** Don't rely on others' test results
- **Understand your code:** Be prepared to explain any part of your implementation

Remember: The goal is to learn network programming, not just to pass tests. The skills you develop here will be valuable throughout your career.