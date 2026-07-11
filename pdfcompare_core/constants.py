"""Magic-number thresholds, regex patterns, and app metadata."""

from __future__ import annotations

import re

TOKEN_RE = re.compile(r"[A-Za-zА-Яа-я0-9]{3,}")
INVALID_DOWNLOAD_NAME_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')
SHEET_RU_RE = re.compile(
    r"(?:\bЛИСТ(?:\s*№)?|\bЛ\.)\s*[:№#-]?\s*([A-ZА-Я]{0,3}\d{1,4}[A-ZА-Я]{0,3})",
    re.IGNORECASE,
)
SHEET_EN_RE = re.compile(
    r"\bSHEET\s*[:#-]?\s*([A-Z]{0,3}\d{1,4}[A-Z]{0,3})\b",
    re.IGNORECASE,
)
SHEET_FRACTION_RE = re.compile(r"\b(\d{1,3})\s*/\s*(\d{1,3})\b")

UNCHANGED_DIFF_PERCENT = 0.15
MINOR_DIFF_PERCENT = 1.0
MODERATE_DIFF_PERCENT = 5.0
PAGE_INFO_THUMB_DPI = 96
THUMB_MAX_WIDTH = 320
THUMB_JPEG_QUALITY = 82
# Soft cap on the rendered page raster (megapixels). Pages above this are
# downscaled before the diff to keep peak memory bounded on large A0/A1
# sheets at high DPI. ~40 MP is roughly an A1 page at 250 DPI.
MAX_RENDER_MEGAPIXELS = 40.0
LIVE_REPORT_EVENT_PREFIX = "__PDFCOMPARE_LIVE_REPORT__|"
INTERNAL_REPORT_DIR = "_pdfcompare"
START_REPORT_FILE = "start.html"
APP_NAME = "PDFCompare Local"
APP_VERSION = "0.1.7"
GITHUB_REPO = "mikhalchankasm/AutoPDFCompare"
UPDATE_CHECK_ENABLED_DEFAULT = True
UPDATE_CHECK_INTERVAL_HOURS = 24.0
