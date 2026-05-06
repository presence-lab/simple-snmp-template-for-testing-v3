# Testing Guide for SNMP Protocol Implementation

## Important: Project Directory Structure

**Your working directory should be the project root folder** (not the `src/` directory). All commands assume you're running from the root:

```
project/                    ← You should be here
├── src/                    ← Your implementation files
│   ├── snmp_protocol.py
│   ├── snmp_agent.py
│   ├── snmp_manager.py
│   └── mib_database.py
├── tests/                  ← Test files
├── template/               ← Original starter files
└── run_tests.py           ← Test runner
```

**Tests automatically look for your code in the `src/` directory**, so you don't need to change directories or modify imports.

## Quick Start

### Run Tests with Grading Script
```bash
# From project root directory
# See your current grade
python run_tests.py

# See detailed results
python run_tests.py -v

# Test specific bundle
python run_tests.py -m "bundle_C"  # C-level tests
python run_tests.py -m "bundle_B"  # B-level tests
python run_tests.py -m "bundle_A"  # A-level tests
```

### Run Tests with pytest
```bash
# From project root directory
# Run all tests
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_protocol_structure.py -v

# Run tests matching a pattern
python -m pytest tests/ -k "oid" -v
```

---

## VS Code Testing Integration

### Setting Up VS Code

1. **Install VS Code** and open the project folder
2. **Install recommended extensions** when prompted (or search for @recommended in Extensions)
3. **Select Python interpreter**: Press `Ctrl+Shift+P` → "Python: Select Interpreter" → Choose your venv

### Using the Test Explorer

#### Visual Test Runner
1. Click the **Testing** icon in the Activity Bar (flask icon on left sidebar)
2. All tests appear in a tree view organized by file and function
3. Click the ▶ button next to any test to run it
4. Results show immediately: ✅ = passed, ❌ = failed
5. Click on a failed test to jump to the failure location

#### Running Tests from VS Code

**Option 1: Test Explorer (Visual)**
- Click play buttons next to tests/folders in Testing sidebar
- Run individual tests, test files, or all tests
- See live results with colored indicators

**Option 2: Command Palette** (`Ctrl+Shift+P`)
- "Python: Run All Tests"
- "Python: Run Test Method"
- "Python: Debug Test Method"

**Option 3: Tasks** (`Ctrl+Shift+B`)
- "Run All Tests" - runs grading script
- "Run Tests (Verbose)" - detailed output
- "Run Tests (Bundle 1/2/3)" - specific bundles
- "Test with Coverage" - see code coverage

**Option 4: Keyboard Shortcuts**
- `F5` - Debug current test
- `Ctrl+F5` - Run without debugging
- `Shift+F5` - Stop debugging

### Debugging Tests in VS Code

#### Setting Breakpoints
1. Click in the gutter (left of line numbers) to set a red breakpoint
2. Open a test file or your implementation
3. Set breakpoints where you want to investigate

#### Debug Configurations
Press `F5` or use Run and Debug sidebar:
- **Python: Current File** - Debug the open file
- **Python: Run Tests (All)** - Debug all tests
- **Python: Run Tests (Current File)** - Debug tests in current file
- **Python: Debug Tests (Current Test)** - Debug specific test

#### Debug Controls
- `F5` - Continue execution
- `F10` - Step over (execute current line)
- `F11` - Step into (enter function calls)
- `Shift+F11` - Step out (exit current function)
- `F9` - Toggle breakpoint

#### Debug Panel Features
- **Variables**: See all local and global variables
- **Watch**: Monitor specific expressions
- **Call Stack**: Trace execution path
- **Breakpoints**: Manage all breakpoints

### VS Code Productivity Tips

