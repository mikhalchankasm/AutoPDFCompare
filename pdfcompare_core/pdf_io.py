"""PDF rendering, image I/O, run-directory paths, and per-page text extraction."""

from __future__ import annotations

import html
import json
import os
import re
from collections.abc import Callable, Sequence
from pathlib import Path
from uuid import uuid4

import cv2
import fitz
import numpy as np

from .constants import (
    INTERNAL_REPORT_DIR,
    INVALID_DOWNLOAD_NAME_CHARS_RE,
    MAX_RENDER_MEGAPIXELS,
    PAGE_INFO_THUMB_DPI,
    SHEET_EN_RE,
    SHEET_FRACTION_RE,
    SHEET_RU_RE,
    START_REPORT_FILE,
    THUMB_JPEG_QUALITY,
    THUMB_MAX_WIDTH,
    TOKEN_RE,
)
from .models import PageInfo


def safe_download_file_name(raw_name: str, suffix: str = ".png") -> str:
    """Return a browser-download-friendly file name."""
    name = str(raw_name or "").strip()
    name = INVALID_DOWNLOAD_NAME_CHARS_RE.sub("_", name)
    name = re.sub(r"\s+", "_", name, flags=re.UNICODE)
    name = re.sub(r"_+", "_", name).strip(" ._")
    if not name:
        name = "download"
    if suffix and not name.lower().endswith(suffix.lower()):
        name = f"{name}{suffix}"
    name = name[:140].rstrip(" ._")
    if not name:
        name = f"download{suffix}"
    return name


def render_page(doc: fitz.Document, page_index: int, dpi: int) -> np.ndarray:
    page = doc[page_index]
    zoom = dpi / 72.0
    # Force a predictable pixel format for downstream OpenCV code:
    # - consistent 3-channel output (BGR)
    # - avoid crashes on grayscale PDFs (n == 1) or unexpected channel order.
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False, colorspace=fitz.csRGB)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)

    if pix.n == 3:
        # PyMuPDF returns RGB for csRGB; convert to OpenCV's BGR.
        img = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    elif pix.n == 4:
        # Shouldn't happen with alpha=False, but keep it robust.
        img = cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
    elif pix.n == 1:
        img = cv2.cvtColor(arr, cv2.COLOR_GRAY2BGR)
    else:
        # Fallback: take first 3 channels and treat them as RGB.
        arr = arr[:, :, :3]
        img = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)

    # Guard against memory blow-ups on very large pages (e.g. A0/A1 at high
    # DPI). The diff pipeline allocates several full-frame float32 buffers;
    # capping the raster area keeps peak memory bounded. Downscaling is area-
    # interpolated to preserve stroke geometry.
    h, w = img.shape[:2]
    megapixels = (w * h) / 1_000_000.0
    if megapixels > MAX_RENDER_MEGAPIXELS:
        scale = (MAX_RENDER_MEGAPIXELS / megapixels) ** 0.5
        new_w = max(1, int(round(w * scale)))
        new_h = max(1, int(round(h * scale)))
        img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
    return img


def render_page_gray(doc: fitz.Document, page_index: int, dpi: int) -> np.ndarray:
    page = doc[page_index]
    zoom = dpi / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False, colorspace=fitz.csGRAY)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n == 1:
        gray: np.ndarray = arr[:, :, 0]
    else:
        gray = cv2.cvtColor(arr[:, :, :3], cv2.COLOR_RGB2GRAY)

    h, w = gray.shape[:2]
    megapixels = (w * h) / 1_000_000.0
    if megapixels > MAX_RENDER_MEGAPIXELS:
        scale = (MAX_RENDER_MEGAPIXELS / megapixels) ** 0.5
        new_w = max(1, int(round(w * scale)))
        new_h = max(1, int(round(h * scale)))
        gray = cv2.resize(gray, (new_w, new_h), interpolation=cv2.INTER_AREA).astype(np.uint8)
    return gray


def page_tokens(text: str) -> set[str]:
    return {m.group(0).upper() for m in TOKEN_RE.finditer(text)}


def normalize_sheet_mark(raw: str) -> str:
    mark = raw.strip().upper()
    mark = re.sub(r"[\s_]+", "", mark)
    mark = mark.replace("№", "")
    return mark


def extract_sheet_mark(text: str) -> str | None:
    for rx in (SHEET_RU_RE, SHEET_EN_RE):
        m = rx.search(text)
        if m:
            return normalize_sheet_mark(m.group(1))
    m_frac = SHEET_FRACTION_RE.search(text)
    if m_frac:
        return normalize_sheet_mark(m_frac.group(1))
    return None


