"""Live progress HTML reports (refreshed while the comparison is running)."""

from __future__ import annotations

import html
import json
from collections.abc import Sequence
from pathlib import Path

from .classification import level_to_report_tags
from .html_css import CSS_CMP, CSS_LIVE_CMP, REPORT_CSS_TOKENS
from .html_i18n import HTML_REPORT_I18N
from .html_slider import render_slider_runtime
from .models import MatchPair
from .pdf_io import atomic_write_text, find_pages_dir, report_dir, write_start_page


def live_report_labels(lang: str) -> dict[str, str]:
    if str(lang).lower().startswith("en"):
        return {
            "title": "PDF comparison in progress",
            "subtitle": "The report updates automatically while pages are being compared.",
            "ready": "Ready",
            "pending": "Processing",
            "changed": "Changed",
            "unchanged": "Unchanged",
            "added": "Added",
            "removed": "Removed",
            "size_mismatch": "Size mismatch",
            "summary": "Progress",
            "open": "Open",
            "old": "Old",
            "new": "New",
            "diff": "Diff",
            "page": "Page",
            "status": "Status",
            "level": "Level",
            "diff_pct": "Diff %",
            "fg_pct": "Drawn %",
            "boxes": "Boxes",
            "back": "Back to live summary",
            "finalizing": "Final report is being prepared...",
            "done": "Final report is ready.",
        }
    return {
        "title": "Сравнение PDF выполняется",
        "subtitle": "Отчёт обновляется автоматически по мере готовности листов.",
        "ready": "Готово",
        "pending": "Обрабатывается",
        "changed": "Изменён",
        "unchanged": "Без изменений",
        "added": "Добавлен",
        "removed": "Удалён",
        "size_mismatch": "Разный размер",
        "summary": "Прогресс",
        "open": "Открыть",
        "old": "Старый",
        "new": "Новый",
        "diff": "Разница",
        "page": "Лист",
        "status": "Статус",
        "level": "Уровень",
        "diff_pct": "Разница %",
        "fg_pct": "Заполнено %",
        "boxes": "Зоны",
        "back": "К live-сводке",
        "finalizing": "Финальный отчёт готовится...",
        "done": "Финальный отчёт готов.",
    }


def live_row_status(row: dict, labels: dict[str, str]) -> tuple[str, str, str]:
    raw_status = str(row.get("status") or "")
    if raw_status == "added":
        return "added", labels["added"], "added"
    if raw_status == "removed":
        return "removed", labels["removed"], "removed"
    if raw_status == "size_mismatch" or row.get("change_level") == "size_mismatch":
        return "changed", labels["size_mismatch"], "major"
    level = row.get("change_level")
    content_status, level_tag = level_to_report_tags(level)
    if content_status == "UNCHANGED":
        return "unchanged", labels["unchanged"], "unchanged"
    return "changed", labels["changed"], str(level_tag or "changed").lower()


def first_existing_rel(base_dir: Path, pair_name: str, names: Sequence[str], prefix: str) -> str | None:
    pair_dir = base_dir / pair_name
    for name in names:
        if (pair_dir / name).exists():
            return f"{prefix}{pair_name}/{name}"
    return None


def format_eta(seconds: float | None) -> str:
    if seconds is None or seconds < 0:
        return "-"
    total = int(round(seconds))
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}ч {minutes:02d}м"
    if minutes:
        return f"{minutes}м {secs:02d}с"
    return f"{secs}с"


