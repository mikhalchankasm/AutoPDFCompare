"""HTML fragment builders for the report: localized text and page badges.

These used to be ~25 closures inside ``generate_html_report``, which is why that
function was unreadable. They only ever depended on the report language (and, for
the precision badge, the run's base DPI), so they live here as two small objects
the generator binds once.

Every method returns an HTML string that is already escaped.
"""

from __future__ import annotations

import html

from .classification import level_to_report_tags
from .constants import FG_MINOR_PERCENT, FG_MODERATE_PERCENT
from .html_i18n import HTML_REPORT_I18N

STATUS_LABEL_KEYS = {
    "CHANGED": "status_col_changed",
    "UNCHANGED": "status_col_unchanged",
    "ADDED": "status_col_added",
    "REMOVED": "status_col_removed",
}
LEVEL_LABEL_KEYS = {
    "MAJOR": "level_major",
    "MODERATE": "level_moderate",
    "MINOR": "level_minor",
    "UNCHANGED": "level_unchanged",
}
STATUS_BADGE_CLASSES = {
    "CHANGED": "st-changed",
    "UNCHANGED": "st-unchanged",
    "ADDED": "st-added",
    "REMOVED": "st-removed",
}
LEVEL_BADGE_CLASSES = {
    "MAJOR": "lv-major",
    "MODERATE": "lv-moderate",
    "MINOR": "lv-minor",
    "UNCHANGED": "lv-unchanged",
}


class ReportI18n:
    """Localized text for the report.

    The report ships both languages in the markup (``data-i18n-ru`` /
    ``data-i18n-en``) so the reader can switch language in the browser without
    regenerating anything; ``lang`` only decides which one is rendered as the
    visible text.
    """

    def __init__(self, report_lang: str = "ru") -> None:
        self.lang = "en" if str(report_lang).lower().startswith("en") else "ru"
        self.all = HTML_REPORT_I18N
        self.t = HTML_REPORT_I18N[self.lang]

    def tr_attr(self, key: str) -> str:
        return html.escape(str(self.t.get(key, key)), quote=True)

    def i18n_span(self, key: str, cls: str | None = None) -> str:
        ru = html.escape(str(self.all["ru"].get(key, key)), quote=True)
        en = html.escape(str(self.all["en"].get(key, key)), quote=True)
        text = html.escape(str(self.t.get(key, key)))
        cls_attr = f' class="{html.escape(cls, quote=True)}"' if cls else ""
        return f'<span{cls_attr} data-i18n-ru="{ru}" data-i18n-en="{en}">{text}</span>'

    def i18n_span_text(self, ru_text: str, en_text: str, cls: str | None = None) -> str:
        ru_attr = html.escape(ru_text, quote=True)
        en_attr = html.escape(en_text, quote=True)
        text = html.escape(en_text if self.lang == "en" else ru_text)
        cls_attr = f' class="{html.escape(cls, quote=True)}"' if cls else ""
        return f'<span{cls_attr} data-i18n-ru="{ru_attr}" data-i18n-en="{en_attr}">{text}</span>'

    def i18n_aria(self, ru_text: str, en_text: str, attr_name: str = "aria-label") -> str:
        ru_attr = html.escape(ru_text, quote=True)
        en_attr = html.escape(en_text, quote=True)
        current = html.escape(en_text if self.lang == "en" else ru_text, quote=True)
        return f'{attr_name}="{current}" data-i18n-aria-ru="{ru_attr}" data-i18n-aria-en="{en_attr}"'

    def i18n_attr(self, key: str, attr_name: str) -> str:
        ru = html.escape(str(self.all["ru"].get(key, key)), quote=True)
        en = html.escape(str(self.all["en"].get(key, key)), quote=True)
        return f'data-i18n-{attr_name}-ru="{ru}" data-i18n-{attr_name}-en="{en}"'

    def i18n_placeholder_text(self, ru_text: str, en_text: str) -> str:
        current = html.escape(en_text if self.lang == "en" else ru_text, quote=True)
        return (
            f'placeholder="{current}" data-i18n-placeholder-ru="{html.escape(ru_text, quote=True)}" '
            f'data-i18n-placeholder-en="{html.escape(en_text, quote=True)}"'
        )

    def title_attrs(self, ru_text: str, en_text: str) -> str:
        return f'data-title-ru="{html.escape(ru_text, quote=True)}" data-title-en="{html.escape(en_text, quote=True)}"'

    def title_text(self, ru_text: str, en_text: str) -> str:
        return html.escape(en_text if self.lang == "en" else ru_text)

    def format_duration_pair(self, seconds: float | None) -> tuple[str, str]:
        if seconds is None or seconds < 0:
            return "-", "-"
        total = int(round(seconds))
        minutes, secs = divmod(total, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours}ч {minutes:02d}м {secs:02d}с", f"{hours}h {minutes:02d}m {secs:02d}s"
        if minutes:
            return f"{minutes}м {secs:02d}с", f"{minutes}m {secs:02d}s"
        return f"{secs}с", f"{secs}s"


