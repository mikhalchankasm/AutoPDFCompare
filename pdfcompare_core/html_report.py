"""Final HTML report builder (dashboard, slider views, detail pages)."""

from __future__ import annotations

import html
import json
import os
import shutil
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import fitz


from .classification import status_and_confidence
from .constants import (
    PAGE_INFO_THUMB_DPI,
    START_REPORT_FILE,
    UNCHANGED_DIFF_PERCENT,
)
from .pdf_io import (
    copy_thumb,
    find_pages_dir,
    internal_dir,
    page_map_csv_path,
    report_dir,
    write_start_page,
)



from .html_css import CSS_CMP, CSS_INDEX, CSS_VIEW, REPORT_CSS_TOKENS
from .html_fragments import (
    LEVEL_LABEL_KEYS,
    STATUS_LABEL_KEYS,
    ReportBadges,
    ReportI18n,
)
from .html_icons import report_icon


def _prepare_pages_records(
    details: Sequence[dict],
    file_a: Path,
    file_b: Path,
    pages_root: Path,
    bundle_dir: Path,
    thumbs_dir: Path,
    t: dict[str, str],
    progress_cb: Callable[[int, int], None] | None = None,
) -> list[dict]:
    """Copy thumbnails and assemble the per-page display records.

    progress_cb(done, total) is called once per processed row, so the caller
    can map row indices into its global progress percent space.
    """
    pages_records: list[dict] = []
    total_details = max(1, len(details))
    for row_idx, row in enumerate(details, start=1):
        seq = int(row["seq"])
        a_page = row.get("a_page")
        b_page = row.get("b_page")
        pair_name = row.get("pair_dir", f"{seq:03d}__A_{a_page or 'NA'}__B_{b_page or 'NA'}")
        pair_abs = pages_root / pair_name
        pair_rel = Path(os.path.relpath(pair_abs, bundle_dir))

        old_img = pair_rel / "a.png"
        new_img = pair_rel / "b.png"
        diff_img = pair_rel / "overlay.png"
        if not (pair_abs / "a.png").exists():
            old_img = pair_rel / "a_preview.png"
        if not (pair_abs / "b.png").exists():
            new_img = pair_rel / "b_preview.png"
        if not (pair_abs / "overlay.png").exists():
            diff_img = Path()

        thumb_old = Path("assets") / "thumbs" / f"{seq:03d}_old.jpg"
        thumb_new = Path("assets") / "thumbs" / f"{seq:03d}_new.jpg"
        thumb_diff = Path("assets") / "thumbs" / f"{seq:03d}_diff.jpg"
        old_src = pair_abs / old_img.name if old_img and old_img.name else None
        new_src = pair_abs / new_img.name if new_img and new_img.name else None
        diff_src = pair_abs / diff_img.name if diff_img and diff_img.name else None
        old_preview_src = pair_abs / "a_preview.png"
        new_preview_src = pair_abs / "b_preview.png"
        old_thumb_src = old_preview_src if old_preview_src.is_file() else old_src
        new_thumb_src = new_preview_src if new_preview_src.is_file() else new_src
        copy_thumb(old_thumb_src if old_thumb_src and old_thumb_src.is_file() else None, thumbs_dir / thumb_old.name)
        copy_thumb(new_thumb_src if new_thumb_src and new_thumb_src.is_file() else None, thumbs_dir / thumb_new.name)
        copy_thumb(diff_src if diff_src and diff_src.is_file() else None, thumbs_dir / thumb_diff.name)

        status, conf, content_status, moved = status_and_confidence(row)
        if row["status"] == "added":
            status_simple = "NEW"
            status_ru = t["status_new_sheet"]
            note = t["note_new_only"]
        elif row["status"] == "removed":
            status_simple = "CHANGED"
            status_ru = t["status_changed_short"]
            note = t["note_removed_in_b"]
        elif content_status == "UNCHANGED":
            status_simple = "UNCHANGED"
            status_ru = t["status_unchanged_short"]
            note = t["note_no_significant"]
        else:
            status_simple = "CHANGED"
            status_ru = t["status_changed_short"]
            fg = row.get("diff_foreground_percent")
            area = row.get("diff_area_mm2")
            n_zones = row.get("bboxes_count")
            max_region = row.get("max_region_area_mm2")
            sparse = bool(row.get("foreground_sparse") or False)
            if sparse or fg is None:
                note = t["note_visual_changes_sparse"].format(
                    area=float(area or 0),
                    n=int(n_zones or 0),
                    max=float(max_region or 0),
                )
            else:
                note = t["note_visual_changes"].format(
                    fg=float(fg),
                    area=float(area or 0),
                    n=int(n_zones or 0),
                    max=float(max_region or 0),
                )
        if row.get("ecc_failed"):
            note = f"{note} {t['note_ecc_failed']}"

        a_label = "-" if a_page is None else str(a_page)
        b_label = "-" if b_page is None else str(b_page)
        nav_label = f"({file_a.name} {t['nav_sheet_word']} {a_label}) - ({file_b.name} {t['nav_sheet_word']} {b_label})"
        pages_records.append(
            {
                "seq": seq,
                "b_index": b_page,
                "a_index": a_page,
                "status_raw": status,
                "status": status_simple,
                "status_ru": status_ru,
                "content_status": content_status,
                "match_confidence": conf,
                "moved": moved,
                "diff_metric": row.get("diff_percent"),
                "diff_area_px": row.get("diff_area_px"),
                "diff_area_mm2": row.get("diff_area_mm2"),
                "diff_foreground_metric": row.get("diff_foreground_percent"),
                "foreground_sparse": bool(row.get("foreground_sparse") or False),
                "added_area_mm2": row.get("added_area_mm2"),
                "removed_area_mm2": row.get("removed_area_mm2"),
                "max_region_area_mm2": row.get("max_region_area_mm2"),
                "change_level": row.get("change_level"),
                "bboxes_count": row.get("bboxes_count"),
                "page_settings": {
                    "high_dpi": row.get("high_dpi"),
                    "stroke_tol_px": row.get("stroke_tol_px"),
                    "diff_strictness": row.get("diff_strictness"),
                    "bbox_merge_gap_mm": row.get("bbox_merge_gap_mm"),
                    "bbox_merge_max_area_ratio": row.get("bbox_merge_max_area_ratio"),
                    "mixed_settings": row.get("mixed_settings"),
                },
                "score": row.get("score"),
                "notes": note,
                "nav_label": nav_label,
                "view_file": f"{seq:03d}.html",
                "assets": {
                    "thumb_old": str(thumb_old).replace("\\", "/") if (thumbs_dir / thumb_old.name).exists() else None,
                    "thumb_new": str(thumb_new).replace("\\", "/") if (thumbs_dir / thumb_new.name).exists() else None,
                    "thumb_diff": str(thumb_diff).replace("\\", "/") if (thumbs_dir / thumb_diff.name).exists() else None,
                    "hires_old": str(old_img).replace("\\", "/") if old_img and (pair_abs / old_img.name).exists() else None,
                    "hires_new": str(new_img).replace("\\", "/") if new_img and (pair_abs / new_img.name).exists() else None,
                    "hires_diff": str(diff_img).replace("\\", "/") if diff_img and (pair_abs / diff_img.name).exists() else None,
                },
            }
        )
        if progress_cb is not None:
            progress_cb(row_idx, total_details)
    return pages_records



NAV_DATA_FILE = "nav-data.js"


def _build_nav_data(ctx: _ReportContext) -> dict:
    """The sheet list every page navigates by — built once, for all of them.

    It used to be built per page and inlined into each one: the detail nav was
    pasted into all N detail pages, and every slider re-walked all N sheets to
    emit its own copy of the drawer *and* a JSON copy of the same list beside it.
    That is O(N²) bytes and O(N²) work — at 1000 sheets, ~2 GB of HTML and half a
    minute of generation, most of it the same list over and over.

    Now it is one file the pages load. It stays a plain ``.js`` assigning a global,
    not JSON fetched at runtime: the report has to open from the file system, with
    no server, and `fetch()` of a local file is blocked by the browser's origin
    rules. A `<script src>` is not.
    """
    strings, badges = ctx.strings, ctx.badges
    i18n = strings.all
    status_label_keys = STATUS_LABEL_KEYS

    pages: list[dict] = []
    for p in ctx.pages_records:
        nav_a = "—" if p["a_index"] is None else f"A{p['a_index']}"
        nav_b = "—" if p["b_index"] is None else f"B{p['b_index']}"
        nav_diff = "—" if p["diff_metric"] is None else f'{p["diff_metric"]:.3f}%'
        nav_fg = "—" if p.get("diff_foreground_metric") is None else f'{float(p["diff_foreground_metric"]):.2f}%'
        nav_boxes = "—" if p["bboxes_count"] is None else str(p["bboxes_count"])
        has_slider = bool(p.get("slider_file"))
        status_tag = str(p.get("_status_tag") or "CHANGED")
        level_tag = str(p.get("_level_tag") or "")
        status_key = status_label_keys.get(status_tag, "")

        pages.append(
            {
                # The slider drawer highlights the current sheet by view order.
                "seq": p["view_ord"],
                "label": f"{nav_a} -> {nav_b}",
                "status": status_tag,
                "statusRu": str(i18n["ru"].get(status_key, status_tag)),
                "statusEn": str(i18n["en"].get(status_key, status_tag)),
                "level": level_tag,
                "hasSlider": has_slider,
                "href": str(p["slider_file"] if has_slider else p["view_file"]),
                "diff": nav_diff,
                "boxes": nav_boxes,
                "metaRu": (
                    "Слайдер недоступен · открыть страницу листа"
                    if not has_slider
                    else f"заполнено {nav_fg} · {nav_boxes} областей"
                ),
                "metaEn": (
                    "Slider unavailable · open sheet page"
                    if not has_slider
                    else f"drawn {nav_fg} · {nav_boxes} boxes"
                ),
                "titleRu": (
                    "Слайдер недоступен для добавленных/удалённых листов" if not has_slider else p["nav_label"]
                ),
                "titleEn": ("Slider not available for added/removed sheets" if not has_slider else p["nav_label"]),
                "ariaRu": (
                    "Слайдер недоступен для добавленных/удалённых листов"
                    if not has_slider
                    else "Открыть лист в слайдере"
                ),
                "ariaEn": (
                    "Slider not available for added/removed sheets" if not has_slider else "Open sheet in slider"
                ),
                "search": (
                    f"{p['view_ord']} {nav_a} {nav_b} {p['status_ru']} {status_tag} "
                    f"{level_tag} {nav_fg} {nav_diff} {nav_boxes} {p['notes']}"
                ).lower(),
                # The detail-page sidebar lists sheets by their report row number.
                "viewFile": str(p["view_file"]),
                "navShort": f"{p['seq']} · {nav_a} -> {nav_b}",
                "navLabel": str(p["nav_label"]),
                "navSearch": (
                    f"{p['seq']} · {nav_a} -> {nav_b} {p['nav_label']} {p['status_ru']} {status_tag} "
                    f"{level_tag} {p['b_index'] or ''} {p['a_index'] or ''}"
                ).lower(),
            }
        )

    # Only a handful of distinct badges exist, so they are rendered once here
    # instead of once per sheet per page.
    badge_html = {
        tag: badges.status_badge_html(tag) for tag in sorted({str(p["status"]) for p in pages} | {"CHANGED"})
    }
    return {
        "badges": badge_html,
        "navOkIcon": report_icon("check-circle", "ic nav-ok", 16),
        "pages": pages,
    }


def _write_nav_data(ctx: _ReportContext) -> None:
    payload = json.dumps(_build_nav_data(ctx), ensure_ascii=False, separators=(",", ":"))
    (ctx.bundle_dir / NAV_DATA_FILE).write_text(f"window.PDFCOMPARE_NAV={payload};\n", encoding="utf-8")


@dataclass
class _ReportContext:
    """Everything the page builders need from the run.

    generate_html_report used to be a single 1700-line function whose page
    builders were closures over ~30 locals; this is those locals, named once.
    """

    strings: ReportI18n
    badges: ReportBadges
    run_dir: Path
    bundle_dir: Path
    file_a: Path
    file_b: Path
    details: Sequence[dict]
    pages_records: list[dict]
    page_count_a: int
    page_count_b: int
    high_dpi: int
    stroke_tol_px: float
    mixed_precision_seqs: list[int]
    views_dir: Path
    slider_record_by_file: dict
    first_slider_file: str | None
    last_slider_file: str | None


