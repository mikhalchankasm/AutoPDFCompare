"""Telling one process from another — shared by the MCP server and its worker.

A PID is not an identity. Windows hands a number out again within seconds of a
process exiting, so "is PID 4242 still alive?" and "is PID 4242 still *the process
I started*?" are different questions, and only the second one may decide whether
something gets killed. The creation time answers it: it is fixed for the life of a
process and has 100 ns resolution.

Nor is the PID that ``subprocess.Popen`` returns necessarily the process you asked
for. In a virtualenv, ``Scripts\\python.exe`` can be a launcher that re-execs the
real interpreter — Popen hands back the launcher's PID while the Python that runs
your script has a different one. So the worker records *itself* (``self_identity``)
and the server reads that, rather than assuming the PID it spawned is the one doing
the work.
"""

from __future__ import annotations

import ctypes
import os
from pathlib import Path
from typing import Any


def process_create_time(pid: int) -> int | None:
    """When this exact process started, or None if it cannot be read."""
    if pid <= 0:
        return None

    if os.name == "nt":
        process_query_limited_information = 0x1000
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(process_query_limited_information, False, int(pid))
        if not handle:
            return None
        try:
            creation = ctypes.c_ulonglong()
            exited = ctypes.c_ulonglong()
            kernel_time = ctypes.c_ulonglong()
            user_time = ctypes.c_ulonglong()
            ok = kernel32.GetProcessTimes(
                handle,
                ctypes.byref(creation),
                ctypes.byref(exited),
                ctypes.byref(kernel_time),
                ctypes.byref(user_time),
            )
            return int(creation.value) if ok else None
        finally:
            kernel32.CloseHandle(handle)

    try:
        raw = (Path("/proc") / str(pid) / "stat").read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    # The command name is field 2 and may itself contain spaces and brackets, so the
    # fields are counted from after its closing one. starttime is field 22.
    fields = raw.rpartition(")")[2].split()
    if len(fields) < 20:
        return None
    try:
        return int(fields[19])
    except ValueError:
        return None


def pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False

    if os.name == "nt":
        process_query_limited_information = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(process_query_limited_information, False, int(pid))
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        # Access denied still means the PID exists; be conservative for cleanup.
        return ctypes.windll.kernel32.GetLastError() == 5

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def self_identity() -> dict[str, Any]:
    """Who I am, for whoever started me — recorded by the worker about itself."""
    pid = os.getpid()
    return {"pid": pid, "create_time": process_create_time(pid)}


def same_process(pid: int, create_time: int | None) -> bool:
    """Is the process behind this PID still the one that had this creation time?

    With no recorded creation time (an older job, or a platform that would not give
    one) this degrades to plain existence — no worse than before, and still never
    the basis for a kill on its own.
    """
    if not pid_exists(pid):
        return False
    if create_time is None:
        return True
    current = process_create_time(pid)
    return current is not None and int(current) == int(create_time)