def imread_compat(path: Path, flags: int = cv2.IMREAD_UNCHANGED) -> np.ndarray | None:
    """Unicode-safe image read for Windows paths."""
    try:
        raw = np.fromfile(str(path), dtype=np.uint8)
    except OSError:
        return None
    if raw.size == 0:
        return None
    return cv2.imdecode(raw, flags)


def imwrite_compat(path: Path, img: np.ndarray, params: Sequence[int] | None = None) -> None:
    """Unicode-safe image write for Windows paths."""
    ext = path.suffix.lower() or ".png"
    encode_params = [] if params is None else list(params)
    ok, encoded = cv2.imencode(ext, img, encode_params)
    if not ok:
        raise RuntimeError(f"Не удалось закодировать изображение для {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded.tofile(str(path))


def internal_dir(run_dir: Path) -> Path:
    return run_dir / INTERNAL_REPORT_DIR


def report_dir(run_dir: Path) -> Path:
    return internal_dir(run_dir) / "report"


def report_pages_dir(run_dir: Path) -> Path:
    return internal_dir(run_dir) / "pages"


def summary_json_path(run_dir: Path) -> Path:
    return internal_dir(run_dir) / "summary.json"


def page_map_csv_path(run_dir: Path) -> Path:
    return internal_dir(run_dir) / "page_map.csv"


def find_summary_json_path(run_dir: Path) -> Path:
    current = summary_json_path(run_dir)
    return current if current.exists() else run_dir / "summary.json"


def find_pages_dir(run_dir: Path) -> Path:
    current = report_pages_dir(run_dir)
    return current if current.exists() else run_dir / "pages"


def atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    tmp.write_text(text, encoding=encoding)
    os.replace(tmp, path)


def copy_thumb(src: Path | None, dst: Path, max_w: int = THUMB_MAX_WIDTH) -> None:
    if src is None or not src.exists():
        return
    img = imread_compat(src, cv2.IMREAD_UNCHANGED)
    if img is None:
        return
    h, w = img.shape[:2]
    if w > max_w:
        scale = max_w / float(w)
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    imwrite_compat(dst, img, [cv2.IMWRITE_JPEG_QUALITY, THUMB_JPEG_QUALITY])


def write_start_page(run_dir: Path, report_lang: str = "ru") -> None:
    lang = "en" if str(report_lang).lower().startswith("en") else "ru"
    title = "Open PDF comparison report" if lang == "en" else "Открыть отчёт сравнения PDF"
    body = "The report will open automatically." if lang == "en" else "Отчёт откроется автоматически."
    link = f"{INTERNAL_REPORT_DIR}/report/index.html"
    html_text = f"""<!doctype html>
<html lang="{lang}">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <meta http-equiv="refresh" content="0; url={html.escape(link)}"/>
  <title>{html.escape(title)}</title>
  <style>
    body {{ margin:0; min-height:100vh; display:grid; place-items:center; font-family:Segoe UI,Arial,sans-serif; background:#f3f6fb; color:#1d2433; }}
    a {{ display:inline-block; margin-top:12px; padding:10px 14px; border-radius:8px; background:#185fa5; color:white; text-decoration:none; }}
  </style>
</head>
<body>
  <main>
    <h1>{html.escape(title)}</h1>
    <p>{html.escape(body)}</p>
    <a href="{html.escape(link)}">{html.escape(title)}</a>
  </main>
  <script>window.location.replace({json.dumps(link)});</script>
</body>
</html>
"""
    atomic_write_text(run_dir / START_REPORT_FILE, html_text)


def build_page_info(
    doc_path: Path,
    thumb_dpi: int = PAGE_INFO_THUMB_DPI,
    progress_cb: Callable[[int, int, str], None] | None = None,
    label: str = "",
) -> list[PageInfo]:
    infos: list[PageInfo] = []
    with fitz.open(doc_path) as doc:
        total = len(doc)
        for i in range(total):
            gray = render_page_gray(doc, i, thumb_dpi)
            thumb_u8 = cv2.resize(gray, (160, 160), interpolation=cv2.INTER_AREA)
            thumb = cv2.normalize(thumb_u8, np.empty_like(thumb_u8), 0, 255, cv2.NORM_MINMAX).astype(np.float32)
            text = doc[i].get_text("text") or ""
            rect = doc[i].rect
            infos.append(
                PageInfo(
                    index=i,
                    thumb=thumb,
                    text_tokens=page_tokens(text),
                    width_pt=float(rect.width),
                    height_pt=float(rect.height),
                    sheet_mark=extract_sheet_mark(text),
                )
            )
            if progress_cb is not None:
                progress_cb(i + 1, total, label)
    return infos