#### Essential Shortcuts
- `` Ctrl+` `` - Toggle terminal
- `Ctrl+Shift+P` - Command palette
- `Ctrl+P` - Quick file open
- `F12` - Go to definition
- `Shift+F12` - Find all references
- `F2` - Rename symbol

#### Test-Specific Features
- **Inline Test Results**: See pass/fail directly in code
- **Test Output**: View detailed output in OUTPUT panel
- **Problem Matcher**: Errors appear in PROBLEMS panel
- **CodeLens**: Run/debug buttons above each test

---

## Test Categories and Structure

### Bundle C: Core Protocol (25 tests)

#### Protocol Structure Tests
```bash
# Test OID encoding/decoding
python -m pytest tests/ -k "test_oid" -v

# Test message structure
python -m pytest tests/ -k "test_header" -v

# Test byte ordering
python -m pytest tests/ -k "test_byte_order" -v
```

#### Basic Operations Tests
```bash
# Test single GET operations
python -m pytest tests/ -k "test_single_get" -v

# Test agent startup
python -m pytest tests/ -k "test_agent_start" -v
```

### Bundle B: Advanced Features (20 tests)

#### Multiple OID Tests
```bash
# Test multiple OID queries
python -m pytest tests/ -k "test_multiple_oid" -v

# Test error handling
python -m pytest tests/ -k "test_error" -v
```

#### SET Operation Tests
```bash
# Test SET requests
python -m pytest tests/ -k "test_set" -v

# Test permission checking
python -m pytest tests/ -k "test_readonly" -v
```

### Bundle A: Production Quality (15 tests)

#### Buffering Tests
```bash
# Test large messages
python -m pytest tests/ -k "test_large_message" -v

# Test fragmentation
python -m pytest tests/ -k "test_buffer" -v
```

#### Robustness Tests
```bash
# Test stress conditions
python -m pytest tests/ -k "test_stress" -v

# Test malformed input
python -m pytest tests/ -k "test_malformed" -v
```

---

## Manual Testing

### Starting the Agent
```bash
# Terminal 1: Start agent
python snmp_agent.py
# Should output: SNMP Agent listening on port 1161...
```

### Testing with Manager
```bash
# Terminal 2: Test commands

# Single GET
python snmp_manager.py get localhost:1161 1.3.6.1.2.1.1.1.0

# Multiple GET
python snmp_manager.py get localhost:1161 1.3.6.1.2.1.1.1.0 1.3.6.1.2.1.1.5.0

# SET operation
python snmp_manager.py set localhost:1161 1.3.6.1.2.1.1.5.0 string "test-name"

# Verify SET worked
python snmp_manager.py get localhost:1161 1.3.6.1.2.1.1.5.0
```

### Interactive Testing with Python
```python
# Start Python REPL
python

>>> from snmp_protocol import *
>>> from snmp_manager import SNMPManager
>>> 
>>> # Test protocol functions
>>> oid = "1.3.6.1.2.1.1.5.0"
>>> encoded = encode_oid(oid)
>>> print(f"Encoded: {encoded.hex()}")
>>> 
>>> # Test message creation
>>> req = GetRequest(1234, [oid])
>>> packed = req.pack()
>>> print(f"Message: {packed.hex()}")
>>> 
>>> # Test manager
>>> manager = SNMPManager()
>>> manager.get("localhost", 1161, [oid])
```

---

## Debugging Failed Tests

### Understanding Test Output

#### pytest Output Format
```
tests/test_protocol_structure.py::test_oid_encoding FAILED

================================= FAILURES =================================
______________________________ test_oid_encoding ______________________________

    def test_oid_encoding():
        oid = "1.3.6.1.2.1.1.5.0"
        expected = b'\x01\x03\x06\x01\x02\x01\x01\x05\x00'
>       assert encode_oid(oid) == expected
E       AssertionError: assert None == b'\x01\x03\x06...'
E         Expected: b'\x01\x03\x06\x01\x02\x01\x01\x05\x00'
E         Got: None
```

#### Reading Error Messages
- **Test name**: Shows which test failed
- **Expected vs Got**: Shows what the test expected and what your code produced
- **Line number**: Click to jump to the failing assertion
- **Traceback**: Shows the call stack leading to the error

### Common Test Failures and Solutions

#### Protocol Tests Failing

**Issue**: "struct.error: unpack requires a buffer of 4 bytes"
```python
# Problem: Not enough data for unpacking
data = b'\x00\x00'  # Only 2 bytes
size = struct.unpack('!I', data)  # Expects 4 bytes!