def write_live_slider_view(
    run_dir: Path,
    file_a: Path,
    file_b: Path,
    row: dict,
    report_lang: str,
    old_src: str | None,
    new_src: str | None,
) -> str | None:
    if not old_src or not new_src:
        return None
    views_dir = report_dir(run_dir) / "views"
    views_dir.mkdir(parents=True, exist_ok=True)
    seq = int(row["seq"])
    slider_file = f"cmp_{seq:03d}.html"
    pair_name = str(row.get("pair_dir") or "")
    bboxes_path = find_pages_dir(run_dir) / pair_name / "bboxes.json"
    try:
        bboxes_data = json.loads(bboxes_path.read_text(encoding="utf-8")) if bboxes_path.exists() else []
    except Exception:
        bboxes_data = []
    lang = "en" if str(report_lang).lower().startswith("en") else "ru"
    text = HTML_REPORT_I18N[lang]
    a_page = "-" if row.get("a_page") is None else str(row.get("a_page"))
    b_page = "-" if row.get("b_page") is None else str(row.get("b_page"))
    slider_runtime = render_slider_runtime(
        {
            "oldSrc": old_src,
            "newSrc": new_src,
            "bboxes": bboxes_data,
            "bboxOpacity": 13,
            "loadError": text["slider_load_error"],
            "storagePrefix": "pdfcompare:live",
        }
    )
    html_text = f"""<!doctype html>
<html lang="{lang}">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>{html.escape(text["nav_sheet_word"])} B{html.escape(b_page)}</title>
  <style>
{REPORT_CSS_TOKENS}
{CSS_CMP}
{CSS_LIVE_CMP}
  </style>
</head>
<body>
  <div class="live-cmp-page"><div class="live-cmp-panel">
    <div class="live-cmp-header">
      <div><b>{html.escape(text["nav_sheet_word"])} A{html.escape(a_page)} - B{html.escape(b_page)}</b><div class="muted">{html.escape(file_a.name)} -> {html.escape(file_b.name)}</div></div>
      <div><a class="btn" href="{seq:03d}.html">{html.escape(text["back_to_sheet"])}</a><a class="btn" href="../index.html">{html.escape(text["back_summary"])}</a><button class="btn fit-btn" id="fitBtn" type="button">{html.escape(text["fit_to_window"])}</button></div>
    </div>
    <div class="stage" id="stage" tabindex="0">
      <div class="compare-surface" id="surface">
        <img id="imgNew" class="layer" alt="{html.escape(text["slider_new"])}" draggable="false"/>
        <div id="oldLayer" class="old-layer"><img id="imgOld" class="layer" alt="{html.escape(text["slider_old"])}" draggable="false"/></div>
        <div id="bboxLayer" class="bbox-layer"></div><div id="divider" class="divider"></div>
      </div>
      <div id="loadMsg" class="load-msg">{html.escape(live_report_labels(lang)["pending"])}</div>
    </div>
    <div class="live-cmp-controls"><span>{html.escape(text["slider_old"])}</span><input id="split" type="range" min="0" max="100" step="0.1" value="50"/><span>{html.escape(text["slider_new"])}</span><span>{html.escape(text["slider_zoom"])}</span><input id="zoom" class="live-cmp-zoom" type="range" min="1" max="500" value="100"/><span id="zoomVal">100%</span>
      <div class="live-cmp-bbox-controls" aria-label="{html.escape(text["bbox_color"])}">
        <span class="muted">{html.escape(text["bbox_color"])}:</span>
        <label class="swatch-option"><input type="radio" name="bboxColor" value="yellow" checked/><span class="swatch swatch-yellow"></span>{html.escape(text["bbox_yellow"])}</label>
        <label class="swatch-option"><input type="radio" name="bboxColor" value="pink"/><span class="swatch swatch-pink"></span>{html.escape(text["bbox_pink"])}</label>
        <label class="swatch-option"><input type="radio" name="bboxColor" value="green"/><span class="swatch swatch-green"></span>{html.escape(text["bbox_green"])}</label>
        <span class="muted">{html.escape(text["bbox_opacity"])}:</span><input id="bboxOpacity" class="bbox-opacity" type="range" min="5" max="35" value="13"/><span id="bboxOpacityVal">13%</span>
      </div>
    </div>
  </div></div>
  {slider_runtime}
</body>
</html>
"""
    atomic_write_text(views_dir / slider_file, html_text)
    return slider_file


