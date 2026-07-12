"""Live progress HTML reports (refreshed while the comparison is running)."""

from __future__ import annotations

import html
import json
from collections.abc import Sequence
from pathlib import Path

from .classification import level_to_report_tags
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
    labels = live_report_labels(report_lang)
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
    a_page = "-" if row.get("a_page") is None else str(row.get("a_page"))
    b_page = "-" if row.get("b_page") is None else str(row.get("b_page"))
    lang = "en" if str(report_lang).lower().startswith("en") else "ru"
    load_error = "Failed to load image" if lang == "en" else "Не удалось загрузить изображение"
    fit_label = "Fit to window" if lang == "en" else "Вписать в окно"
    back_label = "Back to page" if lang == "en" else "Назад к листу"
    summary_label = "Back to summary" if lang == "en" else "К сводке"
    zoom_label = "Zoom" if lang == "en" else "Масштаб"
    bbox_color_label = "Box color" if lang == "en" else "Цвет зон"
    bbox_yellow_label = "Yellow" if lang == "en" else "Жёлтый"
    bbox_pink_label = "Pink" if lang == "en" else "Розовый"
    bbox_green_label = "Green" if lang == "en" else "Зелёный"
    bbox_opacity_label = "Opacity" if lang == "en" else "Непрозрачность"
    html_text = f"""<!doctype html>
<html lang="{lang}">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>{html.escape(labels["page"])} B{html.escape(b_page)}</title>
  <style>
    html,body {{ width:100%; height:100%; }}
    body {{ margin:0; font-family:Segoe UI,Arial,sans-serif; background:#f3f6fb; color:#1d2433; overflow:hidden; }}
    .wrap {{ width:100vw; height:100vh; margin:0; padding:0; }}
    .panel {{ width:100%; height:100%; background:#fff; border:0; padding:10px; box-sizing:border-box; display:flex; flex-direction:column; }}
    .top {{ display:flex; flex-wrap:wrap; gap:8px; align-items:center; justify-content:space-between; margin-bottom:10px; }}
    .btn {{ border:1px solid #d7deea; border-radius:8px; padding:6px 10px; text-decoration:none; color:#0f4fa8; background:#fff; }}
    .stage {{ flex:1; width:100%; border:1px solid #d7deea; border-radius:10px; background:#fff; padding:8px; box-sizing:border-box; overflow:auto; min-height:0; position:relative; }}
    .stage.dragging {{ cursor:ew-resize; }}
    .stage.panning {{ cursor:grabbing; }}
    .compare-surface {{ --bbox-border:rgba(255,180,0,.74); --bbox-fill:rgba(255,235,120,.13); position:relative; display:none; background:#fff; overflow:hidden; cursor:ew-resize; transform-origin:0 0; }}
    .layer {{ position:absolute; inset:0; width:100%; height:100%; object-fit:fill; user-select:none; -webkit-user-drag:none; }}
    .old-layer {{ position:absolute; inset:0; overflow:hidden; clip-path:inset(0 50% 0 0); }}
    .bbox-layer {{ position:absolute; inset:0; pointer-events:none; }}
    .bbox {{ position:absolute; border:2px solid var(--bbox-border); background:var(--bbox-fill); box-sizing:border-box; }}
    .divider {{ position:absolute; top:0; bottom:0; left:50%; width:2px; background:rgba(20,120,255,.95); pointer-events:none; }}
    .load-msg {{ position:absolute; inset:0; display:flex; align-items:center; justify-content:center; color:#5f6b84; }}
    .slider-wrap {{ margin:10px 0 0 0; display:flex; gap:10px; align-items:center; flex-wrap:wrap; }}
    input[type=range] {{ width:100%; }}
    .small {{ width:150px; }}
    .bbox-controls {{ display:flex; align-items:center; gap:6px; flex-wrap:wrap; margin-left:auto; }}
    .swatch-option {{ display:inline-flex; align-items:center; gap:5px; border:1px solid #d7deea; border-radius:8px; padding:5px 8px; background:#fff; cursor:pointer; user-select:none; }}
    .swatch-option input {{ margin:0; }}
    .swatch {{ width:14px; height:14px; border-radius:4px; border:2px solid currentColor; box-sizing:border-box; }}
    .swatch-yellow {{ color:rgb(255,180,0); background:rgba(255,235,120,.45); }}
    .swatch-pink {{ color:rgb(236,72,153); background:rgba(244,114,182,.45); }}
    .swatch-green {{ color:rgb(22,163,74); background:rgba(134,239,172,.45); }}
    .bbox-opacity {{ width:110px; }}
    .muted {{ color:#5f6b84; font-size:12px; }}
  </style>
</head>
<body>
  <div class="wrap"><div class="panel">
    <div class="top">
      <div><b>{html.escape(labels["page"])} A{html.escape(a_page)} - B{html.escape(b_page)}</b><div class="muted">{html.escape(file_a.name)} -> {html.escape(file_b.name)}</div></div>
      <div><a class="btn" href="{seq:03d}.html">{html.escape(back_label)}</a><a class="btn" href="../index.html">{html.escape(summary_label)}</a><button class="btn" id="fitBtn" type="button">{html.escape(fit_label)}</button></div>
    </div>
    <div class="stage" id="stage" tabindex="0">
      <div class="compare-surface" id="surface">
        <img id="imgNew" class="layer" alt="{html.escape(labels["new"])}" draggable="false"/>
        <div id="oldLayer" class="old-layer"><img id="imgOld" class="layer" alt="{html.escape(labels["old"])}" draggable="false"/></div>
        <div id="bboxLayer" class="bbox-layer"></div><div id="divider" class="divider"></div>
      </div>
      <div id="loadMsg" class="load-msg">{html.escape(labels["pending"])}</div>
    </div>
    <div class="slider-wrap"><span>{html.escape(labels["old"])}</span><input id="split" type="range" min="0" max="100" step="0.1" value="50"/><span>{html.escape(labels["new"])}</span><span>{html.escape(zoom_label)}</span><input id="zoom" class="small" type="range" min="1" max="500" value="100"/><span id="zoomVal">100%</span>
      <div class="bbox-controls" aria-label="{html.escape(bbox_color_label)}">
        <span class="muted">{html.escape(bbox_color_label)}:</span>
        <label class="swatch-option"><input type="radio" name="bboxColor" value="yellow" checked/><span class="swatch swatch-yellow"></span>{html.escape(bbox_yellow_label)}</label>
        <label class="swatch-option"><input type="radio" name="bboxColor" value="pink"/><span class="swatch swatch-pink"></span>{html.escape(bbox_pink_label)}</label>
        <label class="swatch-option"><input type="radio" name="bboxColor" value="green"/><span class="swatch swatch-green"></span>{html.escape(bbox_green_label)}</label>
        <span class="muted">{html.escape(bbox_opacity_label)}:</span><input id="bboxOpacity" class="bbox-opacity" type="range" min="5" max="35" value="13"/><span id="bboxOpacityVal">13%</span>
      </div>
    </div>
  </div></div>
  <script>
    const oldSrc = {json.dumps(old_src)};
    const newSrc = {json.dumps(new_src)};
    const bboxData = {json.dumps(bboxes_data, ensure_ascii=False)};
    const slider = document.getElementById('split');
    const zoom = document.getElementById('zoom');
    const zoomVal = document.getElementById('zoomVal');
    const fitBtn = document.getElementById('fitBtn');
    const stage = document.getElementById('stage');
    const surface = document.getElementById('surface');
    const oldLayer = document.getElementById('oldLayer');
    const divider = document.getElementById('divider');
    const bboxLayer = document.getElementById('bboxLayer');
    const loadMsg = document.getElementById('loadMsg');
    const oldImg = document.getElementById('imgOld');
    const newImg = document.getElementById('imgNew');
    const bboxOpacity = document.getElementById('bboxOpacity');
    const bboxOpacityVal = document.getElementById('bboxOpacityVal');
    const bboxPalettes = {{
      yellow: {{ border:'255,180,0', fill:'255,235,120' }},
      pink: {{ border:'236,72,153', fill:'244,114,182' }},
      green: {{ border:'22,163,74', fill:'134,239,172' }}
    }};
    let activeBboxColor = 'yellow';
    function currentBboxAlpha() {{
      const value = Math.max(5, Math.min(35, Number(bboxOpacity.value) || 13));
      bboxOpacity.value = String(value);
      bboxOpacityVal.textContent = value + '%';
      return value / 100;
    }}
    function setBboxColor(name) {{
      activeBboxColor = bboxPalettes[name] ? name : 'yellow';
      applyBboxStyle();
      try {{ localStorage.setItem('pdfcompare:bboxColor', activeBboxColor); }} catch (e) {{}}
    }}
    function applyBboxStyle() {{
      const palette = bboxPalettes[activeBboxColor] || bboxPalettes.yellow;
      const alpha = currentBboxAlpha();
      const borderAlpha = Math.min(0.9, 0.35 + alpha * 3);
      surface.style.setProperty('--bbox-border', `rgba(${{palette.border}},${{borderAlpha.toFixed(2)}})`);
      surface.style.setProperty('--bbox-fill', `rgba(${{palette.fill}},${{alpha.toFixed(2)}})`);
      try {{ localStorage.setItem('pdfcompare:bboxOpacity', bboxOpacity.value); }} catch (e) {{}}
    }}
    document.querySelectorAll('input[name="bboxColor"]').forEach(input => {{
      input.addEventListener('change', () => setBboxColor(input.value));
    }});
    try {{
      const savedColor = localStorage.getItem('pdfcompare:bboxColor') || 'yellow';
      const savedOpacity = localStorage.getItem('pdfcompare:bboxOpacity') || '13';
      bboxOpacity.value = savedOpacity;
      const savedInput = document.querySelector(`input[name="bboxColor"][value="${{savedColor}}"]`);
      if (savedInput) savedInput.checked = true;
      setBboxColor(savedColor);
    }} catch (e) {{
      setBboxColor('yellow');
    }}
    bboxOpacity.addEventListener('input', applyBboxStyle);
    let loaded = 0, naturalW = 0, naturalH = 0;
    function ready() {{ loaded += 1; if (loaded >= 2) initialize(); }}
    function fail() {{ loadMsg.textContent = {json.dumps(load_error)}; }}
    oldImg.onload = ready; newImg.onload = ready; oldImg.onerror = fail; newImg.onerror = fail;
    oldImg.src = oldSrc; newImg.src = newSrc;
    function initialize() {{
      naturalW = Math.max(oldImg.naturalWidth || 1, newImg.naturalWidth || 1);
      naturalH = Math.max(oldImg.naturalHeight || 1, newImg.naturalHeight || 1);
      surface.style.display = 'block'; loadMsg.style.display = 'none'; buildBboxes(); applySplit(); fitToWindow();
    }}
    function buildBboxes() {{
      bboxLayer.innerHTML = '';
      bboxData.forEach(b => {{
        const x=Number(b.x||0), y=Number(b.y||0), bw=Number(b.w||0), bh=Number(b.h||0);
        if (bw <= 1 || bh <= 1) return;
        const box=document.createElement('div'); box.className='bbox';
        box.style.left=(100*x/naturalW)+'%'; box.style.top=(100*y/naturalH)+'%';
        box.style.width=(100*bw/naturalW)+'%'; box.style.height=(100*bh/naturalH)+'%';
        bboxLayer.appendChild(box);
      }});
    }}
    function setZoomPercent(v) {{ const clamped=Math.max(1, Math.min(500, Math.round(v))); zoom.value=String(clamped); applyZoom(); }}
    function applyZoom() {{ if (!naturalW || !naturalH) return; const z=Number(zoom.value)/100; zoomVal.textContent=Math.round(z*100)+'%'; surface.style.width=Math.max(1, Math.round(naturalW*z))+'px'; surface.style.height=Math.max(1, Math.round(naturalH*z))+'px'; }}
    function fitToWindow() {{ if (!naturalW || !naturalH) return; const pad=16; const sx=Math.max(0.01,(stage.clientWidth-pad)/naturalW); const sy=Math.max(0.01,(stage.clientHeight-pad)/naturalH); setZoomPercent(Math.max(0.01, Math.min(sx, sy))*100); }}
    function applySplit() {{ const pct=Math.max(0, Math.min(100, Number(slider.value)||0)); oldLayer.style.clipPath=`inset(0 ${{100-pct}}% 0 0)`; divider.style.left=pct+'%'; }}
    function setSplitFromClientX(clientX) {{ const rect=surface.getBoundingClientRect(); if (!rect.width) return; const x=Math.max(0, Math.min(rect.width, clientX-rect.left)); slider.value=String((x/rect.width)*100); applySplit(); }}
    let draggingSplit=false, panning=false, panStartX=0, panStartY=0, panStartScrollLeft=0, panStartScrollTop=0;
    surface.addEventListener('mousedown', e => {{ if (e.button===2) {{ panning=true; stage.classList.add('panning'); panStartX=e.clientX; panStartY=e.clientY; panStartScrollLeft=stage.scrollLeft; panStartScrollTop=stage.scrollTop; e.preventDefault(); return; }} if (e.button!==0) return; draggingSplit=true; stage.classList.add('dragging'); setSplitFromClientX(e.clientX); }});
    window.addEventListener('mousemove', e => {{ if (panning) {{ stage.scrollLeft=panStartScrollLeft-(e.clientX-panStartX); stage.scrollTop=panStartScrollTop-(e.clientY-panStartY); return; }} if (draggingSplit) setSplitFromClientX(e.clientX); }});
    window.addEventListener('mouseup', () => {{ draggingSplit=false; panning=false; stage.classList.remove('dragging'); stage.classList.remove('panning'); }});
    stage.addEventListener('contextmenu', e => e.preventDefault());
    stage.addEventListener('wheel', e => {{ if (!e.ctrlKey) return; e.preventDefault(); setZoomPercent(Number(zoom.value)+(e.deltaY<0?6:-6)); }}, {{ passive:false }});
    slider.addEventListener('input', applySplit); zoom.addEventListener('input', () => setZoomPercent(Number(zoom.value))); fitBtn.addEventListener('click', fitToWindow);
  </script>
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

