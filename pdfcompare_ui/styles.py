"""Color palette, ttk styles and the section header used across the GUI.

The window used to be three shades of the same warm grey — window `#ECEBE5`,
panel `#F5F4EE`, card `#FFFFFF` — with grey headings in the same weight as the
hints under them. Nothing read as a *zone*: the eye had no edges to land on and
no hierarchy to follow. The palette below keeps the warm grey and the blue
accent, but pulls the values apart so the parts of the window separate:

- the window is darker, so a white card is genuinely a card;
- every section starts with a bold title and an accent bar, so a zone begins
  somewhere visible;
- secondary and tertiary text got darker — `#999791` on a light panel was barely
  legible, which is not "quiet", it is unreadable;
- the state of a control is filled, not hinted: the chosen strictness chip is
  solid accent, not a slightly thicker border.

The ttk theme is `clam`, chosen deliberately: the native Windows theme draws tabs
and buttons from OS bitmaps and ignores most `configure()` calls, so an app that
wants its own look cannot have one on top of it.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

# --- surfaces ---
BG_WINDOW = "#E3E1D9"  # deeper than the cards on purpose: it is what makes them cards
BG_CARD = "#FFFFFF"
BG_SOFT = "#F4F3ED"
BG_INFO = "#DEEAF7"
BG_ACCENT_SOFT = "#E7F0FA"

# --- text ---
TEXT_PRIMARY = "#141413"
TEXT_SECONDARY = "#57564F"
TEXT_TERTIARY = "#7B7971"
TEXT_ON_ACCENT = "#FFFFFF"

# --- lines ---
BORDER_THIN = "#D4D2CA"
BORDER_STRONG = "#B3B1A8"
BORDER_CARD = "#C8C6BD"

# --- accent ---
ACCENT = "#175FA5"
ACCENT_DARK = "#0C447C"
ACCENT_LIGHT = "#5B93CC"
# The rail a slider handle runs on: dark enough that a white handle is obvious.
SLIDER_TRACK = "#A7C3DF"

# --- semantic ---
OLD_DOT = "#D93A38"
OLD_BORDER = "#E8A9A8"
NEW_DOT = "#4E8A15"
NEW_BORDER = "#A9CE7C"
# These tint a whole history row, so they have to stay a whisper: the signal is the
# bold coloured word in the Result column, not a wall of green behind 40 rows.
PILL_OK_BG = "#F3F8EC"
PILL_OK_TEXT = "#33610C"
PILL_CANCEL_BG = "#F2F0E9"
PILL_CANCEL_TEXT = "#57564F"

SECTION_BAR_PX = 4
FONT = "Segoe UI"


def configure_ttk_styles(root: tk.Misc) -> None:
    """Apply the palette above to the ttk widgets used by the app."""
    style = ttk.Style(root)
    # Without clam, the Windows theme draws tabs/buttons from bitmaps and silently
    # drops the colors below — the app would keep the flat OS look it is trying to
    # get away from.
    try:
        style.theme_use("clam")
    except tk.TclError:  # pragma: no cover - clam ships with Tk everywhere we run
        pass

    style.configure("TFrame", background=BG_WINDOW)
    style.configure("TLabel", background=BG_WINDOW, foreground=TEXT_PRIMARY, font=(FONT, 10))

    style.configure("Header.TLabel", font=(FONT, 20, "bold"), foreground=TEXT_PRIMARY, background=BG_WINDOW)
    style.configure("SubHeader.TLabel", font=(FONT, 10), foreground=TEXT_SECONDARY, background=BG_WINDOW)
    style.configure("Hint.TLabel", font=(FONT, 9), foreground=TEXT_TERTIARY, background=BG_WINDOW)

    # A section title: bold, upper case, and paired with the accent bar below.
    style.configure("Section.TLabel", font=(FONT, 10, "bold"), foreground=TEXT_PRIMARY, background=BG_WINDOW)
    # A card title: same idea, one step smaller, sitting on white.
    style.configure("CardTitle.TLabel", font=(FONT, 9, "bold"), foreground=TEXT_SECONDARY, background=BG_CARD)
    style.configure("FieldLabel.TLabel", font=(FONT, 9, "bold"), foreground=TEXT_SECONDARY, background=BG_CARD)
    # The number a slider is currently at — the one thing on the row worth reading.
    style.configure("Value.TLabel", font=(FONT, 12, "bold"), foreground=ACCENT, background=BG_CARD)

    style.configure("FileLabel.TLabel", font=(FONT, 10, "bold"), foreground=TEXT_PRIMARY, background=BG_CARD)
    style.configure("Red.TLabel", font=(FONT, 9, "bold"), foreground=OLD_DOT, background=BG_CARD)
    style.configure("Green.TLabel", font=(FONT, 9, "bold"), foreground=NEW_DOT, background=BG_CARD)
    style.configure("Pill.TLabel", font=(FONT, 9, "bold"))

    style.configure(
        "Primary.TButton", font=(FONT, 11, "bold"), foreground=TEXT_ON_ACCENT, background=ACCENT, padding=(12, 8)
    )
    style.configure(
        "Small.TButton",
        font=(FONT, 9, "bold"),
        foreground=TEXT_PRIMARY,
        background=BG_CARD,
        bordercolor=BORDER_STRONG,
        lightcolor=BG_CARD,
        darkcolor=BG_CARD,
        borderwidth=1,
        focusthickness=0,
        padding=(11, 6),
    )
    style.map(
        "Small.TButton",
        background=[("pressed", BG_ACCENT_SOFT), ("active", BG_ACCENT_SOFT), ("disabled", BG_SOFT)],
        foreground=[("active", ACCENT_DARK), ("disabled", TEXT_TERTIARY)],
        bordercolor=[("active", ACCENT_LIGHT)],
    )

    # The zone picker builds its format/orientation/anchor/unit switches out of
    # Toolbutton radiobuttons. Under clam their "selected" look is a faint border —
    # you cannot tell which sheet format you are on. Fill it, like every other
    # toggle in the app.
    style.configure(
        "Toolbutton",
        font=(FONT, 9),
        background=BG_CARD,
        foreground=TEXT_SECONDARY,
        bordercolor=BORDER_STRONG,
        lightcolor=BG_CARD,
        darkcolor=BG_CARD,
        borderwidth=1,
        focusthickness=0,
        padding=(8, 5),
        anchor="center",
    )
    style.map(
        "Toolbutton",
        background=[("selected", ACCENT), ("active", BG_ACCENT_SOFT)],
        foreground=[("selected", TEXT_ON_ACCENT), ("active", ACCENT_DARK)],
        bordercolor=[("selected", ACCENT)],
        lightcolor=[("selected", ACCENT)],
        darkcolor=[("selected", ACCENT)],
        font=[("selected", (FONT, 9, "bold"))],
    )

    style.configure(
        "Path.TEntry",
        fieldbackground=BG_CARD,
        background=BG_CARD,
        foreground=TEXT_PRIMARY,
        bordercolor=BORDER_STRONG,
        lightcolor=BORDER_STRONG,
        darkcolor=BORDER_STRONG,
        borderwidth=1,
        padding=(8, 4),
    )
    style.map("Path.TEntry", bordercolor=[("focus", ACCENT)], lightcolor=[("focus", ACCENT)])

    style.configure(
        "TCheckbutton",
        background=BG_CARD,
        foreground=TEXT_PRIMARY,
        font=(FONT, 9),
        focuscolor=BG_CARD,
        indicatorcolor=BG_CARD,
        bordercolor=BORDER_STRONG,
    )
    style.map(
        "TCheckbutton",
        background=[("active", BG_CARD)],
        indicatorcolor=[("selected", ACCENT), ("pressed", ACCENT_DARK)],
        foreground=[("disabled", TEXT_TERTIARY)],
    )

    style.configure(
        "Horizontal.TProgressbar",
        troughcolor=BG_CARD,
        background=ACCENT,
        bordercolor=BORDER_THIN,
        lightcolor=ACCENT,
        darkcolor=ACCENT,
        borderwidth=0,
        thickness=8,
    )

    style.configure("TNotebook", background=BG_WINDOW, borderwidth=0, tabmargins=(0, 4, 0, 0))
    style.configure(
        "TNotebook.Tab",
        padding=(18, 9),
        font=(FONT, 10),
        background=BG_WINDOW,
        foreground=TEXT_SECONDARY,
        bordercolor=BG_WINDOW,
        lightcolor=BG_WINDOW,
        darkcolor=BG_WINDOW,
        borderwidth=0,
    )
    # The active tab is filled and bold, not merely bold: on a flat toolbar a font
    # weight alone is not an obvious enough "you are here".
    style.map(
        "TNotebook.Tab",
        background=[("selected", BG_ACCENT_SOFT), ("active", BG_SOFT)],
        foreground=[("selected", ACCENT_DARK), ("active", TEXT_PRIMARY)],
        font=[("selected", (FONT, 10, "bold"))],
        lightcolor=[("selected", BG_ACCENT_SOFT)],
    )

    style.configure(
        "History.Treeview",
        background=BG_CARD,
        fieldbackground=BG_CARD,
        foreground=TEXT_PRIMARY,
        rowheight=44,
        borderwidth=0,
        font=(FONT, 10),
    )
    style.configure(
        "History.Treeview.Heading",
        background=BG_SOFT,
        foreground=TEXT_SECONDARY,
        font=(FONT, 9, "bold"),
        relief="flat",
        borderwidth=0,
        padding=(8, 6),
    )
    style.map(
        "History.Treeview",
        background=[("selected", BG_ACCENT_SOFT)],
        foreground=[("selected", ACCENT_DARK)],
    )
    style.map("History.Treeview.Heading", background=[("active", BG_SOFT)])


def section_header(
    parent: tk.Misc,
    text: str,
    *,
    bg: str = BG_WINDOW,
    style_name: str = "Section.TLabel",
) -> tuple[tk.Frame, ttk.Label]:
    """A zone starts here: an accent bar, then a bold title.

    Returns the row and the title label — the label so the caller can keep it and
    re-translate it when the language changes.
    """
    row = tk.Frame(parent, bg=bg)
    bar = tk.Frame(row, bg=ACCENT, width=SECTION_BAR_PX)
    bar.pack(side=tk.LEFT, fill=tk.Y)
    label = ttk.Label(row, text=text, style=style_name, background=bg)
    label.pack(side=tk.LEFT, padx=(8, 0))
    return row, label


def card(parent: tk.Misc | None, *, bg: str = BG_CARD, border: str = BORDER_CARD, pad: int = 14) -> tk.Frame:
    """A white surface with a border you can actually see."""
    return tk.Frame(parent, bg=bg, padx=pad, pady=pad, highlightthickness=1, highlightbackground=border)
