# Changelog

## v0.1.6 - 2026-07-11

### Added
- Slider report mode: middle-mouse (wheel button) drag to draw a rectangle and zoom the view to fit that rectangle. Left-drag still moves the split divider; right-drag still pans; the browser's middle-click autoscroll is suppressed during the drag. Return to the full view with the existing Fit button or Ctrl+wheel-out.

## v0.1.5 - 2026-07-11

### Fixed
- Resolved out-of-memory crash (`cv2.error: -4 Insufficient memory`, ~1 GB allocation) on large A0/A1 sheets at high DPI. The two full-frame `distanceTransform` buffers are now computed and released one at a time instead of held simultaneously, halving peak memory in the diff engine.
- Added a render-area guard (`MAX_RENDER_MEGAPIXELS = 40`): pages rendered above this size are area-downscaled before the diff to keep memory bounded, while preserving stroke geometry.

## v0.1.4 - 2026-07-11

### Added
- GUI now exposes the same comparison controls as the MCP server: experimental bbox merge (toggle, gap, max-area ratio) and a debug-images toggle, wired through to `compare_pdfs`.
- Visual exclusion-region picker (✏ Pick…) on the Compare tab: draw one or more rectangles on a rendered PDF page instead of typing `x,y,w,h` by hand.
- Re-render tab now shows the `FG %` and `mm²` content-relative metrics per row, alongside `Diff %`.
- Re-render tab supports override fields (stroke tolerance, strictness, exclude regions, bbox merge) and a per-page (mixed-precision) mode that routes selected pages through `regenerate_report_pages_mixed`.
- CLI gained `--bbox-merge-gap-mm` and `--bbox-merge-max-area-ratio` flags for parity with GUI and MCP.

### Changed
- Moved packaging, requirements, launchers, and agent setup prompt files into dedicated folders to keep the repository root smaller.
- `start_pdf_comparison` signature in the MCP docs now lists the full parameter set (`diff_strictness`, `exclude_regions`, `bbox_merge_max_area_ratio`).

### Fixed
- PyInstaller spec resolves its root from `SPECPATH` after the spec moved into `packaging/`, so EXE builds work regardless of the invocation working directory.

## v0.1.3 - 2026-07-03

### Added
- Excluded page regions for ignoring title blocks, stamps, or author tables during visual diff.
- Diff strictness presets (`strict`, `normal`, `loose`) across CLI, GUI, and MCP.
- Content-relative `FG %` and physical `mm²` change metrics in report data and HTML.
- Safe per-page rerendering through MCP with visible custom-precision markers.

### Changed
- Bbox merging remains disabled by default and is documented as experimental.
- Optional bbox merging now groups from the diff mask and rejects sparse, page-sized groups.
- Change severity can use content-relative foreground percentage when available, not only whole-sheet page percentage.

## v0.1.2 - 2026-06-15

### Added
- Local stdio MCP server scripts and agent documentation for background PDF comparison jobs.
- Optional named result folders via `--run-name`, GUI report-name field, and shared run-name sanitization.
- Tests for named result folder sanitization and path construction.
- Copy-paste agent prompts for connecting PDFCompare MCP and starting comparisons.
- One-click Cursor/VS Code MCP setup buttons and `SETUP_PROMPT.md` for agent-driven installation.
- MCP bootstrap wrapper that refreshes dependencies, starts the stdio server, and supports opt-in repository updates.

### Changed
- Portable ZIP packaging now ships a runtime-focused set: core/UI modules, GUI/MCP launch scripts, and short user/agent docs.
- MCP dependencies are split into `requirements-mcp.txt`; base desktop installs stay lightweight.
- `pytest` is scoped to `tests/` so generated portable builds do not create duplicate test collection.
- Release/download links are surfaced as README buttons for direct EXE and portable ZIP access.

### Fixed
- OpenCV typing noise in lint/mypy checks for normalization and ECC calls.

## v0.1.1 - 2026-05-12

### Added
- Slider pages now have previous/next navigation between comparable sheets.
- Slider pages now include a hover/click sheet picker with status, diff percentage, change-zone count, and search.
- Detail and slider pages now include a `Save DIFF as` action for downloading the generated overlay image for the current sheet.

### Changed
- The current sheet highlight in report navigation is more visible with a green accent and stronger background.

## v0.1.0 - 2026-05-06

First public release of PDFCompare Local.

### Added
- Windows GUI for comparing two PDF revisions locally.
- CLI entry point with `--old`/`--new` or `--input-dir` modes.
- Visual HTML report with summary, mapped pages, OLD/NEW/DIFF views, and slider comparison.
- Page mapping that handles inserted and removed sheets.
- Parallel page comparison via `--workers`.
- RU/EN UI and report language support.
- Run history, configuration restore, and selected-page re-rendering.
- Portable Python ZIP packaging script.
- GitHub Actions pipeline for lint, tests, EXE build, portable ZIP build, and tagged releases.

### Changed
- Generated run internals are stored under `_pdfcompare/` with a lightweight `start.html` launcher at the run root.
- Full-size alignment debug images are disabled by default and can be restored with `--keep-debug-images`.

### Known Limitations
- No project license is declared yet.
- Current public test coverage focuses on change classification and report generation smoke checks.
