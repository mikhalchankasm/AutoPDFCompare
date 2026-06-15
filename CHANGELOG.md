# Changelog

## Unreleased

_Nothing yet._

## v0.1.2 - 2026-06-15

### Added
- Local stdio MCP server scripts and agent documentation for background PDF comparison jobs.
- Optional named result folders via `--run-name`, GUI report-name field, and shared run-name sanitization.
- Tests for named result folder sanitization and path construction.
- Copy-paste agent prompts for connecting PDFCompare MCP and starting comparisons.
- One-click Cursor/VS Code MCP setup buttons and root `SETUP_PROMPT.md` for agent-driven installation.
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