def write_live_detail_view(run_dir: Path, file_a: Path, file_b: Path, row: dict, report_lang: str) -> None:
    labels = live_report_labels(report_lang)
    bundle_dir = report_dir(run_dir)
    views_dir = bundle_dir / "views"
    views_dir.mkdir(parents=True, exist_ok=True)
    pair_name = str(row.get("pair_dir") or "")
    seq = int(row["seq"])
    pages_dir = find_pages_dir(run_dir)
    old_src = first_existing_rel(pages_dir, pair_name, ("a.png", "a_preview.png"), "../../pages/")
    new_src = first_existing_rel(pages_dir, pair_name, ("b.png", "b_preview.png"), "../../pages/")
    diff_src = first_existing_rel(pages_dir, pair_name, ("overlay.png", "mask.png"), "../../pages/")
    slider_file = write_live_slider_view(run_dir, file_a, file_b, row, report_lang, old_src, new_src)
    css_status, status_text, level_class = live_row_status(row, labels)
    a_page = "-" if row.get("a_page") is None else str(row.get("a_page"))
    b_page = "-" if row.get("b_page") is None else str(row.get("b_page"))
    diff_text = "-" if row.get("diff_percent") is None else f"{float(row['diff_percent']):.3f}%"
    fg_text = "-" if row.get("diff_foreground_percent") is None else f"{float(row['diff_foreground_percent']):.2f}%"
    boxes_text = "-" if row.get("bboxes_count") is None else str(int(row["bboxes_count"]))
    level_text = "-" if row.get("change_level") is None else str(row["change_level"])
    slider_label = "Slider" if str(report_lang).lower().startswith("en") else "Слайдер"

    def figure(title: str, src: str | None, extra: str = "") -> str:
        if src:
            body = f'<img src="{html.escape(src)}" alt="{html.escape(title)}"/>'
        else:
            body = f'<div class="empty">{html.escape(labels["pending"])}</div>'
        return f"<figure class='{extra}'>{body}<figcaption>{html.escape(title)}</figcaption></figure>"

    doc_title = f"A{a_page} - B{b_page}"
    html_text = f"""<!doctype html>
<html lang="{'en' if str(report_lang).lower().startswith('en') else 'ru'}">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>{html.escape(labels["page"])} {html.escape(doc_title)}</title>
  <style>
    body {{ margin:0; font-family:Segoe UI,Arial,sans-serif; background:#ECEBE5; color:#141413; }}
    .wrap {{ max-width:1380px; margin:0 auto; padding:18px; }}
    a {{ color:#185FA5; }}
    .top {{ display:flex; justify-content:space-between; gap:12px; align-items:flex-start; margin-bottom:14px; }}
    .back {{ display:inline-block; padding:8px 12px; background:#185FA5; color:white; text-decoration:none; border-radius:6px; font-weight:700; }}
    h1 {{ margin:0 0 6px 0; font-size:28px; }}
    .meta {{ color:#6E6D68; }}
    .badge {{ display:inline-block; padding:5px 10px; border-radius:999px; font-weight:700; }}
    .changed {{ background:#F8D7D7; color:#7A1F1F; }}
    .unchanged {{ background:#EAF3DE; color:#3B6D11; }}
    .added {{ background:#E6F1FB; color:#0C447C; }}
    .removed {{ background:#F1EFE8; color:#5F5E5A; }}
    .grid {{ display:grid; grid-template-columns:1fr 1fr 1.6fr; gap:12px; align-items:start; }}
    figure {{ margin:0; background:#FFFFFF; border:1px solid #E0DFDB; }}
    img {{ width:100%; max-height:78vh; object-fit:contain; display:block; background:white; }}
    figcaption {{ padding:8px 10px; border-top:1px solid #E0DFDB; color:#6E6D68; font-weight:700; }}
    .empty {{ min-height:260px; display:flex; align-items:center; justify-content:center; color:#999791; }}
    .wide img {{ max-height:82vh; }}
    @media (max-width:1000px) {{ .grid {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="top">
      <div>
        <h1>{html.escape(labels["page"])} {html.escape(doc_title)} <span class="badge {css_status}">{html.escape(status_text)}</span></h1>
        <div class="meta">{html.escape(file_a.name)} -> {html.escape(file_b.name)} | {html.escape(labels["fg_pct"])}: {html.escape(fg_text)} | {html.escape(labels["diff_pct"])}: {html.escape(diff_text)} | {html.escape(labels["boxes"])}: {html.escape(boxes_text)} | {html.escape(labels["level"])}: {html.escape(level_text)}</div>
      </div>
      <div>
        {f'<a class="back" href="{html.escape(slider_file)}">{html.escape(slider_label)}</a>' if slider_file else ''}
        <a class="back" href="../index.html">{html.escape(labels["back"])}</a>
      </div>
    </div>
    <div class="grid">
      {figure(labels["old"], old_src)}
      {figure(labels["new"], new_src)}
      {figure(labels["diff"], diff_src, "wide")}
    </div>
  </div>
</body>
</html>
"""
    atomic_write_text(views_dir / f"{seq:03d}.html", html_text)


