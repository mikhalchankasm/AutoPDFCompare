"""Public facade for the PDFCompare comparison engine.

Historical entry point. The implementation lives in `pdfcompare_core/*`;
this module re-exports the public symbols so callers that import from
`compare_pdfs` (the GUI, scripts, tests, third-party tools) keep working.
"""

from __future__ import annotations

import multiprocessing

from pdfcompare_core.alignment import (
    align_ecc,
    align_pages_hungarian,
    align_pages_monotonic,
    align_pages_v1,
    alignment_quality,
    build_similarity_matrices,
    count_inversions,
    linear_sum_assignment,
    pair_similarity,
    sheet_mark_similarity,
    size_compatible,
    text_similarity,
    visual_similarity,
)
from pdfcompare_core.classification import (
    classify,
    level_to_report_tags,
    status_and_confidence,
)
from pdfcompare_core.cli import main, pick_two_pdfs
from pdfcompare_core.constants import (
    APP_NAME,
    APP_VERSION,
    FG_MAJOR_PERCENT,
    FG_MINOR_PERCENT,
    FG_MODERATE_PERCENT,
    FOREGROUND_SPARSE_THRESHOLD,
    INTERNAL_REPORT_DIR,
    INVALID_DOWNLOAD_NAME_CHARS_RE,
    LIVE_REPORT_EVENT_PREFIX,
    MAX_RENDER_DPI,
    MIN_RENDER_DPI,
    MINOR_DIFF_PERCENT,
    MODERATE_DIFF_PERCENT,
    PAGE_INFO_THUMB_DPI,
    REGION_MAJOR_MM2,
    REGION_MINOR_MM2,
    REGION_MODERATE_MM2,
    SHEET_EN_RE,
    SHEET_FRACTION_RE,
    SHEET_RU_RE,
    START_REPORT_FILE,
    THUMB_JPEG_QUALITY,
    THUMB_MAX_WIDTH,
    TOKEN_RE,
    UNCHANGED_DIFF_PERCENT,
    ZONES_MAJOR,
    ZONES_MINOR,
    ZONES_MODERATE,
)
from pdfcompare_core.diff_engine import DIFF_STRICTNESS_CHOICES, compute_diff, compute_diff_detailed, harmonize_canvas
from pdfcompare_core.exclusions import (
    exclusion_regions_to_pixel_boxes,
    normalize_exclude_regions,
)
from pdfcompare_core.html_css import REPORT_CSS_TOKENS
from pdfcompare_core.html_icons import REPORT_ICON_SVGS, report_icon
from pdfcompare_core.html_report import generate_html_report
from pdfcompare_core.live_report import (
    first_existing_rel,
    format_eta,
    live_report_labels,
    live_row_status,
    write_live_detail_view,
    write_live_html_report,
    write_live_slider_view,
)
from pdfcompare_core.markdown_report import write_engineer_report_md, write_summary_md
from pdfcompare_core.models import MatchPair, PageInfo
from pdfcompare_core.pdf_io import (
    atomic_write_text,
    build_page_info,
    copy_thumb,
    extract_sheet_mark,
    find_pages_dir,
    find_summary_json_path,
    imread_compat,
    imwrite_compat,
    internal_dir,
    normalize_sheet_mark,
    page_map_csv_path,
    page_tokens,
    render_page,
    render_page_gray,
    report_dir,
    report_pages_dir,
    safe_download_file_name,
    summary_json_path,
    write_start_page,
)
from pdfcompare_core.runner import (
    MAX_RUN_FOLDER_NAME_LEN,
    RunCancelled,
    _details_to_pairs,
    _page_value_to_idx,
    _write_run_summary_files,
    build_run_dir,
    compare_pdfs,
    process_pair_task,
    regenerate_report_pages,
    regenerate_report_pages_mixed,
    resolve_worker_count,
    sanitize_run_folder_name,
    validate_render_dpi,
)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
