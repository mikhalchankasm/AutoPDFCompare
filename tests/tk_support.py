"""One Tk interpreter for the whole test session.

Creating and destroying `tk.Tk()` several times inside one process leaves Tcl
unable to find its own `init.tcl` on this platform. The GUI tests then fail in the
worst possible way: one of them *skips* with "no Tk display" while the rest still
run, so the golden widget-tree snapshot silently stops guarding anything — and
occasionally a half-initialised interpreter yields a different tree twice in a row
and the determinism check fails instead.

So the session gets exactly one root. It is created on first use, hidden, and never
destroyed; the process exit tears it down. Tests that need a fresh window build it
as a `Toplevel` of that root.
"""

from __future__ import annotations

import tkinter as tk

import pytest

_ROOT: tk.Tk | None = None


def shared_root() -> tk.Tk:
    """The session's Tk root — hidden, reused, never torn down."""
    global _ROOT
    if _ROOT is None:
        try:
            root = tk.Tk()
        except tk.TclError as exc:  # pragma: no cover - depends on the runner
            pytest.skip(f"no Tk display: {exc}")
        root.withdraw()
        _ROOT = root
    return _ROOT


def hidden_toplevel() -> tk.Toplevel:
    """An unmapped window to build a screen into — a test must not flash on screen."""
    top = tk.Toplevel(shared_root())
    top.withdraw()
    return top
