"""
Utility classes and functions for SNMP protocol testing.
"""

import socket
import threading
import time
import struct
from typing import Optional, List, Tuple, Any, Dict
import random


class MockTCPServer:
    """Mock TCP server for testing SNMP agent functionality."""
    
    def __init__(self):
        self.server_socket = None
        self.port = None
        self.running = False
        self.thread = None
        self.connections = []
        self.received_data = []
        
    def start(self, port: Optional[int] = None) -> int:
        """Start the mock server on specified or random port."""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        if port is None:
            # Find an available port
            self.server_socket.bind(('localhost', 0))
            self.port = self.server_socket.getsockname()[1]
        else:
            self.server_socket.bind(('localhost', port))
            self.port = port
            
        self.server_socket.listen(5)
        self.running = True
        
        # Start accept thread
        self.thread = threading.Thread(target=self._accept_loop)
        self.thread.daemon = True
        self.thread.start()
        
        return self.port
        
    def _accept_loop(self):
        """Accept connections in background thread."""
        while self.running:
            try:
                self.server_socket.settimeout(0.5)
                client_socket, address = self.server_socket.accept()
                self.connections.append((client_socket, address))
            except socket.timeout:
                continue
            except Exception:
                break
                
    def stop(self):
        """Stop the mock server."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1)
        if self.server_socket:
            self.server_socket.close()
        for conn, _ in self.connections:
            conn.close()


class MockTCPClient:
    """Mock TCP client for testing SNMP manager functionality."""
    
    def __init__(self):
        self.socket = None
        self.connected = False
        
    def connect(self, host: str, port: int):
        """Connect to server."""
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect((host, port))
        self.connected = True
        
    def send(self, data: bytes) -> int:
        """Send data to server."""
        if not self.connected:
            raise RuntimeError("Not connected")
        return self.socket.send(data)
        
    def sendall(self, data: bytes):
        """Send all data to server."""
        if not self.connected:
            raise RuntimeError("Not connected")
        self.socket.sendall(data)
        
    def recv(self, size: int) -> bytes:
        """Receive data from server."""
        if not self.connected:
            raise RuntimeError("Not connected")
        return self.socket.recv(size)
        
    def close(self):
        """Close connection."""
        if self.socket:
            self.socket.close()
        self.connected = False


class TestDataGenerator:
    """Generate test data for SNMP protocol testing."""
    
    @staticmethod
    def generate_test_oid() -> str:
        """Generate a random valid OID."""
        components = [1, 3, 6, 1, 2, 1]  # Standard prefix
        # Add random suffix
        for _ in range(random.randint(2, 5)):
            components.append(random.randint(0, 255))
        components.append(0)  # End with .0 for scalar
        return '.'.join(str(c) for c in components)
        
    @staticmethod
    def generate_test_oids(count: int) -> List[str]:
        """Generate multiple test OIDs."""
        return [TestDataGenerator.generate_test_oid() for _ in range(count)]
        
    @staticmethod
    def generate_test_value(value_type: str) -> Any:
        """Generate a test value of specified type."""
        if value_type == 'INTEGER':
            return random.randint(-2147483648, 2147483647)
        elif value_type == 'STRING':
            chars = 'abcdefghijklmnopqrstuvwxyz0123456789'
            length = random.randint(5, 20)
            return ''.join(random.choice(chars) for _ in range(length))
        elif value_type == 'COUNTER':
            return random.randint(0, 4294967295)
        elif value_type == 'TIMETICKS':
            return random.randint(0, 4294967295)
        else:
            return None
            
    @staticmethod
    def generate_test_mib_data() -> Dict[str, Tuple[str, Any]]:
        """Generate test MIB data."""
        mib = {}
        
        # Standard system OIDs
        mib['1.3.6.1.2.1.1.1.0'] = ('STRING', 'Test System Description')
        mib['1.3.6.1.2.1.1.2.0'] = ('OID', '1.3.6.1.4.1.9999')
        mib['1.3.6.1.2.1.1.3.0'] = ('TIMETICKS', 123456)
        mib['1.3.6.1.2.1.1.4.0'] = ('STRING', 'test@example.com')
        mib['1.3.6.1.2.1.1.5.0'] = ('STRING', 'test-host')
        mib['1.3.6.1.2.1.1.6.0'] = ('STRING', 'Test Location')
        mib['1.3.6.1.2.1.1.7.0'] = ('INTEGER', 72)
        
        # Interface OIDs
        mib['1.3.6.1.2.1.2.1.0'] = ('INTEGER', 3)
        mib['1.3.6.1.2.1.2.2.1.1.1'] = ('INTEGER', 1)
        mib['1.3.6.1.2.1.2.2.1.2.1'] = ('STRING', 'eth0')
        mib['1.3.6.1.2.1.2.2.1.3.1'] = ('INTEGER', 6)
        mib['1.3.6.1.2.1.2.2.1.5.1'] = ('COUNTER', 1000000000)
        
        return mib


# MessageBuilder class removed - it exposed protocol implementation details
# Tests should use actual protocol classes or mock data instead