# Changelog

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
