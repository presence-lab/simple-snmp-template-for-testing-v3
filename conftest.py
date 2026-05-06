"""Root conftest for the SNMP project.

Registers tests/snmp_fixtures.py as a pytest plugin so that SNMP-specific
fixtures are discoverable without modifying tests/conftest.py (which is
integrity-verified by tools/INTEGRITY_HASHES.txt and tools/verify_integrity.py).
"""

pytest_plugins = ("tests.snmp_fixtures",)