# Solution: Check data length first
if len(data) >= 4:
    size = struct.unpack('!I', data[:4])[0]
```

**Issue**: "AssertionError: Byte order incorrect"
```python
# Problem: Using wrong byte order
value = struct.pack('<I', 22)  # Little-endian (wrong!)

# Solution: Use network byte order
value = struct.pack('!I', 22)  # Big-endian (correct!)
```

#### Operation Tests Failing

**Issue**: "Connection refused"
```python
# Problem: Agent not running or wrong port

# Solution 1: Start agent first
# Terminal 1: python snmp_agent.py

# Solution 2: Check port number
# Should be 1161, not 161
```

**Issue**: "Timeout waiting for response"
```python
# Problem: Message not being sent completely

# Solution: Ensure complete message transmission
def send_message(sock, message):
    total_sent = 0
    while total_sent < len(message):
        sent = sock.send(message[total_sent:])
        total_sent += sent
```

#### Buffering Tests Failing

**Issue**: "Message incomplete or corrupted"
```python
# Problem: Not handling fragmented messages

# Solution: Implement proper buffering
def receive_message(sock):
    # Get size first
    size_bytes = receive_exactly(sock, 4)
    size = struct.unpack('!I', size_bytes)[0]
    
    # Get complete message
    message = size_bytes + receive_exactly(sock, size - 4)
    return message

def receive_exactly(sock, n):
    data = b''
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise ConnectionError("Socket closed")
        data += chunk
    return data
```

### Debug Helpers

#### Add to Your Code for Debugging
```python
import logging
logging.basicConfig(level=logging.DEBUG)

def debug_bytes(label, data):
    """Print bytes in readable format."""
    logging.debug(f"{label}:")
    logging.debug(f"  Length: {len(data)} bytes")
    logging.debug(f"  Hex: {data.hex()}")
    logging.debug(f"  Spaced: {' '.join(f'{b:02x}' for b in data)}")

def debug_message(message_bytes):
    """Analyze SNMP message structure."""
    if len(message_bytes) < 9:
        logging.error(f"Message too short: {len(message_bytes)} bytes")
        return
    
    size = struct.unpack('!I', message_bytes[0:4])[0]
    req_id = struct.unpack('!I', message_bytes[4:8])[0]
    pdu_type = message_bytes[8]
    
    logging.debug(f"Message Analysis:")
    logging.debug(f"  Size: {size}")
    logging.debug(f"  Request ID: {req_id}")
    logging.debug(f"  PDU Type: 0x{pdu_type:02x}")
```

---

## Test Coverage

### Running with Coverage
```bash
# Generate coverage report
python -m pytest tests/ --cov=. --cov-report=term-missing

# Generate HTML coverage report
python -m pytest tests/ --cov=. --cov-report=html
# Open htmlcov/index.html in browser
```

### Understanding Coverage Output
```
Name                 Stmts   Miss  Cover   Missing
----------------------------------------------------
snmp_protocol.py       120     15    88%   45-50, 78-82
snmp_agent.py          150     20    87%   120-125, 200-210
snmp_manager.py         80      5    94%   55-59
----------------------------------------------------
TOTAL                  350     40    89%
```

- **Stmts**: Total statements in file
- **Miss**: Statements not executed by tests
- **Cover**: Percentage of code covered
- **Missing**: Line numbers not covered

### Improving Coverage
1. Look at "Missing" line numbers
2. Write tests that exercise those code paths
3. Focus on error handling and edge cases
4. Aim for >90% coverage for production code

---

## Performance Testing

### Running Performance Tests
```bash
# Show slowest tests
python -m pytest tests/ --durations=10

