"""Cross-platform process management primitives used by the watchdog."""
from __future__ import annotations

import os
import subprocess
import sys


def is_process_alive(pid: int) -> bool:
    """True if a process with this pid is still running.

    Does not require psutil. Uses os.kill(pid, 0) on Unix and
    OpenProcess/GetExitCodeProcess on Windows.
    """
    if sys.platform == "win32":
        import ctypes
        # PROCESS_QUERY_LIMITED_INFORMATION lets us call GetExitCodeProcess
        # without demanding SYNCHRONIZE rights (which WaitForSingleObject
        # would need). GetExitCodeProcess returns STILL_ACTIVE (259) while
        # the process runs and the real exit code once it's exited.
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        kernel32 = ctypes.windll.kernel32
        kernel32.OpenProcess.argtypes = [
            ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong,
        ]
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.GetExitCodeProcess.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong),
        ]
        kernel32.GetExitCodeProcess.restype = ctypes.c_int
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]

        handle = kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid
        )
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
            if not ok:
                return False
            return exit_code.value == STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    else:
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True  # exists but we can't signal it


def terminate_process(pid: int, timeout: float = 5.0) -> bool:
    """Attempt to terminate. Returns True if the process is gone afterwards."""
    import time
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            capture_output=True,
        )
    else:
        import signal
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            return True
        # Grace period, then SIGKILL
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not is_process_alive(pid):
                return True
            time.sleep(0.2)
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            return True
    # Verify
    time.sleep(0.5)
    return not is_process_alive(pid)
