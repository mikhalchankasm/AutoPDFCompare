# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PDFCompare Local is a standalone Windows desktop application for comparing two multi-page PDF documents. It identifies visual differences, performs page matching (including reorder detection), and generates interactive HTML report bundles with side-by-side comparisons and slider overlays. Designed for engineers reviewing document revisions. All processing is local — no cloud or AI API dependencies.

## Running the Application

```bash
# From source (GUI)
python pdfcompare_gui.py
# Or via batch launcher
.\run_gui.bat

# CLI comparison
python compare_pdfs.py --old file_a.pdf --new file_b.pdf --out-dir ./runs --dpi 250 --stroke-tol 2.0
```

## Dependencies

```bash
pip install PyMuPDF opencv-python numpy
```

GUI uses Tkinter (bundled with Python). Windows drag-and-drop uses ctypes.

## Building the Executable

```bash
pip install pyinstaller
pyinstaller PDFCompareLocal.spec
```

Output: `dist/PDFCompareLocal.exe` (single file, no console window, UPX-compressed).

## Architecture

Two source files constitute the entire application:

**`pdfcompare_gui.py`** — Tkinter GUI layer (~677 lines)
- `WindowsDropHook`: Native Windows Explorer drag-and-drop via ctypes/COM
- `PDFCompareApp`: Main window with file selection, DPI/tolerance options, progress bar, history tab
- Runs comparison in a worker thread to keep UI responsive
- Persists state (paths, history of up to 300 runs) to `~/.pdfcompare_local/state.json`

**`compare_pdfs.py`** — Core comparison engine (~1515 lines)
- **Page extraction**: `render_page()` renders via PyMuPDF; `build_page_info()` produces `PageInfo` (thumbnail, text tokens, dimensions, sheet mark)
- **Similarity**: Visual MSE on 160x160 grayscale thumbnails + Jaccard text similarity + sheet mark matching + size compatibility checks
- **Page alignment**: Dual strategy — `align_pages_hungarian()` (global assignment, supports many-to-one) and `align_pages_monotonic()` (sequence-preserving DP). `align_pages_v1()` picks the best result
- **Image registration**: `align_ecc()` for affine sub-pixel alignment before diffing
- **Diff detection**: `compute_diff()` uses distance transforms with configurable stroke tolerance, morphological filtering, watershed separation, and contour-based bbox detection (min area 180px²). Two-color overlay: pale blue (removed), bright red (added)
- **Classification**: diff% → unchanged (<0.15%), minor (<1%), moderate (<5%), major (≥5%)
- **Report generation**: Produces `report.json` (source of truth), `index.html` dashboard, per-page `views/<seq>.html` detail pages, `views/cmp_<seq>.html` slider comparisons, thumbnails, markdown summaries, CSV, and optional ZIP bundle

Data flow: GUI → worker thread → `compare_pdfs()` → page extraction → alignment → ECC registration → diff computation → report generation → output folder under `runs/run_YYYYMMDD_HHMMSS/`.

## Key Data Structures

- `PageInfo`: index, 160x160 grayscale thumbnail, text token set, dimensions, sheet mark
- `MatchPair`: paired page indices (a/b), status (matched/added/removed), similarity score

## Report Output Structure

Each run produces `runs/run_<timestamp>/` containing:
- `report_bundle/index.html` — main dashboard
- `report_bundle/report.json` — structured data model
- `report_bundle/views/` — per-page HTML comparison views
- `pages/<seq>__A_n__B_m/` — full-res images (a.png, b.png, overlay.png, mask.png, bbox_overlay.png, bboxes.json)
- `summary.md`, `engineer_report.md`, `page_map.csv`

## Conventions

- 4-space indentation, UTF-8
- snake_case for functions/variables, PascalCase for classes
- Conventional Commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`
- Russian/English bilingual support in text extraction (regex patterns handle both)
- `REPORT_RULES.md` contains the full technical specification for the report format and processing pipeline
- `AGENTS.md` contains proposed project structure for future reorganization into `src/`, `tests/`, `scripts/`, etc.