def _build_dashboard_html(ctx: _ReportContext) -> tuple[str, dict[str, int]]:
    """Build index.html: the change matrix, its filters and the summary cards.

    Returns the page and the per-status counts, which the detail views reuse.
    """
    strings, badges = ctx.strings, ctx.badges
    lang, i18n = strings.lang, strings.all
    tr_attr = strings.tr_attr
    i18n_span = strings.i18n_span
    i18n_span_text = strings.i18n_span_text
    i18n_aria = strings.i18n_aria
    i18n_attr = strings.i18n_attr
    title_attrs = strings.title_attrs
    title_text = strings.title_text
    format_duration_pair = strings.format_duration_pair
    report_tags_for_page = badges.report_tags_for_page
    status_badge_html = badges.status_badge_html
    level_badge_html = badges.level_badge_html
    is_mixed_precision_page = badges.is_mixed_precision_page
    page_precision_text = badges.page_precision_text
    precision_badge_html = badges.precision_badge_html
    fg_meter_html = badges.fg_meter_html
    metric_percent_html = badges.metric_percent_html
    metric_area_html = badges.metric_area_html
    preview_tile = badges.preview_tile
    status_label_keys = STATUS_LABEL_KEYS
    level_label_keys = LEVEL_LABEL_KEYS
    run_dir, bundle_dir = ctx.run_dir, ctx.bundle_dir
    file_a, file_b = ctx.file_a, ctx.file_b
    details, pages_records = ctx.details, ctx.pages_records
    page_count_a, page_count_b = ctx.page_count_a, ctx.page_count_b
    high_dpi, stroke_tol_px = ctx.high_dpi, ctx.stroke_tol_px
    mixed_precision_seqs = ctx.mixed_precision_seqs

    matrix_rows: list[str] = []
    changed_cnt = 0
    added_cnt = 0
    removed_cnt = 0
    unchanged_cnt = 0

    for p in pages_records:
        status_tag, level_tag = report_tags_for_page(p)
        p["_status_tag"] = status_tag
        p["_level_tag"] = level_tag
        if status_tag == "CHANGED":
            changed_cnt += 1
        elif status_tag == "ADDED":
            added_cnt += 1
        elif status_tag == "REMOVED":
            removed_cnt += 1
        elif status_tag == "UNCHANGED":
            unchanged_cnt += 1

        a_idx = "—" if p["a_index"] is None else f"A{p['a_index']}"
        b_idx = "—" if p["b_index"] is None else f"B{p['b_index']}"
        seq_txt = str(p["seq"])
        diff_val = None if p.get("diff_metric") is None else float(p["diff_metric"])
        fg_diff_val = None if p.get("diff_foreground_metric") is None else float(p["diff_foreground_metric"])
        area_mm2_val = None if p.get("diff_area_mm2") is None else float(p["diff_area_mm2"])
        boxes_txt = "—" if p.get("bboxes_count") is None else str(int(p["bboxes_count"]))
        fg_sparse = bool(p.get("foreground_sparse") or False)
        href = f"views/{p['view_file']}"

        thumb_old = p["assets"].get("thumb_old")
        thumb_new = p["assets"].get("thumb_new")
        thumb_diff = p["assets"].get("thumb_diff")
        preview_html = (
            "<div class='pv'>"
            f"{preview_tile(thumb_old, 'OLD', 'old preview')}"
            f"{preview_tile(thumb_new, 'NEW', 'new preview')}"
            f"{preview_tile(thumb_diff, 'DIFF', 'diff preview')}"
            "</div>"
        )
        status_search = str(i18n[lang].get(status_label_keys.get(status_tag, ""), status_tag))
        level_search = str(i18n[lang].get(level_label_keys.get(level_tag, ""), level_tag))
        precision_badge = precision_badge_html(p)
        _precision_ru, precision_en = page_precision_text(p)
        precision_search = "custom precision пересчитан " + (precision_en if is_mixed_precision_page(p) else "")
        row_search = f"{seq_txt} {a_idx} {b_idx} {status_tag} {level_tag} {status_search} {level_search} {precision_search}".lower()
        matrix_rows.append(
            f"<tr class='mx-row' data-status='{status_tag}' data-level='{level_tag or 'NONE'}' "
            f"data-search='{html.escape(row_search, quote=True)}' data-href='{html.escape(href, quote=True)}'>"
            f"<td class='td-seq seq-col'>{html.escape(seq_txt)}</td>"
            f"<td class='td-map map-cell'>{html.escape(a_idx)}{report_icon('arrow-right', 'ic map-icon', 14)}{html.escape(b_idx)}</td>"
            f"<td class='td-status'>{status_badge_html(status_tag)}{precision_badge}</td>"
            f"<td class='td-level'>{level_badge_html(level_tag)}</td>"
            f"<td class='td-fg diff-cell'>{fg_meter_html(fg_diff_val, sparse=fg_sparse)}</td>"
            f"<td class='td-diff'>{metric_percent_html(diff_val)}</td>"
            f"<td class='td-area'>{metric_area_html(area_mm2_val)}</td>"
            f"<td class='td-boxes'>{html.escape(boxes_txt)}</td>"
            f"<td class='td-preview'>{preview_html}</td>"
            f"<td class='td-open'><a class='open-link' href='{html.escape(href, quote=True)}' "
            f"{i18n_aria('Открыть сравнение листа', 'Open sheet compare')} title='{tr_attr('open_sheet_title')}'>{report_icon('arrow-up-right', size=16)}</a></td>"
            "</tr>"
        )

    total_pages = len(pages_records)
    run_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    elapsed_sum = sum(float(row.get("elapsed_sec") or 0.0) for row in details)
    duration_ru, duration_en = format_duration_pair(elapsed_sum if elapsed_sum > 0 else None)
    if mixed_precision_seqs:
        seqs_txt = ", ".join(map(str, mixed_precision_seqs))
        dpi_meta_ru = f"DPI: {high_dpi} базовый · смешанная точность: листы {seqs_txt}"
        dpi_meta_en = f"DPI: {high_dpi} base · mixed precision: sheets {seqs_txt}"
    else:
        dpi_meta_ru = f"DPI: {high_dpi}"
        dpi_meta_en = f"DPI: {high_dpi}"
    run_meta = i18n_span_text(
        f"Дата: {run_timestamp} · длительность: {duration_ru} · {dpi_meta_ru} · stroke tol: {stroke_tol_px:g}px",
        f"Date: {run_timestamp} · duration: {duration_en} · {dpi_meta_en} · stroke tol: {stroke_tol_px:g}px",
    )
    old_doc_meta = i18n_span_text(f"Doc A · {page_count_a} листов · ред. ?", f"Doc A · {page_count_a} sheets · rev. ?")
    new_doc_meta = i18n_span_text(f"Doc B · {page_count_b} листов · ред. ?", f"Doc B · {page_count_b} sheets · rev. ?")
    footer_text = i18n_span_text(
        f"Создано PDFCompare Local · собрано локально · {run_timestamp}",
        f"Created by PDFCompare Local · built locally · {run_timestamp}",
    )
    csv_link = None
    if page_map_csv_path(run_dir).exists():
        csv_link = str(Path(os.path.relpath(page_map_csv_path(run_dir), bundle_dir))).replace("\\", "/")
    zip_link = None
    for candidate in (internal_dir(run_dir) / "report_bundle.zip", run_dir / "report_bundle.zip"):
        if candidate.exists():
            zip_link = str(Path(os.path.relpath(candidate, bundle_dir))).replace("\\", "/")
            break
    export_items = [
        f'<a href="report.json" download>{i18n_span_text("Скачать report.json", "Download report.json")}</a>'
    ]
    if csv_link:
        export_items.append(
            f'<a href="{html.escape(csv_link, quote=True)}" download>{i18n_span_text("Скачать CSV", "Download CSV")}</a>'
        )
    if zip_link:
        export_items.append(
            f'<a href="{html.escape(zip_link, quote=True)}" download>{i18n_span_text("Скачать ZIP-бандл", "Download ZIP bundle")}</a>'
        )
    export_menu_html = "".join(export_items)
    sun_icon_js = json.dumps(report_icon("sun", size=18))
    moon_icon_js = json.dumps(report_icon("moon", size=18))
    index_title_ru = "Сводка сравнения PDF — матрица изменений"
    index_title_en = "PDF compare summary — change matrix"

    summary_html = f"""<!doctype html>
<html lang="{lang}" {title_attrs(index_title_ru, index_title_en)}>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>{title_text(index_title_ru, index_title_en)}</title>
  <script>
    try {{
      const savedTheme = localStorage.getItem('pdfcompare.theme');
      if (savedTheme === 'dark') document.documentElement.dataset.theme = 'dark';
      const savedLang = localStorage.getItem('pdfcompare.lang');
      if (savedLang === 'en' || savedLang === 'ru') document.documentElement.lang = savedLang;
    }} catch (e) {{}}
  </script>
  <style>
{REPORT_CSS_TOKENS}
{CSS_INDEX}
  </style>
</head>
<body>
  <div class="wrap">
    <header class="topbar">
      <div class="brand">
        <div class="brand-mark">{report_icon("git-compare", size=20)}</div>
        <div>
          <h1>{i18n_span_text("PDF Compare — матрица изменений", "PDF Compare — Change Matrix")}</h1>
          <div class="subtitle">{i18n_span_text("Локальное сравнение PDF без облака", "Local PDF comparison without cloud processing")}</div>
        </div>
      </div>
      <div class="top-actions">
        <div class="lang-switch" {i18n_aria("Язык", "Language")}>
          <button type="button" data-lang="ru">RU</button>
          <button type="button" data-lang="en">EN</button>
        </div>
        <button id="themeToggle" class="btn icon-only" type="button" {i18n_aria("Переключить тему", "Toggle theme")}>{report_icon("moon", size=18)}</button>
      </div>
    </header>

    <section class="docs" {i18n_aria("Документы", "Documents")}>
      <article class="doc-card old">
        {i18n_span_text("OLD", "OLD", "doc-pill")}
        <div>
          <div class="doc-name">{html.escape(file_a.name)}</div>
          <div class="doc-meta">{old_doc_meta}</div>
        </div>
      </article>
      <div class="doc-arrow">{report_icon("arrow-right", size=20)}</div>
      <article class="doc-card new">
        {i18n_span_text("NEW", "NEW", "doc-pill")}
        <div>
          <div class="doc-name">{html.escape(file_b.name)}</div>
          <div class="doc-meta">{new_doc_meta}</div>
        </div>
      </article>
    </section>
    <p class="run-meta">{run_meta}</p>

    <section class="kpi" {i18n_aria("Сводка", "Summary")}>
      <button type="button" class="kpi-card" data-kind="status" data-value="CHANGED" aria-pressed="false">
        <span class="kpi-ico">{report_icon("alert-circle", size=20)}</span>
        <span><span class="kpi-label">{i18n_span_text("ИЗМЕНЕНЫ", "CHANGED")}</span><span class="kpi-value"><strong>{changed_cnt}</strong><span class="kpi-context">{i18n_span_text(f"из {total_pages}", f"of {total_pages}")}</span></span></span>
      </button>
      <button type="button" class="kpi-card" data-kind="status" data-value="ADDED" aria-pressed="false">
        <span class="kpi-ico">{report_icon("plus-circle", size=20)}</span>
        <span><span class="kpi-label">{i18n_span_text("ДОБАВЛЕНЫ", "ADDED")}</span><span class="kpi-value"><strong>{added_cnt}</strong><span class="kpi-context">{i18n_span_text(f"из {total_pages}", f"of {total_pages}")}</span></span></span>
      </button>
      <button type="button" class="kpi-card" data-kind="status" data-value="REMOVED" aria-pressed="false">
        <span class="kpi-ico">{report_icon("minus-circle", size=20)}</span>
        <span><span class="kpi-label">{i18n_span_text("УДАЛЕНЫ", "REMOVED")}</span><span class="kpi-value"><strong>{removed_cnt}</strong><span class="kpi-context">{i18n_span_text(f"из {total_pages}", f"of {total_pages}")}</span></span></span>
      </button>
      <button type="button" class="kpi-card" data-kind="status" data-value="UNCHANGED" aria-pressed="false">
        <span class="kpi-ico">{report_icon("check-circle", size=20)}</span>
        <span><span class="kpi-label">{i18n_span_text("БЕЗ ИЗМЕНЕНИЙ", "UNCHANGED")}</span><span class="kpi-value"><strong>{unchanged_cnt}</strong><span class="kpi-context">{i18n_span_text(f"из {total_pages}", f"of {total_pages}")}</span></span></span>
      </button>
    </section>

    <section class="matrix-tools">
      <label class="search-wrap">
        {i18n_span("search_sheet", "sr-only")}
        {report_icon("search", size=16)}
        <input id="sheetSearch" class="search" {i18n_attr("search_sheet", "placeholder")} placeholder="{tr_attr("search_sheet")}"/>
      </label>
      <div class="dropdown" data-dropdown>
        <button id="exportBtn" class="btn" type="button" aria-haspopup="menu" aria-expanded="false">{report_icon("download", size=16)}{i18n_span_text("Экспорт", "Export")}<span class="caret">▾</span></button>
        <div class="dropdown-menu" role="menu">{export_menu_html}</div>
      </div>
    </section>

    <section class="matrix" {i18n_aria("Матрица изменений", "Change matrix")}>
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>A {report_icon("arrow-right", "ic map-icon", 14)} B</th>
            <th>{i18n_span_text("Статус", "Status")}</th>
            <th>{i18n_span_text("Уровень", "Level")}</th>
            <th>{i18n_span_text("Заполнено %", "Drawn %")}</th>
            <th>{i18n_span_text("Лист %", "Sheet %")}</th>
            <th>mm²</th>
            <th>Δ</th>
            <th>{i18n_span_text("Превью", "Preview")}</th>
            <th>{i18n_span_text("Открыть", "Open")}</th>
          </tr>
        </thead>
        <tbody id="mxBody">
          {''.join(matrix_rows)}
        </tbody>
      </table>
      <div id="emptyMsg" class="empty" style="display:none;">{i18n_span("empty_filter")}</div>
    </section>

    <details class="legend">
      <summary>{i18n_span_text("Легенда и пороги", "Legend and thresholds")}</summary>
      <div class="legend-body">
        <div class="legend-row">{status_badge_html("CHANGED")}<span>{i18n_span_text("лист содержит визуальные изменения", "sheet has visual changes")}</span></div>
        <div class="legend-row">{status_badge_html("ADDED")}<span>{i18n_span("legend_added_desc")}</span></div>
        <div class="legend-row">{status_badge_html("REMOVED")}<span>{i18n_span("legend_removed_desc")}</span></div>
        <div class="legend-row">{status_badge_html("UNCHANGED")}<span>{i18n_span_text("существенные изменения не обнаружены", "no significant changes detected")}</span></div>
        <div class="legend-row">{level_badge_html("MAJOR")}<span>{i18n_span_text("≥ 20% заполненного - MAJOR", "≥ 20% drawn - MAJOR")}</span></div>
        <div class="legend-row">{level_badge_html("MODERATE")}<span>{i18n_span_text("≥ 8% заполненного - MODERATE", "≥ 8% drawn - MODERATE")}</span></div>
        <div class="legend-row">{level_badge_html("MINOR")}<span>{i18n_span_text("≥ 1% заполненного - MINOR", "≥ 1% drawn - MINOR")}</span></div>
        <div class="legend-row">{level_badge_html("UNCHANGED")}<span>{i18n_span_text("без зон изменений - UNCHANGED", "no change zones - UNCHANGED")}</span></div>
      </div>
    </details>

    <footer class="footer">{footer_text}</footer>
  </div>

  <script>
    const kpis = [...document.querySelectorAll('.kpi-card')];
    const rows = [...document.querySelectorAll('#mxBody tr.mx-row')];
    const searchInput = document.getElementById('sheetSearch');
    const emptyMsg = document.getElementById('emptyMsg');
    const langButtons = [...document.querySelectorAll('[data-lang]')];
    const themeBtn = document.getElementById('themeToggle');
    const sunIcon = {sun_icon_js};
    const moonIcon = {moon_icon_js};
    let statusFilter = 'ALL';

    function applyTheme(theme) {{
      const next = theme === 'dark' ? 'dark' : 'light';
      if (next === 'dark') {{
        document.documentElement.dataset.theme = 'dark';
        themeBtn.innerHTML = sunIcon;
      }} else {{
        delete document.documentElement.dataset.theme;
        themeBtn.innerHTML = moonIcon;
      }}
      try {{ localStorage.setItem('pdfcompare.theme', next); }} catch (e) {{}}
    }}

    function applyLang(nextLang, persist = true) {{
      const next = nextLang === 'en' ? 'en' : 'ru';
      const root = document.documentElement;
      document.documentElement.lang = next;
      if (root.dataset.titleRu && root.dataset.titleEn) {{
        document.title = next === 'en' ? root.dataset.titleEn : root.dataset.titleRu;
      }}
      document.querySelectorAll('[data-i18n-ru]').forEach(el => {{
        el.textContent = next === 'en' ? el.dataset.i18nEn : el.dataset.i18nRu;
      }});
      document.querySelectorAll('[data-i18n-placeholder-ru]').forEach(el => {{
        el.setAttribute('placeholder', next === 'en' ? el.dataset.i18nPlaceholderEn : el.dataset.i18nPlaceholderRu);
      }});
      document.querySelectorAll('[data-i18n-aria-ru]').forEach(el => {{
        el.setAttribute('aria-label', next === 'en' ? el.dataset.i18nAriaEn : el.dataset.i18nAriaRu);
      }});
      langButtons.forEach(btn => btn.classList.toggle('active', btn.dataset.lang === next));
      if (persist) {{
        try {{ localStorage.setItem('pdfcompare.lang', next); }} catch (e) {{}}
      }}
    }}

    function updateFilterUi() {{
      kpis.forEach(kpi => {{
        const active = statusFilter === kpi.dataset.value;
        kpi.classList.toggle('active', active);
        kpi.setAttribute('aria-pressed', active ? 'true' : 'false');
      }});
    }}

    function applyFilters() {{
      const q = searchInput.value.trim().toLowerCase();
      let visible = 0;
      rows.forEach(row => {{
        const st = row.dataset.status;
        const text = row.dataset.search || '';
        let ok = true;
        if (statusFilter !== 'ALL') ok = st === statusFilter;
        if (ok && q) ok = text.includes(q);
        row.style.display = ok ? '' : 'none';
        if (ok) visible += 1;
      }});
      emptyMsg.style.display = visible ? 'none' : 'block';
      updateFilterUi();
    }}

    function handleKpiFilter(control) {{
      const value = control.dataset.value || '';
      statusFilter = statusFilter === value ? 'ALL' : value;
      applyFilters();
    }}

    kpis.forEach(control => {{
      control.addEventListener('click', () => handleKpiFilter(control));
    }});
    searchInput.addEventListener('input', applyFilters);
    rows.forEach(row => {{
      row.addEventListener('click', (e) => {{
        const target = e.target;
        if (target && target.closest('a')) return;
        const href = row.dataset.href;
        if (href) window.location.href = href;
      }});
    }});
    document.querySelectorAll('[data-dropdown]').forEach(dropdown => {{
      const btn = dropdown.querySelector('button');
      btn.addEventListener('click', (e) => {{
        e.stopPropagation();
        const open = dropdown.classList.toggle('open');
        btn.setAttribute('aria-expanded', open ? 'true' : 'false');
      }});
    }});
    document.addEventListener('click', () => {{
      document.querySelectorAll('[data-dropdown].open').forEach(dropdown => {{
        dropdown.classList.remove('open');
        const btn = dropdown.querySelector('button');
        if (btn) btn.setAttribute('aria-expanded', 'false');
      }});
    }});
    langButtons.forEach(btn => btn.addEventListener('click', () => applyLang(btn.dataset.lang)));
    themeBtn.addEventListener('click', () => applyTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'));
    let savedTheme = 'light';
    try {{ savedTheme = localStorage.getItem('pdfcompare.theme') || (document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light'); }} catch (e) {{}}
    applyTheme(savedTheme);
    let savedLang = document.documentElement.lang === 'en' ? 'en' : 'ru';
    try {{ savedLang = localStorage.getItem('pdfcompare.lang') || savedLang; }} catch (e) {{}}
    applyLang(savedLang, false);
    applyFilters();
  </script>
</body>
</html>
"""

    return summary_html, {
        "changed": changed_cnt,
        "added": added_cnt,
        "removed": removed_cnt,
        "unchanged": unchanged_cnt,
    }