# Run with timeout
python -m pytest tests/ --timeout=60

# Profile specific test
python -m cProfile -s cumtime snmp_manager.py get localhost:1161 1.3.6.1.2.1.1.1.0
```

### Stress Testing
```python
# Test with many OIDs
oids = [f"1.3.6.1.2.1.1.{i}.0" for i in range(100)]
python snmp_manager.py get localhost:1161 ' '.join(oids)

# Test rapid connections
for i in range(100):
    python snmp_manager.py get localhost:1161 1.3.6.1.2.1.1.1.0
```

---

## Continuous Testing

### Watch Mode (Auto-run on File Changes)
```bash
# Install pytest-watch
pip install pytest-watch

# Run tests automatically on file save
ptw tests/ -- -v
```

### Git Pre-commit Hook
```bash
# Create .git/hooks/pre-commit
#!/bin/bash
python -m pytest tests/ -q
if [ $? -ne 0 ]; then
    echo "Tests failed. Commit aborted."
    exit 1
fi
```

---

## Test Organization Best Practices

### Writing Your Own Tests
```python
# tests/test_my_features.py
import pytest
from snmp_protocol import *

class TestMyFeatures:
    """Group related tests together."""
    
    def test_feature_one(self):
        """Test names should be descriptive."""
        # Arrange
        input_data = "test"
        
        # Act
        result = my_function(input_data)
        
        # Assert
        assert result == expected_value
    
    @pytest.mark.skip(reason="Not implemented yet")
    def test_future_feature(self):
        """Mark tests to skip temporarily."""
        pass
    
    @pytest.mark.parametrize("input,expected", [
        ("1.3.6", b'\x01\x03\x06'),
        ("1", b'\x01'),
    ])
    def test_multiple_cases(self, input, expected):
        """Test multiple inputs with one test."""
        assert encode_oid(input) == expected
```

### Test Fixtures
```python
@pytest.fixture
def test_agent():
    """Create an agent for testing."""
    agent = SNMPAgent(port=11610)  # Use test port
    yield agent
    agent.shutdown()  # Cleanup

def test_with_agent(test_agent):
    """Use the fixture in a test."""
    response = test_agent.process_request(request)
    assert response.error_code == 0
```

---

## Troubleshooting

### VS Code Issues

**Tests not showing in Test Explorer?**
1. Select correct Python interpreter: `Ctrl+Shift+P` → "Python: Select Interpreter"
2. Refresh tests: `Ctrl+Shift+P` → "Python: Refresh Tests"
3. Check test discovery settings in `.vscode/settings.json`

**Debugging not working?**
1. Ensure virtual environment is activated
2. Check that pytest is installed: `pip install pytest`
3. Verify launch.json configuration exists

### Common Test Issues

**Import errors?**
```bash
# Add project root to Python path
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
```

**Port already in use?**
```bash
# Find process using port
lsof -i :1161
# Or on Windows
netstat -ano | findstr :1161

# Kill the process
kill <PID>
```

**Tests hanging?**
- Add timeout to tests: `@pytest.mark.timeout(30)`
- Check for infinite loops in buffering code
- Verify socket cleanup in teardown

---

## Summary

### Quick Reference

| Task | Command |
|------|---------|
| Check grade | `python run_tests.py` |
| Run all tests | `python -m pytest tests/ -v` |
| Run specific bundle | `python run_tests.py -m "bundle_C"` |
| Debug in VS Code | Set breakpoint → `F5` |
| Test coverage | `python -m pytest tests/ --cov=.` |
| Run one test | `python -m pytest tests/ -k "test_name"` |

### Testing Workflow

1. **Write code** for one feature
2. **Run relevant tests** to check progress
3. **Debug failures** using VS Code debugger
4. **Check coverage** to find untested code
5. **Run full suite** before committing
6. **Check grade** with `run_tests.py`

Remember: Good tests help you write better code. Use them as a guide, not just a grade check!