# Changelog

## Unreleased

Fixes driven by an external repository review (all P1 findings and most P2 confirmed and addressed).

### Fixed
- **Render megapixel cap is now applied before rasterization**: the effective DPI is computed from the page geometry before `get_pixmap`, so an A0 sheet at high DPI no longer allocates a multi-gigabyte raster that was only downscaled afterwards.
- **Physical metrics honor the effective DPI**: when the cap reduces the render DPI, mm² areas, mm-based exclusion zones, and the bbox merge gap are computed from the DPI the raster actually has (previously they silently used the requested DPI — areas were understated up to ~2.4× on A0 at 250 DPI, and mm zones drifted). `summary.json` rows now record both `high_dpi` (requested) and `effective_dpi`.
- **Re-rendering is transactional**: page backups and pre-update copies of summary/CSV/MD now live until the whole update (pages + summary + HTML) succeeds; any failure rolls the run back to a fully consistent state. Previously the backups were deleted right after the page swap, so a failure while writing summary.json left new PNGs with stale metadata.
- **A failed comparison no longer blocks its run name**: the partial run folder is renamed to `<name>.failed-…` (kept for debugging), so the same name can be retried immediately.
- **`scripts/test.ps1` propagates the pytest exit code** — CI can no longer publish a release with failing tests; mypy is now a hard lint gate too.
- **Cancelling a comparison stops queued pages**: pending ProcessPool futures are cancelled on cancel/error instead of grinding to the end.
- **Tkinter is no longer touched from worker threads**: re-render workers receive the report language as a plain string, and the update-check timestamp is saved via the UI-thread event queue.
- **CLI**: passing only one of `--old`/`--new` is now an explicit error instead of silently falling back to `--input-dir`.
- **Uniform DPI validation (72–1200)** for GUI, CLI, MCP, and per-page re-render overrides; per-page dialog no longer crashes on unparseable stroke/gap values.

### Added
- **Auto-update integrity check**: CI publishes `SHA256SUMS.txt` with every release; the in-app updater downloads the manifest, verifies the installer's SHA-256 before launching it, deletes the file on mismatch, and refuses silent install for releases without a manifest (falls back to the download page).
- **PR checks**: the workflow now runs lint + tests on pull requests in a read-only job; release permissions are limited to the build/publish job.
- **Coverage gate**: `scripts/test.ps1` (and therefore CI) fails if `pdfcompare_core` coverage drops below 82% (actual: ~85%; GUI is intentionally out of scope).
- **Schematic sheet mode in the exclusion picker**: choosing a format manually (A4–A0) switches the preview from the real page to a blank sheet of that format in true proportions — with a GOST-style drawing frame and a dashed 185×55 mm title-block guide in the bottom-right corner — so stamp zones can be traced on a clean sheet instead of a live drawing. "Auto" restores the real page render; the canvas resizes to the chosen format's aspect.
- **Backdrop PDF in the exclusion picker**: the "Подложка…" button loads any other PDF as the visual reference (e.g. a clean template sheet); zones stay in percent of the page and apply to the compared documents as usual. The chosen backdrop is persisted in the app state and preloaded next time; the page switcher follows the backdrop's page count.

### Fixed (history)
- History records now store the bbox-merge options (on/off, gap, max ratio) and the debug-images flag, so "Из истории" restores every parameter instead of resetting them to defaults; snapshot records now capture the full input set (previously they lacked even strictness and exclusion zones, and restoring a snapshot wiped the zones field).
- **License**: the repository is now MIT-licensed (note: the PyMuPDF dependency remains AGPL-3.0/commercial, and its terms apply to distributed builds regardless).

## v0.1.14 - 2026-07-12

### Added
- **Windows installer** (`PDFCompareLocal-setup.exe`, Inno Setup): per-user install without admin rights, Start menu / desktop shortcuts, clean uninstall, in-place upgrades. Built by CI and attached to every release.
- **In-app auto-update**: when a new release is available, the packaged app offers "Download and install now" — it downloads the installer, updates silently (`/SILENT`) and restarts itself. Running from source keeps the previous "open the release page" flow; the version can still be skipped.
- **MCP: text forms for exclude zones** — `start_pdf_comparison` and `rerender_pdf_comparison_pages` accept `exclude_regions` as text (percent `"x,y,w,h;…"` or JSON with `unit`/`anchor`) in addition to object lists, matching the GUI field exactly; an empty string on re-render means "inherit". Tool docstrings and the agent prompt document all forms.
- **MCP: picker parity** — `pick_pdf_exclude_region` now opens the same visual editor as the GUI (mm grid, paper formats, multiple regions, move/resize, per-region corner anchors) and returns an `exclude_regions` list; `existing` zones open for editing, `anchor` preselects the anchor for new boxes.

### Changed
- README redesigned: annotated GUI screenshot with a numbered zone legend, install options table (installer / portable EXE / from source), exclude-zone syntax reference with mm/anchor examples, report overview, and update behavior.

### Fixed
- "Выбрать…" dialogs (old/new PDF, output folder) now open at the folder already written in the field instead of the OS's last-used location.
- "Открыть папку" falls back to the output folder from the field when no comparison has been run yet, instead of only showing "folder not set".
- If tkinterdnd2 is importable but its tkdnd Tcl package fails to load, the app now starts without drag-and-drop (with the status-bar notice) instead of crashing on launch.

## v0.1.13 - 2026-07-12