def _write_slider_view(
    ctx: _ReportContext,
    p: dict,
    view_idx: int,
    *,
    slider_file: str | None,
    old_src: str | None,
    new_src: str | None,
    diff_txt: str,
    fg_diff_txt: str,
    status_tag: str,
    level_tag: str,
    bboxes_data: list[dict],
) -> None:
    """Write the side-by-side slider page for one sheet (cmp_NNN.html)."""
    strings, badges = ctx.strings, ctx.badges
    lang, t = strings.lang, strings.t
    i18n_span_text = strings.i18n_span_text
    i18n_aria = strings.i18n_aria
    i18n_placeholder_text = strings.i18n_placeholder_text
    title_attrs = strings.title_attrs
    title_text = strings.title_text
    status_badge_html = badges.status_badge_html
    level_badge_html = badges.level_badge_html
    pages_records = ctx.pages_records
    views_dir = ctx.views_dir
    first_slider_file = ctx.first_slider_file
    last_slider_file = ctx.last_slider_file

    if slider_file and old_src and new_src:
        # Immediate neighbours in view order. Unlike prev/next *slider* files — which
        # skip added/removed sheets, because those have no slider — these step exactly
        # one sheet at a time; a sheet without a slider opens in its detail view. So
        # ←/→ and the sheet buttons never silently jump over a sheet.
        prev_any_rec = pages_records[view_idx - 2] if view_idx - 2 >= 0 else None
        next_any_rec = pages_records[view_idx] if view_idx < len(pages_records) else None
        prev_any_file = (
            (str(prev_any_rec.get("slider_file") or prev_any_rec.get("view_file") or "") or None)
            if prev_any_rec
            else None
        )
        next_any_file = (
            (str(next_any_rec.get("slider_file") or next_any_rec.get("view_file") or "") or None)
            if next_any_rec
            else None
        )
        prev_any_ord = view_idx - 1 if prev_any_rec else ""
        next_any_ord = view_idx + 1 if next_any_rec else ""
        # "Home" as a button, not only as a key: the keyboard shortcut is invisible
        # to anyone who has not read the hint line.
        at_first = not (first_slider_file and first_slider_file != slider_file)
        first_cmp_btn = (
            f'<a class="btn nav-edge" href="{html.escape(str(first_slider_file), quote=True)}" '
            f'{i18n_aria("В начало (Home)", "First sheet (Home)")}>'
            f'{report_icon("chevrons-left", size=16)}{i18n_span_text("В начало", "First")}</a>'
            if not at_first
            else f'<span class="btn nav-edge disabled">{report_icon("chevrons-left", size=16)}'
            f'{i18n_span_text("В начало", "First")}</span>'
        )
        prev_cmp_btn = (
            f'<a class="btn" href="{html.escape(str(prev_any_file), quote=True)}">'
            f'{report_icon("chevron-left", size=16)}{i18n_span_text(f"Лист {prev_any_ord}", f"Sheet {prev_any_ord}")}</a>'
            if prev_any_file
            else f'<span class="btn disabled">{report_icon("chevron-left", size=16)}{i18n_span_text("Первый лист", "First sheet")}</span>'
        )
        next_cmp_btn = (
            f'<a class="btn primary" href="{html.escape(str(next_any_file), quote=True)}">'
            f'{i18n_span_text(f"Лист {next_any_ord}", f"Sheet {next_any_ord}")}{report_icon("chevron-right", size=16)}</a>'
            if next_any_file
            else f'<span class="btn primary disabled">{i18n_span_text("Последний лист", "Last sheet")}{report_icon("chevron-right", size=16)}</span>'
        )
        slider_title_ru = f"Слайдер — лист {view_idx} / {len(pages_records)}"
        slider_title_en = f"Slider — sheet {view_idx} / {len(pages_records)}"
        slider_html = f"""<!doctype html>
<html lang="{lang}" {title_attrs(slider_title_ru, slider_title_en)}>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>{title_text(slider_title_ru, slider_title_en)}</title>
  <script>
    try {{
      if (new URLSearchParams(location.search).get('embed') === '1') {{
        document.documentElement.classList.add('embed');
      }}
      const savedTheme = localStorage.getItem('pdfcompare.theme');
      if (savedTheme === 'dark') document.documentElement.dataset.theme = 'dark';
      const savedLang = localStorage.getItem('pdfcompare.lang');
      if (savedLang === 'en' || savedLang === 'ru') document.documentElement.lang = savedLang;
      const savedBbox = JSON.parse(localStorage.getItem('pdfcompare.bbox') || '{{}}');
      const palettes = {{
        yellow: {{ border: [255, 180, 0], fill: [255, 235, 120] }},
        pink: {{ border: [236, 72, 153], fill: [244, 114, 182] }},
        green: {{ border: [22, 163, 74], fill: [134, 239, 172] }},
      }};
      const palette = palettes[savedBbox.color] || palettes.yellow;
      const opacity = Math.max(0, Math.min(100, Number(savedBbox.opacity) || 74));
      document.documentElement.style.setProperty('--bbox-border', `rgba(${{palette.border.join(',')}},${{(opacity / 100).toFixed(2)}})`);
      document.documentElement.style.setProperty('--bbox-fill', `rgba(${{palette.fill.join(',')}},${{(opacity / 100 * 0.18).toFixed(2)}})`);
      document.documentElement.dataset.bboxEnabled = savedBbox.enabled === false ? 'false' : 'true';
    }} catch (e) {{}}
  </script>
  <style>
    html, body {{ width:100%; height:100%; }}
    body {{ margin:0; font-family:Segoe UI,Arial,sans-serif; background:#f3f6fb; color:#1d2433; overflow:hidden; }}
    .wrap {{ width:100vw; height:100vh; margin:0; padding:0; }}
    .panel {{ width:100%; height:100%; background:#fff; border:0; border-radius:0; padding:10px; box-sizing:border-box; display:flex; flex-direction:column; }}
    .top {{ display:flex; flex-wrap:wrap; gap:8px; align-items:center; justify-content:space-between; margin-bottom:10px; }}
    .top-actions {{ display:flex; flex-wrap:wrap; gap:6px; align-items:center; justify-content:flex-end; }}
    .btn {{ border:1px solid #d7deea; border-radius:8px; padding:6px 10px; text-decoration:none; color:#0f4fa8; background:#fff; }}
    .btn.disabled {{ color:#7b8496; background:#f4f6fa; cursor:default; }}
    .btn-save {{ background:#eaf8ef; border-color:#88d4a2; color:#176235; font-weight:800; }}
    .slider-nav-search {{ width:100%; box-sizing:border-box; border:1px solid #d7deea; border-radius:8px; padding:8px; margin:0 0 8px 0; }}
    .slider-nav-list {{ display:grid; gap:6px; }}
    .slider-nav-item {{ display:grid; gap:4px; border:1px solid #d7deea; border-radius:8px; padding:8px; text-decoration:none; color:inherit; background:#fbfdff; }}
    .slider-nav-item:hover {{ border-color:#0f4fa8; background:#eef5ff; }}
    .slider-nav-item.current {{ border-color:#1fa463; background:#e8f8ee; box-shadow:inset 4px 0 0 #1fa463; font-weight:800; }}
    .slider-nav-main {{ display:flex; justify-content:space-between; gap:8px; align-items:center; }}
    .slider-nav-meta {{ color:#5f6b84; font-size:12px; }}
    .s {{ font-size:11px; border-radius:999px; padding:2px 8px; color:#fff; white-space:nowrap; }}
    .s.ok {{ background:#1f8c4f; }} .s.warn {{ background:#cc3d17; }} .s.add {{ background:#0569d0; }}
    .stage {{ flex:1; width:100%; background:#fff; box-sizing:border-box; overflow:auto; min-height:0; position:relative; }}
    .stage.dragging {{ cursor:ew-resize; }}
    .stage.panning {{ cursor:grabbing; }}
    .compare-surface {{ position:relative; display:none; background:#fff; overflow:hidden; cursor:ew-resize; transform-origin:0 0; }}
    .layer {{ position:absolute; inset:0; width:100%; height:100%; object-fit:fill; user-select:none; -webkit-user-drag:none; }}
    .old-layer {{ position:absolute; inset:0; overflow:hidden; clip-path:inset(0 50% 0 0); }}
    .bbox-layer {{ position:absolute; inset:0; pointer-events:none; }}
    .bbox {{ position:absolute; border:2px solid var(--bbox-border); background:var(--bbox-fill); box-sizing:border-box; }}
    .divider {{ position:absolute; top:0; bottom:0; left:50%; width:2px; background:rgba(20,120,255,.95); pointer-events:none; }}
    .load-msg {{ position:absolute; inset:0; display:flex; align-items:center; justify-content:center; color:#5f6b84; }}
    .stage.panning .compare-surface {{ cursor:grabbing; }}
    .slider-wrap {{ margin:10px 0 0 0; display:flex; gap:10px; align-items:center; flex-wrap:wrap; }}
    input[type=range] {{ width:100%; }}
    .muted {{ color:#5f6b84; font-size:12px; }}
    .small {{ width:150px; }}
    .bbox-controls {{ display:flex; align-items:center; gap:6px; flex-wrap:wrap; margin-left:auto; }}
    .swatch-option {{ display:inline-flex; align-items:center; gap:5px; border:1px solid #d7deea; border-radius:8px; padding:5px 8px; background:#fff; cursor:pointer; user-select:none; }}
    .swatch-option input {{ margin:0; }}
    .swatch {{ width:14px; height:14px; border-radius:4px; border:2px solid currentColor; box-sizing:border-box; }}
    .swatch-yellow {{ color:rgb(255,180,0); background:rgba(255,235,120,.45); }}
    .swatch-pink {{ color:rgb(236,72,153); background:rgba(244,114,182,.45); }}
    .swatch-green {{ color:rgb(22,163,74); background:rgba(134,239,172,.45); }}
    .bbox-opacity {{ width:110px; }}
    .zoom-rect {{ position:absolute; border:2px dashed rgba(20,120,255,.95); background:rgba(20,120,255,.12); box-sizing:border-box; pointer-events:none; z-index:5; display:none; }}
    .annot-layer {{ position:absolute; inset:0; pointer-events:none; z-index:6; }}
    .annot-layer.annot-hidden {{ display:none; }}
    .annot-box {{ position:absolute; box-sizing:border-box; border:2px solid; border-radius:3px; pointer-events:none; }}
    .annot-box.green {{ border-color:rgba(22,163,74,.95); background:rgba(22,163,74,.16); }}
    .annot-box.yellow {{ border-color:rgba(202,138,4,.95); background:rgba(234,179,8,.18); }}
    .annot-box.red {{ border-color:rgba(220,38,38,.95); background:rgba(239,68,68,.16); }}
    .annot-note {{ position:absolute; left:-2px; top:0; transform:translateY(-100%); max-width:240px; background:rgba(17,24,39,.9); color:#fff; font:12px/1.3 Segoe UI,Arial,sans-serif; padding:2px 6px; border-radius:4px 4px 4px 0; white-space:pre-wrap; }}
    .annot-del {{ position:absolute; right:-9px; top:-9px; width:18px; height:18px; border-radius:50%; border:0; background:#dc2626; color:#fff; font-size:12px; line-height:18px; padding:0; cursor:pointer; pointer-events:auto; display:none; }}
    .stage.annot-mode .annot-box {{ pointer-events:auto; cursor:pointer; }}
    .stage.annot-mode .annot-del {{ display:block; }}
    .stage.annot-mode .compare-surface {{ cursor:crosshair; }}
    .annot-draft {{ position:absolute; border:2px dashed; border-radius:3px; box-sizing:border-box; pointer-events:none; z-index:7; display:none; }}
    .annot-draft.green {{ border-color:rgba(22,163,74,.95); background:rgba(22,163,74,.12); }}
    .annot-draft.yellow {{ border-color:rgba(202,138,4,.95); background:rgba(234,179,8,.14); }}
    .annot-draft.red {{ border-color:rgba(220,38,38,.95); background:rgba(239,68,68,.12); }}
    .annot-tools {{ display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-top:8px; }}
    .annot-swatch {{ width:20px; height:20px; border-radius:5px; border:2px solid rgba(0,0,0,.15); cursor:pointer; padding:0; }}
    .annot-swatch.active {{ outline:2px solid #111827; outline-offset:1px; }}
    .annot-swatch.green {{ background:rgba(22,163,74,.55); }}
    .annot-swatch.yellow {{ background:rgba(234,179,8,.6); }}
    .annot-swatch.red {{ background:rgba(239,68,68,.55); }}
    .btn.active {{ background:#0f4fa8; color:#fff; border-color:#0f4fa8; }}
{REPORT_CSS_TOKENS}
{CSS_CMP}
  </style>
</head>
<body>
  <div class="cmp-page pinned" id="cmpPage">
  <aside class="sheet-drawer" id="sheetDrawer" {i18n_aria("Навигация по листам", "Sheet navigation")}>
    <button class="sheet-drawer-handle" type="button" aria-controls="sheetDrawerPanel" aria-expanded="false" {i18n_aria("Открыть список листов", "Open sheet list")}>
      {report_icon("list", size=16)}
      {i18n_span_text("Открыть список листов", "Open sheet list", "sr-only")}
    </button>
    <div class="sheet-drawer-panel" id="sheetDrawerPanel">
      <div class="sheet-drawer-head">
        <strong>{i18n_span_text("Листы", "Sheets")}</strong>
        <span class="muted">{view_idx} / {len(pages_records)}</span>
        <button class="sheet-drawer-pin" id="drawerPin" type="button" {i18n_aria("Открепить панель", "Unpin panel")}>📌</button>
      </div>
      <input id="sliderNavSearch" class="slider-nav-search" type="search" {i18n_placeholder_text("Поиск…", "Search…")}/>
      <div id="sliderNavList" class="slider-nav-list"></div>
      <div class="sheet-drawer-hint muted">{i18n_span_text("📌 — открепить · ←/→ — соседний лист", "📌 — unpin · ←/→ — adjacent sheet")}</div>
    </div>
  </aside>
  <div class="cmp-main">
    <header class="cmp-header">
      <div class="cmp-left">
        <a class="btn home-neon icon-only" href="../index.html" {i18n_aria("В начало — к матрице изменений", "Home — to the change matrix")}>{report_icon("home", size=16)}{i18n_span_text("В начало", "Home", "sr-only")}</a>
        <a class="btn ghost" href="{html.escape(p['view_file'], quote=True)}">{report_icon("arrow-left", size=16)}{i18n_span_text("К листу", "Back to sheet")}</a>
      </div>
      <div class="cmp-title">
        <span>{i18n_span_text(f"Лист {view_idx} / {len(pages_records)}", f"Sheet {view_idx} / {len(pages_records)}")}</span>
        {status_badge_html(status_tag)}
        {level_badge_html(level_tag) if level_tag else ""}
        <span class="muted">· {html.escape(fg_diff_txt)} FG · {html.escape(diff_txt)}</span>
      </div>
      <div class="cmp-right">
        <!-- No sheet counter here: the title already says "Лист 5 / 12", and two
             copies of it cost the header the width its controls need. -->
        <div class="cmp-nav">
          {first_cmp_btn}
          {prev_cmp_btn}
          {next_cmp_btn}
        </div>
        <div class="segmented" {i18n_aria("Управление слайдером", "Slider controls")}>
          <button class="seg-btn" id="fitBtn" type="button">{report_icon("maximize-2", size=16)}{i18n_span_text("Вписать", "Fit")}</button>
          <button class="seg-btn" id="oneBtn" type="button">{report_icon("square", size=16)}{i18n_span_text("1:1", "1:1")}</button>
          <button class="seg-btn seg-btn-accent" id="zonesBtn" type="button" {i18n_aria("Подсветить зоны изменений", "Highlight change zones")}>{report_icon("target", size=16)}{i18n_span_text("Зоны", "Zones")}</button>
          <button class="seg-btn" id="zoomOutBtn" type="button" {i18n_aria("Отдалить (мелкий шаг)", "Zoom out (fine step)")}>{report_icon("zoom-out", size=16)}</button>
          <span class="seg-btn seg-btn-static">{i18n_span_text("Масштаб", "Zoom")} <span id="zoomVal">100%</span></span>
          <button class="seg-btn" id="zoomInBtn" type="button" {i18n_aria("Приблизить (мелкий шаг)", "Zoom in (fine step)")}>{report_icon("zoom-in", size=16)}</button>
        </div>
        <!-- Bbox controls sit open in the header: colour and opacity are adjusted
             while looking at the sheet, and a dropdown made every tweak a two-step trip. -->
        <div class="bbox-bar" {i18n_aria("Настройки выделения", "Bbox settings")}>
          <span class="bbox-swatch swatch-yellow" id="bboxSwatch" aria-hidden="true"></span>
          <span class="bbox-bar-label">{i18n_span_text("Bbox", "Bbox")}</span>
          <div class="seg-toggle" id="bboxToggle" role="group" {i18n_aria("Показывать Bbox", "Show Bbox")}>
            <button type="button" class="seg-toggle-opt active" data-bbox="on">{i18n_span_text("ON", "ON")}</button>
            <button type="button" class="seg-toggle-opt" data-bbox="off">{i18n_span_text("OFF", "OFF")}</button>
          </div>
          <div class="bbox-colors">
            <button type="button" class="swatch-option active" data-color="yellow" {i18n_aria("Жёлтый", "Yellow")}><span class="swatch swatch-yellow"></span></button>
            <button type="button" class="swatch-option" data-color="pink" {i18n_aria("Розовый", "Pink")}><span class="swatch swatch-pink"></span></button>
            <button type="button" class="swatch-option" data-color="green" {i18n_aria("Зелёный", "Green")}><span class="swatch swatch-green"></span></button>
          </div>
          <input class="bbox-opacity" id="bboxOpacity" type="range" min="0" max="100" value="74" {i18n_aria("Прозрачность рамок", "Bbox opacity")}/>
          <span class="bbox-opacity-value" id="bboxOpacityValue">74%</span>
        </div>
      </div>
    </header>
      <div class="stage" id="stage" tabindex="0">
        <div class="compare-surface" id="surface">
          <img id="imgNew" class="layer new-layer" alt="{html.escape(t["slider_new"])}" draggable="false"/>
          <div id="oldLayer" class="old-layer"><img id="imgOld" class="layer" alt="{html.escape(t["slider_old"])}" draggable="false"/></div>
          <div id="bboxLayer" class="bbox-layer"></div>
          <div id="zoneLayer" class="zone-layer" aria-hidden="true"></div>
          <div id="annotLayer" class="annot-layer" aria-hidden="true"></div>
          <div id="zoomRect" class="zoom-rect"></div>
          <div id="annotDraft" class="annot-draft"></div>
          <div id="divider" class="divider"></div>
        </div>
        <div id="zoneCounter" class="zone-counter" role="status" aria-live="polite"></div>
        <div id="loadMsg" class="load-msg">{html.escape(t["no_data"])}</div>
      </div>
      <div class="slider-panel">
        <div class="split-line">
          {i18n_span_text("OLD", "OLD", "split-label old")}
          <input id="split" type="range" min="0" max="100" step="0.1" value="50"/>
          {i18n_span_text("NEW", "NEW", "split-label new")}
        </div>
        <input id="zoom" class="sr-only" type="range" min="1" max="500" value="100"/>
        <div class="hint">{i18n_span_text("ЛКМ - сплит · ПКМ-drag - pan · СКМ-выделение - zoom · Ctrl+Wheel - zoom · Z/H - зоны", "Left click - split · Right drag - pan · Middle drag - zoom to rect · Ctrl+Wheel - zoom · Z/H - zones")}</div>
        <div class="annot-tools" {i18n_aria("Заметки к зонам", "Zone notes")}>
          <button id="annotBtn" class="btn" type="button" {i18n_aria("Режим заметок: выделите область и впишите комментарий", "Note mode: drag a box and type a comment")}>{report_icon("square-dashed", size=16)}{i18n_span_text("Заметка", "Note")}</button>
          <button class="annot-swatch green" data-annot-color="green" type="button" {i18n_aria("Зелёный — нет изменений", "Green — no change")}></button>
          <button class="annot-swatch yellow active" data-annot-color="yellow" type="button" {i18n_aria("Жёлтый — спорное", "Yellow — unsure")}></button>
          <button class="annot-swatch red" data-annot-color="red" type="button" {i18n_aria("Красный — изменение", "Red — change")}></button>
          <button id="annotShowBtn" class="btn" type="button">{i18n_span_text("Скрыть заметки", "Hide notes")}</button>
          <span id="annotCount" class="muted"></span>
          <span class="muted">{i18n_span_text("· хранится в браузере, ✎ дв.клик — правка", "· stored in the browser, ✎ double-click to edit")}</span>
        </div>
      </div>
  </div>
  </div>
  <script src="../{NAV_DATA_FILE}"></script>
  <script>
    const oldSrc = {json.dumps(old_src)};
    const newSrc = {json.dumps(new_src)};
    const bboxData = {json.dumps(bboxes_data, ensure_ascii=False)};
    const prevSheetHref = {json.dumps(prev_any_file)};
    const nextSheetHref = {json.dumps(next_any_file)};
    const firstSliderHref = {json.dumps(first_slider_file)};
    const lastSliderHref = {json.dumps(last_slider_file)};
    const slider = document.getElementById('split');
    const zoom = document.getElementById('zoom');
    const zoomVal = document.getElementById('zoomVal');
    const fitBtn = document.getElementById('fitBtn');
    const oneBtn = document.getElementById('oneBtn');
    const zoomInBtn = document.getElementById('zoomInBtn');
    const zoomOutBtn = document.getElementById('zoomOutBtn');
    const stage = document.getElementById('stage');
    const surface = document.getElementById('surface');
    const oldLayer = document.getElementById('oldLayer');
    const divider = document.getElementById('divider');
    const bboxLayer = document.getElementById('bboxLayer');
    const loadMsg = document.getElementById('loadMsg');
    const oldImg = document.getElementById('imgOld');
    const newImg = document.getElementById('imgNew');
    const bboxToggle = document.getElementById('bboxToggle');
    const bboxOpacity = document.getElementById('bboxOpacity');
    const bboxOpacityValue = document.getElementById('bboxOpacityValue');
    const bboxSwatch = document.getElementById('bboxSwatch');
    const zonesBtn = document.getElementById('zonesBtn');
    const zoneLayer = document.getElementById('zoneLayer');
    const zoneCounter = document.getElementById('zoneCounter');
    const allSheets = (window.PDFCOMPARE_NAV && window.PDFCOMPARE_NAV.pages) || [];
    const currentSeq = {view_idx};
    const drawer = document.getElementById('sheetDrawer');
    const drawerHandle = drawer ? drawer.querySelector('.sheet-drawer-handle') : null;
    const sliderNavSearch = document.getElementById('sliderNavSearch');
    const sliderNavList = document.getElementById('sliderNavList');
    let sliderNavItems = [];
    function escapeHtml(value) {{
      return String(value ?? '').replace(/[&<>"']/g, ch => ({{
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;',
      }}[ch]));
    }}
    function badgeClass(status) {{
      if (status === 'ADDED') return 'st-added';
      if (status === 'REMOVED') return 'st-removed';
      if (status === 'UNCHANGED') return 'st-unchanged';
      return 'st-changed';
    }}
    function renderDrawerItems() {{
      if (!sliderNavList) return;
      const lang = document.documentElement.lang === 'en' ? 'en' : 'ru';
      sliderNavList.innerHTML = allSheets.map(sheet => {{
        const classes = 'slider-nav-item' + (sheet.seq === currentSeq ? ' current' : '') + (sheet.hasSlider ? '' : ' disabled-slider');
        const label = escapeHtml(sheet.label || '');
        const statusRu = escapeHtml(sheet.statusRu || sheet.status || '');
        const statusEn = escapeHtml(sheet.statusEn || sheet.status || '');
        const statusLabel = lang === 'en' ? statusEn : statusRu;
        const metaRu = escapeHtml(sheet.metaRu || '');
        const metaEn = escapeHtml(sheet.metaEn || '');
        const meta = lang === 'en' ? metaEn : metaRu;
        const title = escapeHtml(lang === 'en' ? sheet.titleEn : sheet.titleRu);
        const ariaRu = escapeHtml(sheet.ariaRu || '');
        const ariaEn = escapeHtml(sheet.ariaEn || '');
        const aria = lang === 'en' ? ariaEn : ariaRu;
        return '<a class="' + classes + '" data-label="' + escapeHtml(sheet.search || '') + '" href="' + escapeHtml(sheet.href || '#') + '" role="menuitem" title="' + title + '" aria-label="' + aria + '" data-i18n-aria-ru="' + ariaRu + '" data-i18n-aria-en="' + ariaEn + '">'
          + '<span class="slider-nav-main"><b>' + escapeHtml(String(sheet.seq || '')) + ' · ' + label + '</b>'
          + '<span class="badge ' + badgeClass(sheet.status) + '" data-i18n-ru="' + statusRu + '" data-i18n-en="' + statusEn + '">' + statusLabel + '</span></span>'
          + '<span class="slider-nav-meta" data-i18n-ru="' + metaRu + '" data-i18n-en="' + metaEn + '">' + meta + '</span></a>';
      }}).join('');
      sliderNavItems = [...document.querySelectorAll('.slider-nav-item')];
    }}
    renderDrawerItems();
    function applyLang(nextLang) {{
      const next = nextLang === 'en' ? 'en' : 'ru';
      const root = document.documentElement;
      document.documentElement.lang = next;
      if (root.dataset.titleRu && root.dataset.titleEn) {{
        document.title = next === 'en' ? root.dataset.titleEn : root.dataset.titleRu;
      }}
      document.querySelectorAll('[data-i18n-ru]').forEach(el => {{
        el.textContent = next === 'en' ? el.dataset.i18nEn : el.dataset.i18nRu;
      }});
      document.querySelectorAll('[data-i18n-placeholder-ru]').forEach(el => {{
        el.setAttribute('placeholder', next === 'en' ? el.dataset.i18nPlaceholderEn : el.dataset.i18nPlaceholderRu);
      }});
      document.querySelectorAll('[data-i18n-aria-ru]').forEach(el => {{
        el.setAttribute('aria-label', next === 'en' ? el.dataset.i18nAriaEn : el.dataset.i18nAriaRu);
      }});
    }}
    try {{ applyLang(localStorage.getItem('pdfcompare.lang') || document.documentElement.lang); }} catch (e) {{}}
    function openDrawer() {{
      if (!drawer || isPinned()) return;
      drawer.classList.add('open');
      if (drawerHandle) drawerHandle.setAttribute('aria-expanded', 'true');
    }}
    function closeDrawer() {{
      if (!drawer || isPinned()) return;
      drawer.classList.remove('open');
      if (drawerHandle) drawerHandle.setAttribute('aria-expanded', 'false');
    }}
    const cmpPage = document.getElementById('cmpPage');
    const drawerPin = document.getElementById('drawerPin');
    function isPinned() {{ return cmpPage && cmpPage.classList.contains('pinned'); }}
    function applyPinned(pinned) {{
      if (!cmpPage) return;
      const en = document.documentElement.lang === 'en';
      cmpPage.classList.toggle('pinned', pinned);
      if (drawerPin) {{
        drawerPin.textContent = pinned ? '📌' : '📍';
        drawerPin.setAttribute('aria-label', pinned ? (en ? 'Unpin panel' : 'Открепить панель') : (en ? 'Pin panel' : 'Прикрепить панель'));
      }}
      if (!pinned && drawer) drawer.classList.remove('open');
      try {{ localStorage.setItem('pdfcompare.drawer', pinned ? 'pinned' : 'floating'); }} catch (e) {{}}
    }}
    function togglePin() {{
      applyPinned(!isPinned());
      // The stage width changes by the panel width; re-fit once the
      // grid-template-columns transition (~180ms) settles.
      window.setTimeout(() => fitToWindow(), 220);
    }}
    // Restore persisted pin state (default: pinned).
    try {{
      const stored = localStorage.getItem('pdfcompare.drawer');
      applyPinned(stored ? stored === 'pinned' : true);
    }} catch (e) {{}}
    if (drawerPin) {{ drawerPin.addEventListener('click', togglePin); }}
    if (drawer) {{
      drawer.addEventListener('mouseenter', openDrawer);
      drawer.addEventListener('mouseleave', closeDrawer);
    }}
    if (drawerHandle) {{
      drawerHandle.addEventListener('click', (e) => {{
        e.stopPropagation();
        if (drawer.classList.contains('open')) closeDrawer();
        else {{
          openDrawer();
          if (sliderNavSearch) sliderNavSearch.focus();
        }}
      }});
    }}
    if (sliderNavSearch) {{
      sliderNavSearch.addEventListener('input', () => {{
        const q = sliderNavSearch.value.trim().toLowerCase();
        sliderNavItems.forEach(item => {{
          item.style.display = !q || (item.dataset.label || '').includes(q) ? '' : 'none';
        }});
      }});
    }}
    document.addEventListener('click', (e) => {{
      document.querySelectorAll('[data-dropdown].open').forEach(dropdown => {{
        if (dropdown.contains(e.target)) return;
        dropdown.classList.remove('open');
        const btn = dropdown.querySelector('button');
        if (btn) btn.setAttribute('aria-expanded', 'false');
      }});
    }});
    document.querySelectorAll('[data-dropdown]').forEach(dropdown => {{
      const btn = dropdown.querySelector('button');
      btn.addEventListener('click', (e) => {{
        e.stopPropagation();
        const open = dropdown.classList.toggle('open');
        btn.setAttribute('aria-expanded', open ? 'true' : 'false');
      }});
    }});
    window.addEventListener('keydown', (e) => {{
      const tag = (e.target && e.target.tagName || '').toLowerCase();
      if (e.key === 'Escape') {{
        closeDrawer();
        clearZones();
        if (typeof setAnnotDrawMode === 'function' && annotDrawMode) setAnnotDrawMode(false);
        document.querySelectorAll('[data-dropdown].open').forEach(dropdown => {{
          dropdown.classList.remove('open');
          const btn = dropdown.querySelector('button');
          if (btn) btn.setAttribute('aria-expanded', 'false');
        }});
        return;
      }}
      if (tag === 'input' || tag === 'button') return;
      // Highlight change zones. Z or H (both keyboard layouts; Ctrl+H works too —
      // preventDefault keeps the browser from opening History). Toggles, so the
      // same key clears the rings.
      if (e.key === 'z' || e.key === 'Z' || e.key === 'я' || e.key === 'Я'
          || e.key === 'h' || e.key === 'H' || e.key === 'р' || e.key === 'Р') {{
        e.preventDefault();
        toggleZones();
        return;
      }}
      // Sheet flipping. preventDefault matters when the sheet is zoomed in: the
      // stage is a scroll container, so without it ArrowLeft/Right would pan the
      // image instead of moving to the neighbouring sheet. The targets step one
      // sheet at a time (added/removed included), so nothing is skipped.
      if ((e.key === 'ArrowLeft' || e.key === 'PageUp') && prevSheetHref) {{
        e.preventDefault();
        window.location.href = prevSheetHref;
      }} else if ((e.key === 'ArrowRight' || e.key === 'PageDown') && nextSheetHref) {{
        e.preventDefault();
        window.location.href = nextSheetHref;
      }} else if (e.key === 'Home' && firstSliderHref) {{
        e.preventDefault();
        window.location.href = firstSliderHref;
      }} else if (e.key === 'End' && lastSliderHref) {{
        e.preventDefault();
        window.location.href = lastSliderHref;
      }}
    }});
    const bboxColors = {{
      yellow: {{ border: 'rgba(255,180,0,A)', fill: 'rgba(255,235,120,B)' }},
      pink: {{ border: 'rgba(236,72,153,A)', fill: 'rgba(244,114,182,B)' }},
      green: {{ border: 'rgba(22,163,74,A)', fill: 'rgba(134,239,172,B)' }},
    }};
    let bboxState = {{ enabled: true, color: 'yellow', opacity: 74 }};
    function saveBboxState() {{
      try {{ localStorage.setItem('pdfcompare.bbox', JSON.stringify(bboxState)); }} catch (e) {{}}
    }}
    function applyBboxStyle() {{
      const c = bboxColors[bboxState.color] || bboxColors.yellow;
      const opacityPct = Math.max(0, Math.min(100, Number(bboxState.opacity) || 0));
      const aBorder = Math.min(1, opacityPct / 100);
      const aFill = Math.min(1, opacityPct / 100 * 0.18);
      document.documentElement.style.setProperty('--bbox-border', c.border.replace('A', aBorder.toFixed(2)));
      document.documentElement.style.setProperty('--bbox-fill', c.fill.replace('B', aFill.toFixed(2)));
      document.documentElement.dataset.bboxEnabled = bboxState.enabled ? 'true' : 'false';
      surface.style.setProperty('--bbox-border', c.border.replace('A', aBorder.toFixed(2)));
      surface.style.setProperty('--bbox-fill', c.fill.replace('B', aFill.toFixed(2)));
      bboxLayer.style.display = bboxState.enabled ? '' : 'none';
      document.querySelectorAll('#bboxToggle .seg-toggle-opt').forEach(opt => {{
        opt.classList.toggle('active', (opt.dataset.bbox === 'on') === bboxState.enabled);
      }});
      document.querySelectorAll('.swatch-option').forEach(opt => {{
        opt.classList.toggle('active', opt.dataset.color === bboxState.color);
      }});
      if (bboxOpacity) bboxOpacity.value = String(opacityPct);
      if (bboxOpacityValue) bboxOpacityValue.textContent = opacityPct + '%';
      if (bboxSwatch) bboxSwatch.className = 'bbox-swatch swatch-' + (bboxColors[bboxState.color] ? bboxState.color : 'yellow') + (bboxState.enabled ? '' : ' off');
    }}
    function setBboxState(patch, persist = true) {{
      bboxState = {{ ...bboxState, ...patch }};
      applyBboxStyle();
      if (persist) saveBboxState();
    }}
    document.querySelectorAll('#bboxToggle .seg-toggle-opt').forEach(opt => {{
      opt.addEventListener('click', () => setBboxState({{ enabled: opt.dataset.bbox === 'on' }}));
    }});
    document.querySelectorAll('.swatch-option[data-color]').forEach(opt => {{
      opt.addEventListener('click', () => setBboxState({{ color: opt.dataset.color || 'yellow' }}));
    }});
    if (bboxOpacity) {{
      bboxOpacity.addEventListener('input', () => setBboxState({{ opacity: Number(bboxOpacity.value) || 0 }}));
    }}
    try {{
      const savedBbox = JSON.parse(localStorage.getItem('pdfcompare.bbox') || '{{}}');
      setBboxState({{
        enabled: savedBbox.enabled !== false,
        color: bboxColors[savedBbox.color] ? savedBbox.color : 'yellow',
        opacity: Number.isFinite(Number(savedBbox.opacity)) ? Number(savedBbox.opacity) : 74,
      }}, false);
    }} catch (e) {{
      applyBboxStyle();
    }}
    window.addEventListener('message', (e) => {{
      const data = e.data || {{}};
      if (data.type === 'pdfcompare:bbox') {{
        setBboxState({{ enabled: data.enabled !== false }});
      }}
    }});
    let loaded = 0;
    let naturalW = 0;
    let naturalH = 0;
    function ready() {{ loaded += 1; if (loaded >= 2) initialize(); }}
    function fail() {{ loadMsg.textContent = 'Не удалось загрузить изображение'; }}
    oldImg.onload = ready;
    newImg.onload = ready;
    oldImg.onerror = fail;
    newImg.onerror = fail;
    oldImg.src = oldSrc;
    newImg.src = newSrc;
    function initialize() {{
      naturalW = Math.max(oldImg.naturalWidth || 1, newImg.naturalWidth || 1);
      naturalH = Math.max(oldImg.naturalHeight || 1, newImg.naturalHeight || 1);
      surface.style.display = 'block';
      loadMsg.style.display = 'none';
      buildBboxes();
      applyBboxStyle();
      updateZonesBtn();
      renderAnnots();
      applySplit();
      fitToWindow();
    }}
    function buildBboxes() {{
      bboxLayer.innerHTML = '';
      bboxData.forEach(b => {{
        const x = Number(b.x || 0);
        const y = Number(b.y || 0);
        const bw = Number(b.w || 0);
        const bh = Number(b.h || 0);
        if (bw <= 1 || bh <= 1) return;
        const box = document.createElement('div');
        box.className = 'bbox';
        box.style.left = (100 * x / naturalW) + '%';
        box.style.top = (100 * y / naturalH) + '%';
        box.style.width = (100 * bw / naturalW) + '%';
        box.style.height = (100 * bh / naturalH) + '%';
        bboxLayer.appendChild(box);
      }});
    }}
    function setZoomPercent(v) {{
      const clamped = Math.max(1, Math.min(500, Math.round(v)));
      zoom.value = String(clamped);
      applyZoom();
    }}
    function applyZoom() {{
      if (!naturalW || !naturalH) return;
      const z = Number(zoom.value) / 100;
      zoomVal.textContent = Math.round(z * 100) + '%';
      surface.style.width = Math.max(1, Math.round(naturalW * z)) + 'px';
      surface.style.height = Math.max(1, Math.round(naturalH * z)) + 'px';
    }}
    function fitToWindow() {{
      if (!naturalW || !naturalH) return;
      const pad = 16;
      const sx = Math.max(0.01, (stage.clientWidth - pad) / naturalW);
      const sy = Math.max(0.01, (stage.clientHeight - pad) / naturalH);
      const s = Math.max(0.01, Math.min(sx, sy));
      setZoomPercent(s * 100);
    }}
    function setSplitFromClientX(clientX) {{
      const rect = surface.getBoundingClientRect();
      if (!rect.width) return;
      const x = Math.max(0, Math.min(rect.width, clientX - rect.left));
      const pct = (x / rect.width) * 100;
      slider.value = String(pct);
      applySplit();
    }}
    function applySplit() {{
      const pct = Math.max(0, Math.min(100, Number(slider.value) || 0));
      oldLayer.style.clipPath = `inset(0 ${{100 - pct}}% 0 0)`;
      divider.style.left = pct + '%';
      slider.style.setProperty('--split-pct', pct + '%');
    }}
    let draggingSplit = false;
    let panning = false;
    let panStartX = 0;
    let panStartY = 0;
    let panStartScrollLeft = 0;
    let panStartScrollTop = 0;
    let selecting = false;
    const zoomRect = document.getElementById('zoomRect');
    let selStartClientX = 0;
    let selStartClientY = 0;
    function clientToSurfaceXY(clientX, clientY) {{
      const rect = surface.getBoundingClientRect();
      return {{ x: clientX - rect.left, y: clientY - rect.top, rect: rect }};
    }}
    function zoomToClientRect(startX, startY, endX, endY) {{
      // Convert a screen-space drag rectangle (relative to the surface) into
      // an image-pixel rectangle, then fit it into the viewport.
      const left = Math.min(startX, endX);
      const top = Math.min(startY, endY);
      const w = Math.abs(endX - startX);
      const h = Math.abs(endY - startY);
      if (w < 4 || h < 4) return;  // ignore accidental clicks
      const rect = surface.getBoundingClientRect();
      if (!rect.width || !rect.height || !naturalW || !naturalH) return;
      // Image-pixel rectangle captured by this drag.
      const imgX = (left / rect.width) * naturalW;
      const imgY = (top / rect.height) * naturalH;
      const imgW = (w / rect.width) * naturalW;
      const imgH = (h / rect.height) * naturalH;
      // Fit the selected image rect into the stage viewport (with padding).
      const pad = 16;
      const sx = Math.max(0.01, (stage.clientWidth - pad) / imgW);
      const sy = Math.max(0.01, (stage.clientHeight - pad) / imgH);
      const s = Math.max(0.01, Math.min(5.0, Math.min(sx, sy)));
      setZoomPercent(s * 100);
      // After resize, center the selected rect in the viewport.
      const z = s;
      stage.scrollLeft = Math.max(0, imgX * z - (stage.clientWidth - imgW * z) / 2);
      stage.scrollTop = Math.max(0, imgY * z - (stage.clientHeight - imgH * z) / 2);
    }}
    surface.addEventListener('mousedown', (e) => {{
      if (annotDrawMode && e.button === 0) {{
        // In note mode the left button draws an annotation box instead of moving
        // the split; preventDefault suppresses the image drag-select.
        e.preventDefault();
        annotDrawing = true;
        annotStartX = e.clientX;
        annotStartY = e.clientY;
        const pt = clientToSurfaceXY(e.clientX, e.clientY);
        annotDraft.className = 'annot-draft ' + annotColor;
        annotDraft.style.display = 'block';
        annotDraft.style.left = pt.x + 'px';
        annotDraft.style.top = pt.y + 'px';
        annotDraft.style.width = '0px';
        annotDraft.style.height = '0px';
        return;
      }}
      if (e.button === 2) {{
        panning = true;
        stage.classList.add('panning');
        panStartX = e.clientX;
        panStartY = e.clientY;
        panStartScrollLeft = stage.scrollLeft;
        panStartScrollTop = stage.scrollTop;
        e.preventDefault();
        return;
      }}
      if (e.button === 1) {{
        // Middle button: start a zoom-by-rectangle selection.
        // preventDefault is essential to suppress the browser autoscroll cursor.
        e.preventDefault();
        selecting = true;
        selStartClientX = e.clientX;
        selStartClientY = e.clientY;
        zoomRect.style.display = 'block';
        const p = clientToSurfaceXY(e.clientX, e.clientY);
        zoomRect.style.left = p.x + 'px';
        zoomRect.style.top = p.y + 'px';
        zoomRect.style.width = '0px';
        zoomRect.style.height = '0px';
        return;
      }}
      if (e.button !== 0) return;
      draggingSplit = true;
      stage.classList.add('dragging');
      setSplitFromClientX(e.clientX);
    }});
    window.addEventListener('mousemove', (e) => {{
      if (annotDrawing) {{
        const s = clientToSurfaceXY(annotStartX, annotStartY);
        const c = clientToSurfaceXY(e.clientX, e.clientY);
        annotDraft.style.left = Math.min(s.x, c.x) + 'px';
        annotDraft.style.top = Math.min(s.y, c.y) + 'px';
        annotDraft.style.width = Math.abs(c.x - s.x) + 'px';
        annotDraft.style.height = Math.abs(c.y - s.y) + 'px';
        return;
      }}
      if (selecting) {{
        const start = clientToSurfaceXY(selStartClientX, selStartClientY);
        const cur = clientToSurfaceXY(e.clientX, e.clientY);
        const left = Math.min(start.x, cur.x);
        const top = Math.min(start.y, cur.y);
        const w = Math.abs(cur.x - start.x);
        const h = Math.abs(cur.y - start.y);
        zoomRect.style.left = left + 'px';
        zoomRect.style.top = top + 'px';
        zoomRect.style.width = w + 'px';
        zoomRect.style.height = h + 'px';
        return;
      }}
      if (panning) {{
        stage.scrollLeft = panStartScrollLeft - (e.clientX - panStartX);
        stage.scrollTop = panStartScrollTop - (e.clientY - panStartY);
        return;
      }}
      if (!draggingSplit) return;
      setSplitFromClientX(e.clientX);
    }});
    window.addEventListener('mouseup', (e) => {{
      if (annotDrawing) {{
        annotDrawing = false;
        annotDraft.style.display = 'none';
        const rect = surface.getBoundingClientRect();
        const s = clientToSurfaceXY(annotStartX, annotStartY);
        const c = clientToSurfaceXY(e.clientX, e.clientY);
        const left = Math.min(s.x, c.x);
        const top = Math.min(s.y, c.y);
        const w = Math.abs(c.x - s.x);
        const h = Math.abs(c.y - s.y);
        if (w >= 5 && h >= 5 && rect.width && rect.height && naturalW && naturalH) {{
          addAnnot(left / rect.width * naturalW, top / rect.height * naturalH, w / rect.width * naturalW, h / rect.height * naturalH);
        }}
        return;
      }}
      if (selecting) {{
        selecting = false;
        zoomRect.style.display = 'none';
        const start = clientToSurfaceXY(selStartClientX, selStartClientY);
        const cur = clientToSurfaceXY(e.clientX, e.clientY);
        zoomToClientRect(start.x, start.y, cur.x, cur.y);
        return;
      }}
      if (draggingSplit) {{
        draggingSplit = false;
        stage.classList.remove('dragging');
      }}
      if (panning) {{
        panning = false;
        stage.classList.remove('panning');
      }}
    }});
    stage.addEventListener('contextmenu', (e) => {{
      e.preventDefault();
    }});
    surface.addEventListener('touchstart', (e) => {{
      if (!e.touches || !e.touches.length) return;
      draggingSplit = true;
      stage.classList.add('dragging');
      setSplitFromClientX(e.touches[0].clientX);
      e.preventDefault();
    }}, {{ passive: false }});
    window.addEventListener('touchmove', (e) => {{
      if (!draggingSplit || !e.touches || !e.touches.length) return;
      setSplitFromClientX(e.touches[0].clientX);
      e.preventDefault();
    }}, {{ passive: false }});
    window.addEventListener('touchend', () => {{
      draggingSplit = false;
      stage.classList.remove('dragging');
    }});
    stage.addEventListener('wheel', (e) => {{
      if (!e.ctrlKey) return;
      e.preventDefault();
      const delta = e.deltaY < 0 ? 6 : -6;
      setZoomPercent(Number(zoom.value) + delta);
    }}, {{ passive: false }});
    slider.addEventListener('input', applySplit);
    zoom.addEventListener('input', () => setZoomPercent(Number(zoom.value)));
    fitBtn.addEventListener('click', fitToWindow);
    oneBtn.addEventListener('click', () => setZoomPercent(100));
    function zoomByStep(dir) {{
      // A finer step than the wheel's fixed ±6: 2% of the current zoom (min 1pp),
      // so repeated clicks creep in/out for precise framing when the mouse wheel
      // is set to a coarse scroll step.
      const cur = Number(zoom.value) || 100;
      const step = Math.max(1, Math.round(cur * 0.02));
      setZoomPercent(cur + dir * step);
    }}
    if (zoomInBtn) zoomInBtn.addEventListener('click', () => zoomByStep(1));
    if (zoomOutBtn) zoomOutBtn.addEventListener('click', () => zoomByStep(-1));
    // --- "Показать зоны": briefly pulse rings over where changes cluster. ---
    // Reuses bboxData (image-pixel rects) and the surface coordinate space, so
    // the rings land exactly on the changes and pan/zoom with the sheet.
    function usableBoxes() {{
      return bboxData
        .map(b => ({{ x: Number(b.x) || 0, y: Number(b.y) || 0, w: Number(b.w) || 0, h: Number(b.h) || 0 }}))
        .filter(b => b.w > 1 && b.h > 1);
    }}
    function clusterZones(boxes, gap) {{
      // Union-find: two boxes join a zone when their rects (grown by `gap`) touch.
      const n = boxes.length;
      const parent = boxes.map((_, i) => i);
      function find(i) {{ while (parent[i] !== i) {{ parent[i] = parent[parent[i]]; i = parent[i]; }} return i; }}
      function near(a, b) {{
        return a.x <= b.x + b.w + gap && a.x + a.w >= b.x - gap
            && a.y <= b.y + b.h + gap && a.y + a.h >= b.y - gap;
      }}
      for (let i = 0; i < n; i++) {{
        for (let j = i + 1; j < n; j++) {{
          if (near(boxes[i], boxes[j])) parent[find(i)] = find(j);
        }}
      }}
      const groups = {{}};
      for (let i = 0; i < n; i++) {{
        const r = find(i);
        (groups[r] = groups[r] || []).push(boxes[i]);
      }}
      return Object.keys(groups).map(k => {{
        let x1 = Infinity, y1 = Infinity, x2 = -Infinity, y2 = -Infinity;
        groups[k].forEach(b => {{
          x1 = Math.min(x1, b.x); y1 = Math.min(y1, b.y);
          x2 = Math.max(x2, b.x + b.w); y2 = Math.max(y2, b.y + b.h);
        }});
        return {{ x1: x1, y1: y1, x2: x2, y2: y2 }};
      }});
    }}
    let zoneTimer = null;
    function clearZones() {{
      if (zoneTimer) {{ window.clearTimeout(zoneTimer); zoneTimer = null; }}
      zoneLayer.innerHTML = '';
      zoneLayer.classList.remove('active');
      zoneCounter.classList.remove('show');
      zoneCounter.textContent = '';
    }}
    function highlightZones() {{
      if (!naturalW || !naturalH) return;
      const boxes = usableBoxes();
      if (!boxes.length) return;
      clearZones();
      // Highlight at the CURRENT zoom/pan — no forced fit. The rings live in the
      // surface's coordinate space (percent of the sheet), so they land on the
      // changes at whatever scale you are viewing: zoom into an area, press Zones
      // again, and it rings the changes right there instead of snapping back to
      // the whole-sheet view. Use Fit first if you want the global overview.
      const gap = Math.max(naturalW, naturalH) * 0.05;
      const pad = Math.max(naturalW, naturalH) * 0.012;  // a little breathing room around the box
      const zones = clusterZones(boxes, gap);
      zones.forEach(c => {{
        // A tight bounding box of the whole zone: it wraps exactly the changed
        // area (a 100% hit), instead of a circle that inflates to max side and
        // spills off the sheet when a change runs along an edge.
        const x = Math.max(0, c.x1 - pad);
        const y = Math.max(0, c.y1 - pad);
        const w = Math.min(naturalW, c.x2 + pad) - x;
        const h = Math.min(naturalH, c.y2 + pad) - y;
        const ring = document.createElement('div');
        ring.className = 'zone-ring';
        ring.style.left = (100 * x / naturalW) + '%';
        ring.style.top = (100 * y / naturalH) + '%';
        ring.style.width = (100 * w / naturalW) + '%';
        ring.style.height = (100 * h / naturalH) + '%';
        zoneLayer.appendChild(ring);
      }});
      zoneLayer.classList.add('active');
      const en = document.documentElement.lang === 'en';
      zoneCounter.textContent = (en ? 'Change zones: ' : 'Зон с изменениями: ') + zones.length;
      zoneCounter.classList.add('show');
      zoneTimer = window.setTimeout(clearZones, 3200);
    }}
    function updateZonesBtn() {{
      if (!zonesBtn) return;
      zonesBtn.disabled = usableBoxes().length === 0;
    }}
    function toggleZones() {{
      if (zoneLayer.classList.contains('active')) clearZones();
      else highlightZones();
    }}
    if (zonesBtn) {{
      zonesBtn.addEventListener('click', toggleZones);
    }}
    // --- Local annotations: green/yellow/red boxes + a note, per run + sheet. ---
    // Stored in localStorage, namespaced by the run folder in the URL and the sheet
    // number, so notes persist across reloads and never collide between runs. They
    // are browser-local: they do NOT yet survive a report re-render (that needs the
    // notes written back into the run and re-emitted) — a deliberate next step.
    const annotLayer = document.getElementById('annotLayer');
    const annotDraft = document.getElementById('annotDraft');
    const annotBtn = document.getElementById('annotBtn');
    const annotShowBtn = document.getElementById('annotShowBtn');
    const annotCount = document.getElementById('annotCount');
    const annotKey = 'pdfcompare.annot:' + location.pathname.replace(/[^/]*$/, '') + ':' + currentSeq;
    let annots = [];
    let annotColor = 'yellow';
    let annotDrawMode = false;
    let annotVisible = true;
    let annotDrawing = false;
    let annotStartX = 0;
    let annotStartY = 0;
    function loadAnnots() {{
      try {{ annots = JSON.parse(localStorage.getItem(annotKey) || '[]'); }} catch (e) {{ annots = []; }}
      if (!Array.isArray(annots)) annots = [];
    }}
    function saveAnnots() {{
      try {{ localStorage.setItem(annotKey, JSON.stringify(annots)); }} catch (e) {{}}
    }}
    function annotNewId() {{ return 'a' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6); }}
    function updateAnnotCount() {{
      if (!annotCount) return;
      const en = document.documentElement.lang === 'en';
      annotCount.textContent = annots.length ? ((en ? 'Notes: ' : 'Заметок: ') + annots.length) : '';
    }}
    function updateAnnotShowBtn() {{
      if (!annotShowBtn) return;
      const en = document.documentElement.lang === 'en';
      annotShowBtn.textContent = annotVisible ? (en ? 'Hide notes' : 'Скрыть заметки') : (en ? 'Show notes' : 'Показать заметки');
    }}
    function updateAnnotPalette() {{
      document.querySelectorAll('[data-annot-color]').forEach(b => b.classList.toggle('active', b.dataset.annotColor === annotColor));
    }}
    function removeAnnot(id) {{ annots = annots.filter(a => a.id !== id); saveAnnots(); renderAnnots(); }}
    function editAnnot(id) {{
      const a = annots.find(x => x.id === id);
      if (!a) return;
      const en = document.documentElement.lang === 'en';
      const text = window.prompt(en ? 'Note text:' : 'Текст заметки:', a.text || '');
      if (text === null) return;
      a.text = text;
      saveAnnots(); renderAnnots();
    }}
    function renderAnnots() {{
      if (!annotLayer) return;
      annotLayer.innerHTML = '';
      if (naturalW && naturalH) {{
        annots.forEach(a => {{
          const box = document.createElement('div');
          box.className = 'annot-box ' + (a.color || 'yellow');
          box.style.left = (100 * a.x / naturalW) + '%';
          box.style.top = (100 * a.y / naturalH) + '%';
          box.style.width = (100 * a.w / naturalW) + '%';
          box.style.height = (100 * a.h / naturalH) + '%';
          if (a.text) {{
            const note = document.createElement('div');
            note.className = 'annot-note';
            note.textContent = a.text;
            box.appendChild(note);
          }}
          const del = document.createElement('button');
          del.className = 'annot-del';
          del.type = 'button';
          del.textContent = '×';
          del.addEventListener('click', ev => {{ ev.stopPropagation(); removeAnnot(a.id); }});
          box.appendChild(del);
          box.addEventListener('dblclick', ev => {{ ev.stopPropagation(); editAnnot(a.id); }});
          annotLayer.appendChild(box);
        }});
      }}
      annotLayer.classList.toggle('annot-hidden', !annotVisible);
      updateAnnotCount();
    }}
    function addAnnot(x, y, w, h) {{
      const a = {{ id: annotNewId(), x: x, y: y, w: w, h: h, color: annotColor, text: '' }};
      annots.push(a);
      saveAnnots(); renderAnnots();
      editAnnot(a.id);
    }}
    function setAnnotDrawMode(on) {{
      annotDrawMode = on;
      if (on) annotVisible = true;
      stage.classList.toggle('annot-mode', on);
      if (annotBtn) annotBtn.classList.toggle('active', on);
      updateAnnotShowBtn();
      renderAnnots();
    }}
    if (annotBtn) annotBtn.addEventListener('click', () => setAnnotDrawMode(!annotDrawMode));
    if (annotShowBtn) annotShowBtn.addEventListener('click', () => {{ annotVisible = !annotVisible; updateAnnotShowBtn(); renderAnnots(); }});
    document.querySelectorAll('[data-annot-color]').forEach(b => b.addEventListener('click', () => {{
      annotColor = b.dataset.annotColor || 'yellow';
      updateAnnotPalette();
      if (!annotDrawMode) setAnnotDrawMode(true);
    }}));
    loadAnnots();
    updateAnnotPalette();
    updateAnnotShowBtn();
    window.addEventListener('resize', () => {{
      if (Number(zoom.value) <= 5) fitToWindow();
    }});
  </script>
</body>
</html>"""
        (views_dir / slider_file).write_text(slider_html, encoding="utf-8")


