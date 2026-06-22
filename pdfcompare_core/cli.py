"""CLI entry point for `python -m pdfcompare_core` and `python compare_pdfs.py`."""

from __future__ import annotations

import argparse
import multiprocessing
from pathlib import Path

from .constants import APP_NAME, APP_VERSION, START_REPORT_FILE
from .diff_engine import DIFF_STRICTNESS_CHOICES
from .exclusions import normalize_exclude_regions
from .runner import compare_pdfs


def pick_two_pdfs(folder: Path) -> tuple[Path, Path]:
    pdfs = sorted(folder.glob("*.pdf"))
    if len(pdfs) != 2:
        raise RuntimeError(f"Ожидалось ровно 2 PDF-файла в {folder}, найдено {len(pdfs)}")
    return pdfs[0], pdfs[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare two multi-page PDFs and build visual report.")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {APP_VERSION}")
    parser.add_argument("--old", type=Path, help="Path to file A (old/base)")
    parser.add_argument("--new", type=Path, help="Path to file B (new/target)")
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("TestDocs"),
        help="Folder with two PDFs (used if --old/--new omitted)",
    )
    parser.add_argument("--out-dir", type=Path, default=Path("runs"), help="Output runs folder")
    parser.add_argument("--run-name", type=str, default="", help="Optional exact result folder name inside --out-dir")
    parser.add_argument("--dpi", type=int, default=250, help="High DPI for final page diff rendering")
    parser.add_argument("--stroke-tol", type=float, default=2.0, help="Tolerance in pixels for line-thickness jitter")
    parser.add_argument(
        "--diff-strictness",
        choices=DIFF_STRICTNESS_CHOICES,
        default="normal",
        help="Diff sensitivity preset: strict detects more, loose ignores more small jitter",
    )
    parser.add_argument(
        "--exclude-region",
        action="append",
        default=[],
        metavar="X,Y,W,H",
        help="Exclude a page area from visual diff, in percent of page. Repeat for multiple areas.",
    )
    parser.add_argument("--lang", type=str, default="ru", choices=["ru", "en"], help="Report language")
    parser.add_argument("--workers", type=int, default=0, help="Parallel page workers; 0 means auto")
    parser.add_argument(
        "--keep-debug-images",
        action="store_true",
        help="Keep extra full-size debug PNGs such as b_raw.png and b_aligned.png",
    )
    args = parser.parse_args()

    if args.old and args.new:
        file_a = args.old
        file_b = args.new
    else:
        file_a, file_b = pick_two_pdfs(args.input_dir)

    run_dir = compare_pdfs(
        file_a,
        file_b,
        args.out_dir,
        high_dpi=args.dpi,
        stroke_tol_px=args.stroke_tol,
        exclude_regions=normalize_exclude_regions(";".join(args.exclude_region)),
        diff_strictness=args.diff_strictness,
        report_lang=args.lang,
        run_name=args.run_name or None,
        keep_debug_images=args.keep_debug_images,
        workers=args.workers,
    )
    print(f"Готово. Результаты: {run_dir}")
    print(f"Открыть отчёт: {run_dir / START_REPORT_FILE}")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