class ReportBadges:
    """Status/level badges, meters and preview tiles for a page row."""

    def __init__(self, i18n: ReportI18n, high_dpi: int) -> None:
        self.i18n = i18n
        self.high_dpi = high_dpi

    def report_tags_for_page(self, page: dict) -> tuple[str, str]:
        status_raw = str(page.get("status_raw") or "")
        if status_raw == "ADDED":
            return "ADDED", ""
        elif status_raw == "REMOVED":
            return "REMOVED", ""
        return level_to_report_tags(page.get("change_level"))

    def status_badge_html(self, status_tag: str) -> str:
        cls = STATUS_BADGE_CLASSES.get(status_tag, "st-changed")
        key = STATUS_LABEL_KEYS.get(status_tag)
        label = self.i18n.i18n_span(key) if key else html.escape(status_tag)
        return f'<span class="badge {cls}">{label}</span>'

    def level_badge_html(self, level_tag: str) -> str:
        if not level_tag:
            return "—"
        cls = LEVEL_BADGE_CLASSES.get(level_tag, "lv-major")
        key = LEVEL_LABEL_KEYS.get(level_tag)
        label = self.i18n.i18n_span(key) if key else html.escape(level_tag)
        return f'<span class="badge {cls}">{label}</span>'

    def is_mixed_precision_page(self, page: dict) -> bool:
        return bool((page.get("page_settings") or {}).get("mixed_settings"))

    def page_precision_text(self, page: dict) -> tuple[str, str]:
        settings = page.get("page_settings") or {}
        mixed = settings.get("mixed_settings") or {}
        dpi = settings.get("high_dpi") or mixed.get("dpi") or self.high_dpi
        tol = settings.get("stroke_tol_px") if settings.get("stroke_tol_px") is not None else mixed.get("stroke_tol_px")
        strictness = settings.get("diff_strictness") or mixed.get("diff_strictness") or "-"
        merge_gap = settings.get("bbox_merge_gap_mm")
        if merge_gap is None:
            merge_gap = mixed.get("bbox_merge_gap_mm")
        try:
            merge_gap_num = float(merge_gap or 0.0)
        except (TypeError, ValueError):
            merge_gap_num = 0.0
        tol_txt = "-" if tol is None else f"{float(tol):g}px"
        merge_ru = "merge выкл." if merge_gap_num <= 0 else f"merge {merge_gap_num:g} мм"
        merge_en = "merge off" if merge_gap_num <= 0 else f"merge {merge_gap_num:g} mm"
        return (
            f"DPI {dpi} · {strictness} · tol {tol_txt} · {merge_ru}",
            f"DPI {dpi} · {strictness} · tol {tol_txt} · {merge_en}",
        )

    def precision_badge_html(self, page: dict) -> str:
        if not self.is_mixed_precision_page(page):
            return ""
        ru_text, en_text = self.page_precision_text(page)
        title = self.i18n.title_text(ru_text, en_text)
        return (
            f'<span class="badge precision-badge" title="{html.escape(title, quote=True)}">'
            f'{self.i18n.i18n_span_text("Пересчитан", "Custom precision")}</span>'
        )

    def heat_class(self, fg: float | None) -> str:
        if fg is None or fg < FG_MINOR_PERCENT:
            return "heat-ok"
        if fg < FG_MODERATE_PERCENT:
            return "heat-warn"
        return "heat-bad"

    def fg_meter_html(self, fg: float | None, sparse: bool = False) -> str:
        if fg is None:
            return '<span class="faint">—</span>'
        if sparse:
            return '<span class="faint">—</span>'
        # Scale: 20% FG saturates the bar (20 * 5 = 100).
        width = fg * 5.0
        return (
            '<div class="diff-wrap">'
            '<div class="diff-bar">'
            f'<div class="diff-fill {self.heat_class(fg)}" style="width:clamp(2%, {width:.3f}%, 100%);"></div>'
            "</div>"
            f'<span class="diff-num">{fg:.2f}%</span>'
            "</div>"
        )

    def metric_percent_html(self, value: float | None) -> str:
        if value is None:
            return '<span class="faint">—</span>'
        return f'<span class="diff-num">{float(value):.2f}%</span>'

    def metric_area_html(self, value: float | None) -> str:
        if value is None:
            return '<span class="faint">—</span>'
        return f'<span class="diff-num">{float(value):.1f}</span>'

    def preview_tile(self, src: str | None, label: str, alt: str) -> str:
        label_html = self.i18n.i18n_span_text(label, label, "pv-label")
        if src:
            media = f'<img loading="lazy" src="{html.escape(src, quote=True)}" alt="{html.escape(alt, quote=True)}"/>'
        else:
            media = '<div class="ph">—</div>'
        return f'<div class="pv-tile">{label_html}{media}</div>'