def _write_page_views(
    ctx: _ReportContext,
    p: dict,
    view_idx: int,
    status_counts: dict[str, int],
) -> None:
    """Write both pages for one sheet: the detail view and the slider view."""
    strings, badges = ctx.strings, ctx.badges
    lang = strings.lang
    tr_attr = strings.tr_attr
    i18n_span = strings.i18n_span
    i18n_span_text = strings.i18n_span_text
    i18n_aria = strings.i18n_aria
    i18n_attr = strings.i18n_attr
    title_attrs = strings.title_attrs
    title_text = strings.title_text
    status_badge_html = badges.status_badge_html
    level_badge_html = badges.level_badge_html
    is_mixed_precision_page = badges.is_mixed_precision_page
    page_precision_text = badges.page_precision_text
    precision_badge_html = badges.precision_badge_html
    bundle_dir, views_dir = ctx.bundle_dir, ctx.views_dir
    pages_records = ctx.pages_records
    changed_cnt = status_counts["changed"]
    added_cnt = status_counts["added"]
    removed_cnt = status_counts["removed"]
    unchanged_cnt = status_counts["unchanged"]

    diff_txt = "-" if p["diff_metric"] is None else f'{p["diff_metric"]:.3f}%'
    fg_diff_txt = "-" if p.get("diff_foreground_metric") is None else f'{float(p["diff_foreground_metric"]):.2f}%'
    area_txt = "-" if p.get("diff_area_mm2") is None else f'{float(p["diff_area_mm2"]):.1f} mm²'
    old_src = f"../{p['assets']['hires_old']}" if p["assets"]["hires_old"] else None
    new_src = f"../{p['assets']['hires_new']}" if p["assets"]["hires_new"] else None
    diff_src = f"../{p['assets']['hires_diff']}" if p["assets"]["hires_diff"] else None
    prev_link = p["prev_view_file"]
    next_link = p["next_view_file"]
    slider_file = p["slider_file"]
    pair_rel = None
    bboxes_data: list[dict] = []
    if p["assets"]["hires_old"]:
        pair_rel = Path(p["assets"]["hires_old"]).parent
    elif p["assets"]["hires_new"]:
        pair_rel = Path(p["assets"]["hires_new"]).parent
    if pair_rel is not None and (bundle_dir / pair_rel / "bboxes.json").exists():
        try:
            bboxes_data = json.loads((bundle_dir / pair_rel / "bboxes.json").read_text(encoding="utf-8"))
        except Exception:
            bboxes_data = []

    status_tag = str(p.get("_status_tag") or "CHANGED")
    level_tag = str(p.get("_level_tag") or "")
    boxes_text = "—" if p.get("bboxes_count") is None else str(int(p["bboxes_count"]))
    detail_precision_badge = precision_badge_html(p)
    precision_ru, precision_en = page_precision_text(p)
    detail_precision_text = (
        f'<span class="muted">{i18n_span_text(precision_ru, precision_en)}</span>'
        if is_mixed_precision_page(p)
        else ""
    )

    def figure_html(src: str | None, label: str, cls: str = "", bbox_off_src: str | None = None) -> str:
        data_attrs = ""
        if bbox_off_src and src:
            data_attrs = (
                f' data-bbox-on-src="{html.escape(src, quote=True)}"'
                f' data-bbox-off-src="{html.escape(bbox_off_src, quote=True)}"'
            )
        media = (
            f'<img loading="lazy" src="{html.escape(src, quote=True)}" alt="{html.escape(label.lower(), quote=True)} sheet"{data_attrs}/>'
            if src
            else f'<div class="noimg">{i18n_span("no_data")}</div>'
        )
        label_attr = html.escape(label, quote=True)
        return (
            f'<figure class="{html.escape(cls, quote=True)}">'
            f'<span class="cap-pill" data-i18n-ru="{label_attr}" data-i18n-en="{label_attr}">{html.escape(label)}</span>'
            f"{media}</figure>"
        )

    external_items: list[str] = []
    for label, ru_label, en_label, src in (
        ("OLD", "Старый", "Old", old_src),
        ("NEW", "Новый", "New", new_src),
        ("DIFF", "Отличия", "Diff", diff_src),
    ):
        if src:
            external_items.append(
                f'<button type="button" class="open-ext" data-src="{html.escape(src, quote=True)}">'
                f'<span>{i18n_span_text(ru_label, en_label)}</span><span class="badge lv-empty">{label}</span></button>'
            )
    external_menu = "".join(external_items) if external_items else f'<button type="button" disabled>{i18n_span("no_data")}</button>'
    prev_top = (
        f'<a class="btn" href="{html.escape(prev_link, quote=True)}">{report_icon("chevron-left", size=16)}{i18n_span_text("Назад", "Previous")}</a>'
        if prev_link
        else f'<button class="btn" type="button" disabled>{report_icon("chevron-left", size=16)}{i18n_span_text("Назад", "Previous")}</button>'
    )
    next_top = (
        f'<a class="btn primary" href="{html.escape(next_link, quote=True)}">{i18n_span_text("Вперёд", "Next")}{report_icon("chevron-right", size=16)}</a>'
        if next_link
        else f'<button class="btn primary" type="button" disabled>{i18n_span_text("Вперёд", "Next")}{report_icon("chevron-right", size=16)}</button>'
    )
    primary_slider_action = (
        f'<a class="btn primary btn-xl btn-slider" id="primarySliderLink" href="{html.escape(slider_file, quote=True)}">'
        f'{report_icon("arrow-left-right", size=20)}'
        f'{i18n_span_text("Открыть в слайдере", "Open in slider")}'
        f'<span class="kbd">{i18n_span_text("Enter", "Enter")}</span></a>'
        if slider_file
        else f'<button class="btn primary btn-xl btn-slider" type="button" disabled>'
        f'{report_icon("arrow-left-right", size=20)}'
        f'{i18n_span_text("Слайдер недоступен", "Slider unavailable")}</button>'
    )
    view_title_ru = f"Лист {view_idx} / {len(pages_records)} — PDFCompare"
    view_title_en = f"Sheet {view_idx} / {len(pages_records)} — PDFCompare"
    detail_html = f"""<!doctype html>
<html lang="{lang}" {title_attrs(view_title_ru, view_title_en)}>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>{title_text(view_title_ru, view_title_en)}</title>
  <script>
    try {{
      const savedTheme = localStorage.getItem('pdfcompare.theme');
      if (savedTheme === 'dark') document.documentElement.dataset.theme = 'dark';
      const savedLang = localStorage.getItem('pdfcompare.lang');
      if (savedLang === 'en' || savedLang === 'ru') document.documentElement.lang = savedLang;
    }} catch (e) {{}}
  </script>
  <style>
{REPORT_CSS_TOKENS}
{CSS_VIEW}
  </style>
</head>
<body>
  <header class="toolbar" {i18n_aria("Навигация по листу", "Sheet navigation")}>
    <div><a class="btn home-neon" href="../index.html" {i18n_aria("В начало — к матрице изменений", "Home — to the change matrix")}>{report_icon("home", size=16)}{i18n_span_text("К матрице изменений", "Back to change matrix")}</a></div>
    <div class="toolbar-center">
      <span class="sheet-title">{i18n_span_text(f"Лист {view_idx} из {len(pages_records)}", f"Sheet {view_idx} of {len(pages_records)}")}</span>
      {status_badge_html(status_tag)}
      {level_badge_html(level_tag) if level_tag else ""}
      {detail_precision_badge}
      <span class="muted">{i18n_span_text(f"· заполнено {fg_diff_txt} · лист {diff_txt} · {area_txt} · {boxes_text} областей", f"· drawn {fg_diff_txt} · sheet {diff_txt} · {area_txt} · {boxes_text} areas")}</span>
      {detail_precision_text}
    </div>
    <div class="toolbar-right">
      {prev_top}
      {next_top}
      <span class="muted">{i18n_span_text(f"Лист {view_idx}/{len(pages_records)}", f"Sheet {view_idx}/{len(pages_records)}")}</span>
    </div>
  </header>

  <div class="body-grid">
    <aside class="side">
      <div class="side-summary">
        <div class="side-summary-title">{i18n_span_text("Сводка", "Summary")}</div>
        <ul class="side-summary-list">
          <li><span class="dot dot-changed"></span><span>{i18n_span_text("Изменены", "Changed")}</span><b>{changed_cnt}</b></li>
          <li><span class="dot dot-added"></span><span>{i18n_span_text("Добавлены", "Added")}</span><b>{added_cnt}</b></li>
          <li><span class="dot dot-removed"></span><span>{i18n_span_text("Удалены", "Removed")}</span><b>{removed_cnt}</b></li>
          <li><span class="dot dot-unchanged"></span><span>{i18n_span_text("Без изменений", "Unchanged")}</span><b>{unchanged_cnt}</b></li>
        </ul>
      </div>
      <div class="section-title">{i18n_span_text("НАВИГАЦИЯ ПО ЛИСТАМ", "SHEET NAVIGATION")}</div>
      <label class="search-wrap">
        {i18n_span("search_sheet", "sr-only")}
        {report_icon("search", size=16)}
        <input id="search" class="search" {i18n_attr("search_sheet", "placeholder")} placeholder="{tr_attr("search_sheet")}"/>
      </label>
      <div id="navList" class="nav-list"></div>
    </aside>

    <main class="view-area">
      <div class="view-tools">
        <div class="view-primary">
          {primary_slider_action}
          <div class="primary-hint">{i18n_span_text("Главный режим просмотра — split-view с движком сравнения", "Primary view — side-by-side compare slider")}</div>
        </div>
        <div class="view-modes">
          <span class="view-modes-label">{i18n_span_text("Другой режим:", "Other mode:")}</span>
          <div class="tabs" role="tablist" {i18n_aria("Режим просмотра", "View mode")}>
            <button type="button" class="tab active" data-mode="split">{i18n_span_text("Сравнение", "Split")}</button>
            <button type="button" class="tab" data-mode="old">{i18n_span_text("OLD", "OLD")}</button>
            <button type="button" class="tab" data-mode="new">{i18n_span_text("NEW", "NEW")}</button>
            <button type="button" class="tab" data-mode="diff">{i18n_span_text("DIFF", "DIFF")}</button>
          </div>
          <div class="dropdown" data-dropdown>
            <button class="btn" type="button" aria-haspopup="menu" aria-expanded="false">{report_icon("external-link", size=16)}{i18n_span_text("Открыть внешне", "Open externally")}</button>
            <div class="dropdown-menu" role="menu">{external_menu}</div>
          </div>
        </div>
      </div>

      <section class="preview-mode active" data-panel="split">
        <div class="split-grid">
          <div class="left-stack">
            {figure_html(old_src, "OLD")}
            {figure_html(new_src, "NEW")}
          </div>
          <div class="diff-view">{figure_html(diff_src, "DIFF", "diff-figure", new_src)}</div>
        </div>
      </section>
      <section class="preview-mode" data-panel="old"><div class="single-view">{figure_html(old_src, "OLD")}</div></section>
      <section class="preview-mode" data-panel="new"><div class="single-view">{figure_html(new_src, "NEW")}</div></section>
      <section class="preview-mode" data-panel="diff"><div class="single-view">{figure_html(diff_src, "DIFF", "", new_src)}</div></section>
    </main>
  </div>

  <script src="../{NAV_DATA_FILE}"></script>
  <script>
    const current = "{html.escape(p['view_file'], quote=True)}";
    const primarySliderHref = {json.dumps(slider_file or "")};
    const NAV = window.PDFCOMPARE_NAV || {{ pages: [], badges: {{}}, navOkIcon: '' }};
    function escapeHtml(value) {{
      return String(value ?? '').replace(/[&<>"']/g, ch => ({{
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;',
      }}[ch]));
    }}
    // The sheet list is the same on every detail page, so it ships once as
    // nav-data.js and is rendered here — inlining it into all N pages was PDF-008.
    const navList = document.getElementById('navList');
    if (navList) {{
      navList.innerHTML = NAV.pages.map(sheet => {{
        const badge = sheet.status === 'UNCHANGED'
          ? NAV.navOkIcon
          : (NAV.badges[sheet.status] || NAV.badges.CHANGED || '');
        return '<a class="nav-item" data-label="' + escapeHtml(sheet.navSearch) + '"'
          + ' title="' + escapeHtml(sheet.navLabel) + '"'
          + ' href="' + escapeHtml(sheet.viewFile) + '">'
          + '<span class="nav-main">' + escapeHtml(sheet.navShort) + '</span>' + badge + '</a>';
      }}).join('');
    }}
    document.querySelectorAll('.nav-item').forEach(a => {{
      const href = a.getAttribute('href');
      if (href === current) a.classList.add('current');
    }});
    const inp = document.getElementById('search');
    const items = [...document.querySelectorAll('.nav-item')];
    inp.addEventListener('input', () => {{
      const q = inp.value.trim().toLowerCase();
      items.forEach(it => {{
        it.style.display = !q || it.dataset.label.includes(q) ? '' : 'none';
      }});
    }});
    function applyLang(nextLang) {{
      const next = nextLang === 'en' ? 'en' : 'ru';
      const root = document.documentElement;
      document.documentElement.lang = next;
      if (root.dataset.titleRu && root.dataset.titleEn) {{
        document.title = next === 'en' ? root.dataset.titleEn : root.dataset.titleRu;
      }}
      document.querySelectorAll('[data-i18n-ru]').forEach(el => {{
        el.textContent = next === 'en' ? el.dataset.i18nEn : el.dataset.i18nRu;
      }});
      document.querySelectorAll('[data-i18n-placeholder-ru]').forEach(el => {{
        el.setAttribute('placeholder', next === 'en' ? el.dataset.i18nPlaceholderEn : el.dataset.i18nPlaceholderRu);
      }});
      document.querySelectorAll('[data-i18n-aria-ru]').forEach(el => {{
        el.setAttribute('aria-label', next === 'en' ? el.dataset.i18nAriaEn : el.dataset.i18nAriaRu);
      }});
    }}
    try {{ applyLang(localStorage.getItem('pdfcompare.lang') || document.documentElement.lang); }} catch (e) {{}}
    let currentMode = 'split';
    document.querySelectorAll('.tab').forEach(tab => {{
      tab.addEventListener('click', () => {{
        if (tab.disabled) return;
        const mode = tab.dataset.mode;
        currentMode = mode;
        document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t === tab));
        document.querySelectorAll('.preview-mode').forEach(panel => {{
          panel.classList.toggle('active', panel.dataset.panel === mode);
        }});
      }});
    }});
    document.querySelectorAll('[data-dropdown]').forEach(dropdown => {{
      const btn = dropdown.querySelector('button');
      btn.addEventListener('click', (e) => {{
        e.stopPropagation();
        const open = dropdown.classList.toggle('open');
        btn.setAttribute('aria-expanded', open ? 'true' : 'false');
      }});
    }});
    document.addEventListener('click', () => {{
      document.querySelectorAll('[data-dropdown].open').forEach(dropdown => {{
        dropdown.classList.remove('open');
        const btn = dropdown.querySelector('button');
        if (btn) btn.setAttribute('aria-expanded', 'false');
      }});
    }});
    function toWinPath(rel) {{
      try {{
        const u = new URL(rel, window.location.href);
        if (u.protocol !== 'file:') return null;
        let p = decodeURIComponent(u.pathname);
        if (/^\\/[A-Za-z]:/.test(p)) p = p.slice(1);
        return p.replace(/\\//g, '\\\\');
      }} catch (e) {{
        return null;
      }}
    }}
    document.querySelectorAll('.open-ext').forEach(btn => {{
      btn.addEventListener('click', () => {{
        const rel = btn.dataset.src;
        const wp = toWinPath(rel);
        if (!wp) {{
          window.open(rel, '_blank');
          return;
        }}
        const uri = 'ms-photos:viewer?fileName=' + encodeURIComponent(wp);
        window.location.href = uri;
      }});
    }});
    document.addEventListener('keydown', (e) => {{
      const tag = (e.target && e.target.tagName || '').toLowerCase();
      if (!primarySliderHref || tag === 'input' || tag === 'textarea' || tag === 'select') return;
      if (e.key === 'Enter') {{
        window.location.href = primarySliderHref;
      }}
    }});
  </script>
</body>
</html>
"""
    (views_dir / p["view_file"]).write_text(detail_html, encoding="utf-8")

    _write_slider_view(
        ctx,
        p,
        view_idx,
        slider_file=slider_file,
        old_src=old_src,
        new_src=new_src,
        diff_txt=diff_txt,
        fg_diff_txt=fg_diff_txt,
        status_tag=status_tag,
        level_tag=level_tag,
        bboxes_data=bboxes_data,
    )