### Added
- **Exclusion picker rework**: the visual exclude-region dialog now shows a millimetre grid overlay (off/5/10/25/50 mm step), auto-detects the paper format (A4/A3/A2/A1/A0, with manual override for scans whose nominal size differs), and displays a live size label in mm while drawing. Drawn boxes can be selected, moved, resized via 8 handles, and deleted (Del); each box shows its size in mm. Multi-page PDFs get a page switcher. Regions already present in the "Exclude regions" field open as editable boxes, and OK writes the edited set back (so zones can also be removed).
- **Region anchors in the picker**: each zone can be anchored to any page corner (↖/↗/↙/↘). A bottom-right-anchored stamp zone stays in place on sheets of different formats. The anchored corner is marked on the box; the size label and the toolbar readout show offsets from that corner. Anchored sets are written to the field as JSON (`unit: percent`, `anchor: …`); plain top-left sets keep the old `x,y,w,h` text.
- **Exclude picker in the re-render tab**: the uniform "Exclude regions" field got the same picker button. It opens the loaded run's old PDF (the selected row's page when exactly one row is selected) with the field's current zones pre-loaded for editing.

### Fixed
- Pinned sidebar squeezed the whole slider view into the 48px header row: the comparison stage collapsed to the top and auto-fit zoomed to ~1%. The main column now owns the header/stage/controls rows itself; the page grid only splits sidebar/content columns.
- Pin state was not saved to localStorage due to an undefined variable in the pin handler (also broke the button label update).
- Toggling the pin now re-fits the image to the new viewport width after the sidebar transition.
- Slider header no longer overlaps: the title metrics clip with an ellipsis and button labels collapse to icons when the content column is narrow (container queries).
- Embedded slider (iframe on the sheet view page) no longer reserves the 300px pinned sidebar column; the drawer is hidden in embed mode.

## v0.1.12 - 2026-07-12

### Added
- Slider report sidebar is now **pinned by default**: the sheet navigation panel is visible on the left and pushes the comparison content to the right, so you can click any sheet without hovering the edge. A 📌 button in the panel header toggles to the previous floating (hover-to-open) mode. The pin state persists across pages via localStorage.

## v0.1.11 - 2026-07-12

### Changed
- Update check interval reduced from 24 hours to 1 hour.
- Replaced the gear (⚙) icon with an explicit refresh icon (↻) for "check for updates" in the header.

## v0.1.10 - 2026-07-12

### Changed
- The primary change metric is now **% of drawn content** (foreground-relative), not % of the whole sheet. On large A0/A1 drawings where lines cover 3–10% of the page, a significant change that previously read as "0.1%" now shows a meaningful percentage relative to the actual drawing content.
- Composite severity classification: the change level (minor/moderate/major) is now the maximum across three independent signals — FG% (≥1/8/20%), largest change region in mm² (≥100/2500/10000), and number of change zones (≥1/15/40). A significant change is no longer masked by a mostly-empty sheet.
- HTML report: the change matrix leads with the FG% meter bar (heat colors keyed to 1/8/20%); sheet diff% is secondary. Per-page toolbar, slider header, and navigation show FG% first.
- Markdown and live reports: FG% column added ahead of sheet diff%; engineer report sorts by FG%.
- GUI re-render tab: "Drawn %" column promoted ahead of "Diff %".
- Page note: "Changed ≈ X% of drawn content (Y mm², zones: N, max zone: Z mm²)".

### Added
- `foreground_sparse` flag: pages with less than 0.05% drawn content are flagged; on such pages FG% is unreliable and classification falls back to absolute metrics (mm², zones).
- FG% is clamped to 100.0 (mask morphing could push it past 100 on near-empty pages).
- Legend updated to the 1/8/20% FG thresholds.

### Compatibility
- Legacy runs without `foreground_sparse` / `diff_foreground_percent` fall back to the old diff-percent classification and render with "—" for missing fields.

## v0.1.9 - 2026-07-12

### Fixed
- Resolved "coordinates must fit in 0..100%" error when using the visual exclusion picker. The picker rounded x and w independently, so their sum could exceed 100% by a tiny amount and be rejected by validation. The picker now clamps the width/height so x+w and y+h never exceed 100; the validator also tolerates sub-0.01% overflow from rounding instead of rejecting it.

## v0.1.8 - 2026-07-11

### Changed
- Increased default window height (740→820 px) and minimum height (640→700 px) so the bottom action buttons are visible on launch.
- Replaced the bbox-merge and debug-images on/off chips with checkboxes so the pressed/unpressed state is visually obvious.
- Reformulated the stroke-tolerance hint to explain what higher and lower values do.
- Removed the Workers (Auto/1/4) control entirely; the app always uses automatic parallel processing.
- Open Report and Open Folder buttons next to Run are now always enabled and show an informational message when no report/folder exists, instead of being greyed out.
- Removed the duplicate Open report / Open folder hyperlinks from the status bar.

### Added
- A bold, clickable "✓ Report ready to open" banner appears in the status bar as soon as a live report is available mid-comparison, and disappears when the run completes, is cancelled, or errors out.
- Hint label under the report-name field explaining it is optional (empty = auto timestamped folder).

## v0.1.7 - 2026-07-11

### Added
- Auto-update check: on launch the app queries the GitHub releases API (at most once per 24h) and, if a newer version exists, shows a dialog with a link to the download page plus a clickable update badge in the header. The gear icon in the top-right triggers a manual check. Users can skip a specific version to suppress repeated prompts. Network failures are silent on automatic checks.

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
