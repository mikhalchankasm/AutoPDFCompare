"""Hover tooltips.

The options have hint labels under them, but the buttons and chips had nothing:
you had to already know what "Строгость" or "⇅" did. A tooltip is the cheapest
way to answer "what is this?" without adding another line of text to the window.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

DELAY_MS = 450
MAX_WIDTH_PX = 320


class Tooltip:
    """Shows `text_fn()` next to the widget while the pointer rests on it.

    The text is a callable, not a string, so a tooltip follows the interface
    language without being rebuilt when the user switches RU/EN.
    """

    def __init__(self, widget: tk.Misc, text_fn: Callable[[], str]) -> None:
        self.widget = widget
        self.text_fn = text_fn
        self._after_id: str | None = None
        self._tip: tk.Toplevel | None = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event: tk.Event | None = None) -> None:
        self._cancel()
        self._after_id = self.widget.after(DELAY_MS, self._show)

    def _cancel(self) -> None:
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None

    def _show(self) -> None:
        if self._tip is not None:
            return
        text = (self.text_fn() or "").strip()
        if not text:
            return
        try:
            x = self.widget.winfo_rootx() + 12
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        except tk.TclError:
            return
        tip = tk.Toplevel(self.widget)
        tip.wm_overrideredirect(True)  # no title bar
        tip.wm_geometry(f"+{x}+{y}")
        tk.Label(
            tip,
            text=text,
            justify="left",
            wraplength=MAX_WIDTH_PX,
            bg="#1f2937",
            fg="#f9fafb",
            padx=8,
            pady=5,
            font=("Segoe UI", 9),
        ).pack()
        self._tip = tip

    def _hide(self, _event: tk.Event | None = None) -> None:
        self._cancel()
        if self._tip is not None:
            try:
                self._tip.destroy()
            except tk.TclError:
                pass
            self._tip = None


def add_tooltip(widget: tk.Misc | None, text_fn: Callable[[], str]) -> None:
    """Attach a tooltip, ignoring widgets that were never built."""
    if widget is not None:
        Tooltip(widget, text_fn)