def generate_html_report(
    run_dir: Path,
    file_a: Path,
    file_b: Path,
    details: Sequence[dict],
    high_dpi: int,
    stroke_tol_px: float,
    report_lang: str = "ru",
    progress_cb: Callable[[float, str], None] | None = None,
) -> Path:
    def emit(pct: float, msg: str) -> None:
        if progress_cb is not None:
            progress_cb(float(max(0.0, min(100.0, pct))), msg)

    # Localized fragments and page badges live in html_fragments; bind them to
    # local names so the markup below reads as plain calls.
    strings = ReportI18n(report_lang)
    lang = strings.lang
    t = strings.t

    emit(2, t["progress_prepare_bundle"])
    final_bundle_dir = report_dir(run_dir)
    bundle_dir = internal_dir(run_dir) / f".report_{uuid4().hex}"
    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)
    bundle_dir.mkdir(parents=True, exist_ok=True)

    pages_root = find_pages_dir(run_dir)
    if not pages_root.exists():
        raise RuntimeError(f"Не найдена папка страниц: {pages_root}")
    thumbs_dir = bundle_dir / "assets" / "thumbs"
    thumbs_dir.mkdir(parents=True, exist_ok=True)

    with fitz.open(file_a) as da, fitz.open(file_b) as db:
        page_count_a = len(da)
        page_count_b = len(db)

    pages_records = _prepare_pages_records(
        details,
        file_a,
        file_b,
        pages_root,
        bundle_dir,
        thumbs_dir,
        t,
        progress_cb=lambda done, total: emit(6 + 58 * (done / total), t["progress_prepare_pages"].format(idx=done, total=total)),
    )

    pages_records.sort(key=lambda x: (x["b_index"] is None, x["b_index"] or 0, x["seq"]))
    for idx, p in enumerate(pages_records):
        p["view_ord"] = idx + 1
        p["prev_view_file"] = pages_records[idx - 1]["view_file"] if idx > 0 else None
        p["next_view_file"] = pages_records[idx + 1]["view_file"] if idx + 1 < len(pages_records) else None
        p["slider_file"] = f"cmp_{p['view_file']}" if p["assets"]["hires_old"] and p["assets"]["hires_new"] else None

    slider_records = [p for p in pages_records if p["slider_file"]]
    for idx, p in enumerate(slider_records):
        p["prev_slider_file"] = slider_records[idx - 1]["slider_file"] if idx > 0 else None
        p["next_slider_file"] = slider_records[idx + 1]["slider_file"] if idx + 1 < len(slider_records) else None
    slider_record_by_file = {p["slider_file"]: p for p in slider_records if p.get("slider_file")}
    first_slider_file = slider_records[0]["slider_file"] if slider_records else None
    last_slider_file = slider_records[-1]["slider_file"] if slider_records else None

    counts = {
        "unchanged": sum(1 for p in pages_records if p["status"] == "UNCHANGED"),
        "changed": sum(1 for p in pages_records if p["status"] == "CHANGED"),
        "new": sum(1 for p in pages_records if p["status"] == "NEW"),
        "removed": sum(1 for p in pages_records if p["status_raw"] == "REMOVED"),
        "moved": sum(1 for p in pages_records if p["moved"]),
    }
    mixed_precision_pages = [
        p for p in pages_records if (p.get("page_settings") or {}).get("mixed_settings")
    ]
    mixed_precision_seqs = [int(p["seq"]) for p in mixed_precision_pages]

    report_model = {
        "documents": {
            "a": {
                "name": file_a.name,
                "size_bytes": file_a.stat().st_size,
                "page_count": page_count_a,
            },
            "b": {
                "name": file_b.name,
                "size_bytes": file_b.stat().st_size,
                "page_count": page_count_b,
            },
        },
        "settings": {
            "dpi_thumb": PAGE_INFO_THUMB_DPI,
            "dpi_diff": high_dpi,
            "stroke_tolerance_px": stroke_tol_px,
            "threshold_unchanged_percent": UNCHANGED_DIFF_PERCENT,
            "bbox_detected_means_changed": True,
            "align_mode": "ECC_AFFINE",
            "report_lang": lang,
            "is_mixed_precision": bool(mixed_precision_pages),
            "mixed_precision_seqs": mixed_precision_seqs,
        },
        "summary": {"counts": counts},
        "pages": pages_records,
    }
    (bundle_dir / "report.json").write_text(json.dumps(report_model, ensure_ascii=False, indent=2), encoding="utf-8")


    badges = ReportBadges(strings, high_dpi)

    views_dir = bundle_dir / "views"
    views_dir.mkdir(parents=True, exist_ok=True)

    ctx = _ReportContext(
        strings=strings,
        badges=badges,
        run_dir=run_dir,
        bundle_dir=bundle_dir,
        file_a=file_a,
        file_b=file_b,
        details=details,
        pages_records=pages_records,
        page_count_a=page_count_a,
        page_count_b=page_count_b,
        high_dpi=high_dpi,
        stroke_tol_px=stroke_tol_px,
        mixed_precision_seqs=mixed_precision_seqs,
        views_dir=views_dir,
        slider_record_by_file=slider_record_by_file,
        first_slider_file=first_slider_file,
        last_slider_file=last_slider_file,
    )
    summary_html, status_counts = _build_dashboard_html(ctx)
    (bundle_dir / "index.html").write_text(summary_html, encoding="utf-8")

    # One shared sheet list for every detail page and every slider (PDF-008).
    _write_nav_data(ctx)

    total_views = max(1, len(pages_records))
    for view_idx, p in enumerate(pages_records, start=1):
        _write_page_views(ctx, p, view_idx, status_counts)
        emit(66 + 32 * (view_idx / total_views), t["progress_generate_view"].format(idx=view_idx, total=total_views))

    # The report bundle and start.html are published together: the previous
    # bundle stays in a backup until start.html has been written, so a failure
    # anywhere in the swap leaves the run with its old, self-consistent report
    # instead of a new bundle behind a stale entry point (or none at all).
    backup_bundle_dir = internal_dir(run_dir) / f".report_backup_{uuid4().hex}"
    start_path = run_dir / START_REPORT_FILE
    backup_start_path = internal_dir(run_dir) / f".start_backup_{uuid4().hex}.html"
    had_bundle = final_bundle_dir.exists()
    had_start = start_path.exists()
    try:
        if had_bundle:
            final_bundle_dir.rename(backup_bundle_dir)
        if had_start:
            os.replace(start_path, backup_start_path)
        bundle_dir.rename(final_bundle_dir)
        write_start_page(run_dir, report_lang)
    except Exception:
        # Put the previous report back. If it cannot be restored, the backup is
        # deliberately left on disk: it is the only remaining copy.
        if final_bundle_dir.exists():
            shutil.rmtree(final_bundle_dir, ignore_errors=True)
        if had_bundle and backup_bundle_dir.exists() and not final_bundle_dir.exists():
            backup_bundle_dir.rename(final_bundle_dir)
        if had_start and backup_start_path.exists():
            os.replace(backup_start_path, start_path)
        elif not had_start and start_path.exists():
            start_path.unlink()
        if bundle_dir.exists():
            shutil.rmtree(bundle_dir, ignore_errors=True)
        raise

    if backup_bundle_dir.exists():
        shutil.rmtree(backup_bundle_dir, ignore_errors=True)
    backup_start_path.unlink(missing_ok=True)
    emit(100, t["progress_ready"])
    return run_dir / START_REPORT_FILE
