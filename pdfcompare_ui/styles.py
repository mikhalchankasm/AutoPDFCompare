"""Color palette and ttk styles for the Tkinter GUI."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

BG_WINDOW = "#ECEBE5"
BG_CARD = "#FFFFFF"
BG_SOFT = "#F5F4EE"
BG_INFO = "#E6F1FB"
TEXT_PRIMARY = "#141413"
TEXT_SECONDARY = "#6E6D68"
TEXT_TERTIARY = "#999791"
BORDER_THIN = "#E0DFDB"
BORDER_STRONG = "#C9C8C2"
ACCENT = "#185FA5"
ACCENT_DARK = "#0C447C"
OLD_DOT = "#E24B4A"
OLD_BORDER = "#B5D4F4"
NEW_DOT = "#639922"
NEW_BORDER = "#C0DD97"
PILL_OK_BG = "#EAF3DE"
PILL_OK_TEXT = "#3B6D11"
PILL_CANCEL_BG = "#F1EFE8"
PILL_CANCEL_TEXT = "#5F5E5A"


def configure_ttk_styles(root: tk.Misc) -> None:
    """Apply the palette above to the ttk widgets used by the app."""
    style = ttk.Style(root)
    style.configure("TFrame", background=BG_WINDOW)
    style.configure("Header.TLabel", font=("Segoe UI", 18, "normal"), foreground=TEXT_PRIMARY, background=BG_WINDOW)
    style.configure("SubHeader.TLabel", font=("Segoe UI", 10), foreground=TEXT_SECONDARY, background=BG_WINDOW)
    style.configure("Hint.TLabel", font=("Segoe UI", 9), foreground=TEXT_TERTIARY, background=BG_WINDOW)
    style.configure("FileLabel.TLabel", font=("Segoe UI", 10, "bold"), foreground=TEXT_PRIMARY, background=BG_CARD)
    style.configure("Red.TLabel", font=("Segoe UI", 10, "bold"), foreground=OLD_DOT, background=BG_CARD)
    style.configure("Green.TLabel", font=("Segoe UI", 10, "bold"), foreground=NEW_DOT, background=BG_CARD)
    style.configure("Primary.TButton", font=("Segoe UI", 11, "bold"), foreground=BG_CARD, background=ACCENT, padding=(12, 8))
    style.configure("Small.TButton", font=("Segoe UI", 9), padding=(10, 5))
    style.configure("Pill.TLabel", font=("Segoe UI", 9, "bold"))
    style.configure("Path.TEntry", fieldbackground=BG_SOFT, borderwidth=0)
    style.configure("Horizontal.TProgressbar", troughcolor=BG_INFO, background=ACCENT, borderwidth=0)
    style.configure("TNotebook", background=BG_WINDOW, borderwidth=0)
    style.configure(
        "TNotebook.Tab",
        padding=(14, 8),
        font=("Segoe UI", 10),
        background=BG_WINDOW,
        foreground=TEXT_SECONDARY,
        borderwidth=0,
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", BG_WINDOW)],
        foreground=[("selected", TEXT_PRIMARY)],
        font=[("selected", ("Segoe UI", 10, "bold"))],
    )
    style.configure(
        "History.Treeview",
        background=BG_CARD,
        fieldbackground=BG_CARD,
        foreground=TEXT_PRIMARY,
        rowheight=44,
        borderwidth=0,
        font=("Segoe UI", 10),
    )
    style.configure(
        "History.Treeview.Heading",
        background=BG_WINDOW,
        foreground=TEXT_SECONDARY,
        font=("Segoe UI", 9),
        relief="flat",
        borderwidth=0,
    )
    style.map("History.Treeview", background=[("selected", BG_INFO)], foreground=[("selected", TEXT_PRIMARY)])
