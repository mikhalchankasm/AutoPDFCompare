"""SVG icon catalogue for the final HTML report."""

from __future__ import annotations

import html

REPORT_ICON_SVGS = {
    "git-compare": '<path d="M18 8V6a2 2 0 0 0-2-2H6"/><path d="m8 2-3 3 3 3"/><path d="M6 16v2a2 2 0 0 0 2 2h10"/><path d="m16 22 3-3-3-3"/>',
    "file-text": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M16 13H8"/><path d="M16 17H8"/><path d="M10 9H8"/>',
    "alert-circle": '<circle cx="12" cy="12" r="10"/><path d="M12 8v4"/><path d="M12 16h.01"/>',
    "plus-circle": '<circle cx="12" cy="12" r="10"/><path d="M12 8v8"/><path d="M8 12h8"/>',
    "minus-circle": '<circle cx="12" cy="12" r="10"/><path d="M8 12h8"/>',
    "check-circle": '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/>',
    "sliders-horizontal": '<path d="M21 4h-7"/><path d="M10 4H3"/><path d="M21 12h-9"/><path d="M8 12H3"/><path d="M21 20h-5"/><path d="M12 20H3"/><path d="M14 2v4"/><path d="M8 10v4"/><path d="M16 18v4"/>',
    "search": '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    "download": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M7 10l5 5 5-5"/><path d="M12 15V3"/>',
    "arrow-up-right": '<path d="M7 7h10v10"/><path d="M7 17 17 7"/>',
    "arrow-left-right": '<path d="M8 3 4 7l4 4"/><path d="M4 7h16"/><path d="m16 21 4-4-4-4"/><path d="M20 17H4"/>',
    "chevron-left": '<path d="m15 18-6-6 6-6"/>',
    "chevron-right": '<path d="m9 18 6-6-6-6"/>',
    "chevrons-left": '<path d="m11 17-5-5 5-5"/><path d="m18 17-5-5 5-5"/>',
    "chevrons-right": '<path d="m6 17 5-5-5-5"/><path d="m13 17 5-5-5-5"/>',
    "arrow-left": '<path d="m12 19-7-7 7-7"/><path d="M19 12H5"/>',
    "arrow-right": '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
    "external-link": '<path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
    "maximize-2": '<path d="M15 3h6v6"/><path d="m21 3-7 7"/><path d="M9 21H3v-6"/><path d="m3 21 7-7"/>',
    "square": '<rect x="5" y="5" width="14" height="14" rx="2"/>',
    "zoom-in": '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/><path d="M11 8v6"/><path d="M8 11h6"/>',
    "zoom-out": '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/><path d="M8 11h6"/>',
    "square-dashed": '<path d="M5 3a2 2 0 0 0-2 2"/><path d="M19 3a2 2 0 0 1 2 2"/><path d="M21 19a2 2 0 0 1-2 2"/><path d="M5 21a2 2 0 0 1-2-2"/><path d="M9 3h1"/><path d="M14 3h1"/><path d="M21 9v1"/><path d="M21 14v1"/><path d="M15 21h-1"/><path d="M10 21H9"/><path d="M3 15v-1"/><path d="M3 10V9"/>',
    "list": '<path d="M8 6h13"/><path d="M8 12h13"/><path d="M8 18h13"/><path d="M3 6h.01"/><path d="M3 12h.01"/><path d="M3 18h.01"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/>',
    "moon": '<path d="M20.99 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 20.99 12.79z"/>',
    "globe": '<circle cx="12" cy="12" r="10"/><path d="M2 12h20"/><path d="M12 2a15.3 15.3 0 0 1 0 20"/><path d="M12 2a15.3 15.3 0 0 0 0 20"/>',
    "target": '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>',
    "home": '<path d="M3 9.5 12 3l9 6.5V20a1.6 1.6 0 0 1-1.6 1.6H4.6A1.6 1.6 0 0 1 3 20z"/><path d="M9.2 21.4V12h5.6v9.4"/>',
    "help-circle": '<circle cx="12" cy="12" r="10"/><path d="M9.2 9a3 3 0 1 1 5.2 2c-.8.8-1.9 1.4-1.9 2.8"/><path d="M12 17h.01"/>',
    "sparkles": '<path d="M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .963 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 .964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.963 0z"/><path d="M20 3v4"/><path d="M22 5h-4"/><path d="M4 17v2"/><path d="M5 18H3"/>',
}


def report_icon(name: str, cls: str = "ic", size: int = 18) -> str:
    body = REPORT_ICON_SVGS.get(name, "")
    safe_cls = html.escape(cls, quote=True)
    return (
        f'<svg class="{safe_cls}" width="{int(size)}" height="{int(size)}" viewBox="0 0 24 24" '
        f'fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" '
        f'stroke-linejoin="round" aria-hidden="true">{body}</svg>'
    )