def write_live_html_report(
    run_dir: Path,
    file_a: Path,
    file_b: Path,
    pairs: Sequence[MatchPair],
    details: Sequence[dict],
    report_lang: str,
    in_progress: bool = True,
    write_detail_views: bool = True,
) -> None:
    labels = live_report_labels(report_lang)
    bundle_dir = report_dir(run_dir)
    views_dir = bundle_dir / "views"
    views_dir.mkdir(parents=True, exist_ok=True)
    details_by_seq = {int(row["seq"]): row for row in details}
    total = len(pairs)
    ready = len(details_by_seq)
    rows: list[str] = []
    counts = {"changed": 0, "unchanged": 0, "added": 0, "removed": 0, "pending": max(0, total - ready)}

    for seq, pair in enumerate(pairs, start=1):
        row = details_by_seq.get(seq)
        if row is None:
            a_page = "-" if pair.a_idx is None else str(pair.a_idx + 1)
            b_page = "-" if pair.b_idx is None else str(pair.b_idx + 1)
            rows.append(
                "<tr class='pending'>"
                f"<td>{seq}</td><td>{html.escape(a_page)}</td><td>{html.escape(b_page)}</td>"
                f"<td><span class='badge pending-b'>{html.escape(labels['pending'])}</span></td>"
                "<td>-</td><td>-</td><td>-</td><td>-</td>"
                "</tr>"
            )
            continue

        if write_detail_views:
            write_live_detail_view(run_dir, file_a, file_b, row, report_lang)
        css_status, status_text, level_class = live_row_status(row, labels)
        if css_status in counts:
            counts[css_status] += 1
        a_page = "-" if row.get("a_page") is None else str(row.get("a_page"))
        b_page = "-" if row.get("b_page") is None else str(row.get("b_page"))
        diff_text = "-" if row.get("diff_percent") is None else f"{float(row['diff_percent']):.3f}%"
        fg_text = "-" if row.get("diff_foreground_percent") is None else f"{float(row['diff_foreground_percent']):.2f}%"
        boxes_text = "-" if row.get("bboxes_count") is None else str(int(row["bboxes_count"]))
        level_text = "-" if row.get("change_level") is None else str(row["change_level"])
        rows.append(
            f"<tr class='ready' onclick=\"window.location.href='views/{seq:03d}.html'\">"
            f"<td>{seq}</td><td>{html.escape(a_page)}</td><td>{html.escape(b_page)}</td>"
            f"<td><span class='badge {html.escape(css_status)}'>{html.escape(status_text)}</span></td>"
            f"<td><span class='level {html.escape(level_class)}'>{html.escape(level_text)}</span></td>"
            f"<td>{html.escape(fg_text)}</td><td>{html.escape(diff_text)}</td><td>{html.escape(boxes_text)}</td>"
            f"<td><a href='views/{seq:03d}.html'>{html.escape(labels['open'])}</a></td>"
            "</tr>"
        )

    refresh = '<meta http-equiv="refresh" content="4"/>' if in_progress else ""
    progress_text = f"{ready}/{total}"
    state_text = labels["finalizing"] if in_progress else labels["done"]
    html_text = f"""<!doctype html>
<html lang="{'en' if str(report_lang).lower().startswith('en') else 'ru'}">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  {refresh}
  <title>{html.escape(labels["title"])}</title>
  <style>
    body {{ margin:0; font-family:Segoe UI,Arial,sans-serif; background:#ECEBE5; color:#141413; }}
    .wrap {{ max-width:1240px; margin:0 auto; padding:22px; }}
    h1 {{ margin:0; font-size:32px; font-weight:600; }}
    .sub {{ margin:6px 0 16px 0; color:#6E6D68; }}
    .summary {{ display:grid; grid-template-columns:repeat(5,1fr); gap:10px; margin-bottom:16px; }}
    .card {{ background:#FFFFFF; border:1px solid #E0DFDB; padding:12px; }}
    .card span {{ color:#6E6D68; display:block; font-size:13px; }}
    .card b {{ font-size:24px; }}
    table {{ width:100%; border-collapse:collapse; background:#FFFFFF; border:1px solid #E0DFDB; }}
    th, td {{ padding:10px 12px; border-bottom:1px solid #E0DFDB; text-align:left; }}
    th {{ color:#6E6D68; font-weight:600; background:#F5F4EE; }}
    tr.ready {{ cursor:pointer; }}
    tr.ready:hover td {{ background:#E6F1FB; }}
    .badge, .level {{ display:inline-block; padding:4px 9px; border-radius:999px; font-weight:700; font-size:13px; }}
    .changed {{ background:#F8D7D7; color:#7A1F1F; }}
    .unchanged {{ background:#EAF3DE; color:#3B6D11; }}
    .added {{ background:#E6F1FB; color:#0C447C; }}
    .removed, .pending-b {{ background:#F1EFE8; color:#5F5E5A; }}
    .major, .moderate, .minor {{ background:#FFF4CC; color:#705200; }}
    a {{ color:#185FA5; font-weight:700; }}
    @media (max-width:800px) {{ .summary {{ grid-template-columns:1fr 1fr; }} }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>{html.escape(labels["title"])}</h1>
    <div class="sub">{html.escape(labels["subtitle"])} {html.escape(state_text)}</div>
    <div class="summary">
      <div class="card"><span>{html.escape(labels["summary"])}</span><b>{html.escape(progress_text)}</b></div>
      <div class="card"><span>{html.escape(labels["changed"])}</span><b>{counts["changed"]}</b></div>
      <div class="card"><span>{html.escape(labels["unchanged"])}</span><b>{counts["unchanged"]}</b></div>
      <div class="card"><span>{html.escape(labels["added"])}</span><b>{counts["added"]}</b></div>
      <div class="card"><span>{html.escape(labels["removed"])}</span><b>{counts["removed"]}</b></div>
    </div>
    <table>
      <thead>
        <tr>
          <th>#</th><th>A</th><th>B</th><th>{html.escape(labels["status"])}</th>
          <th>{html.escape(labels["level"])}</th><th>{html.escape(labels["fg_pct"])}</th>
          <th>{html.escape(labels["diff_pct"])}</th>
          <th>{html.escape(labels["boxes"])}</th><th>{html.escape(labels["open"])}</th>
        </tr>
      </thead>
      <tbody>{''.join(rows)}</tbody>
    </table>
  </div>
</body>
</html>
"""
    atomic_write_text(bundle_dir / "index.html", html_text)
    write_start_page(run_dir, report_lang)

