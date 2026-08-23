# Local Agent MCP

PDFCompare exposes a local MCP server so any local LLM agent with stdio MCP support can compare PDFs without knowing the internal Python API.

For one-click setup buttons, see the repository `README.md`. For copy-paste setup prompts, see `docs/SETUP_PROMPT.md` and `docs/AGENT_PROMPTS.md`.

## Tools

- `check_pdfcompare_update(fetch = true)`
  - reports the running version, the MCP checkout's branch/commit, and how many commits it is behind `origin/master`;
  - names anything that blocks the automatic pull (not on `master`, uncommitted changes);
  - `fetch = false` compares against already-fetched refs without network access.

- `prepare_pdf_comparison(old_path, new_path, out_dir = "runs", lang = "ru")`
  - validates both PDF paths;
  - counts pages in both files;
  - checks `out_dir` for similar previous comparisons;
  - suggests result folder names;
  - tells the agent to ask the user which folder name to use.

- `start_pdf_comparison(old_path, new_path, out_dir, run_name, dpi = 250, stroke_tol = 2.0, diff_strictness = "normal", exclude_regions = None, bbox_merge_gap_mm = 0.0, bbox_merge_max_area_ratio = 16.0, workers = 0, lang = "ru", keep_debug_images = false, ignore_line_weight = false)`
  - `ignore_line_weight = true` подавляет утолщение/утоньшение штрихов на прежней оси; новые и смещённые линии остаются изменениями.
  - автоматическое многоступенчатое совмещение всегда включено: оно компенсирует небольшой перенос, поворот и масштаб до расчёта diff; зоны исключения не участвуют в оценке преобразования;
  - `summary.json` сохраняет метод/качество совмещения, X/Y в пикселях и миллиметрах, поворот и масштаб для каждой сопоставленной пары;
  - starts the comparison in a background Python process;
  - returns `job_id`, `run_dir`, `report_path`, status file, event log, and worker log.
  - `diff_strictness`: `strict`, `normal`, or `loose` (default `normal`);
  - `exclude_regions`: page areas to ignore. Accepts the same forms as the GUI field:
    - percent text `"x,y,w,h; x2,y2,w2,h2"` (top-left anchor), e.g. `"70,80,30,20"`;
    - a JSON string or list of objects `{"x","y","w","h","unit","anchor","label"}` with `unit` = `percent` (default) / `mm` / `px` and `anchor` = `top_left` (default) / `top_right` / `bottom_left` / `bottom_right` — x/y are offsets from that corner, so a `bottom_right` stamp zone holds on any sheet format, e.g. `[{"x":10,"y":10,"w":60,"h":30,"unit":"mm","anchor":"bottom_right"}]`;
    - a list of 4-number lists (percent, top-left);
  - `bbox_merge_gap_mm`: experimental merge of nearby/overlapping change boxes within this distance; default is `0.0` mm, meaning disabled;
  - `bbox_merge_max_area_ratio`: prevents distant thin changes from becoming one huge empty rectangle; default is `16.0`, with an additional page-area guard;
  - `keep_debug_images`: when `true`, keeps full-size alignment debug images (increases report size).

- `preview_pdf_comparison(old_path, new_path, out_dir, run_name, dpi = 250, stroke_tol = 2.0, diff_strictness = "normal", exclude_regions = [...], bbox_merge_gap_mm = 0, ...)`
  - builds the **final pre-launch checklist without starting anything**: it validates and normalizes exactly what `start_pdf_comparison` would (paths, run-folder name, DPI, strictness, exclusion zones, output collision), so it never green-lights a run start would reject;
  - returns page counts + page delta, the precision settings with a `*_is_default` flag on each, automatic-alignment status, an `exclude_regions` summary (count + one line per zone), the bbox-merge setting, and the output folder / run name / run_dir;
  - takes the same arguments as `start_pdf_comparison`, so after the user confirms, the start call is a straight copy. Call it right before `start_pdf_comparison`.

- `rerender_pdf_comparison_pages(run_dir, seqs = [4], dpi = 500, stroke_tol = 0, diff_strictness = "strict", exclude_regions = [...], ignore_line_weight = true)`
  - re-renders selected rows of an existing report in place and rebuilds one combined report;
  - use after a full compare when a user says "recalculate sheet 4 with higher precision";
  - `exclude_regions` accepts the same text/JSON/list forms as `start_pdf_comparison`; an empty string means "inherit from the original run";
  - `page_settings` can provide different settings per row, e.g. `[{"seq":4,"dpi":500,"stroke_tol":0,"diff_strictness":"strict"},{"seq":7,"dpi":300,"diff_strictness":"loose","exclude_regions":"70,80,30,20"}]`.

- `preview_pdf_vision_analysis(run_dir, excluded_seqs = None, max_sheets = 12, model = "", provider = "", lang = "ru")`
  - performs no network calls and returns the exact sheet list eligible for external visual analysis;
  - eligibility is strict: only `matched` rows with both OLD and NEW pages, a non-`unchanged` level, and non-zero diff metrics;
  - lists skipped sheet numbers by reason (`added`, `removed`, `one_sided`, `not_matched`, `unchanged`, `no_diff`, `excluded`), current cache state, existing report paths, provider configuration state, and safe local setup guidance;
  - includes the external-transfer warning an agent must show before requesting confirmation.

- `analyze_pdf_comparison_with_ai(run_dir, provider = "", confirm_external_upload = false, excluded_seqs = None, seqs = None, max_sheets = 12, max_zones = 8, model = "", lang = "ru")`
  - with the default `confirm_external_upload=false`, behaves as a no-network preview and returns `analysis_started=false`;
  - only after the user explicitly agrees, call it with `confirm_external_upload=true`; the MCP server then sends generated JPEG montages (OLD, NEW, DIFF, numbered boxes and OLD/NEW crops) to the selected external API;
  - never sends source PDF files, added/removed sheets, one-sided rows, or any row rejected by the preview filter;
  - `provider` accepts `deepseek` or `qwen`; when omitted, `PDFCOMPARE_VISION_PROVIDER` is used, then `deepseek` as the compatible default;
  - reads the engineer's key only from the MCP environment. DeepSeek uses `DEEPSEEK_API_KEY`; Qwen uses `QWEN_API_KEY`, `QWEN_BASE_URL`, and optionally `QWEN_MODEL`. No API-key tool argument exists;
  - validates Qwen URLs as official Alibaba Model Studio HTTPS `compatible-mode/v1` endpoints before attaching the key, preventing an accidental upload to an arbitrary host;
  - caches successful descriptions separately by provider, model, language, and prompt version, then writes an interactive HTML report, Markdown `report.md`, machine-readable JSON, and a downloadable ZIP under `<run_dir>/_pdfcompare/vision_analysis/`;
  - the report root is a sheet matrix; every analyzed sheet has a separate page with a full-resolution PNG OLD/NEW slider, AI zones, lossless detail crops, zoom, pan, bottom sheet navigation, and Markdown copy. Noise zones are visible by default and use a distinct blue outline;
  - DeepSeek returns a USD estimate from actual token usage: direct API, the same inference through OpenRouter, OpenRouter's proportional credit-purchase fee, and the peak-rate comparison. Qwen returns token usage without a built-in price estimate because Alibaba tariffs depend on region/account. Locally cached sheets count as zero new spend;
  - `seqs` can narrow a confirmed batch, `max_sheets` is 1..50, and `max_zones` is 1..20. The call is synchronous and can take several minutes when many sheets are not cached.

- `analyze_pdf_comparison_with_deepseek(...)`
  - backward-compatible DeepSeek-only alias; new integrations should use `analyze_pdf_comparison_with_ai`.

- `pick_pdf_exclude_region(pdf_path, page_number = 1, anchor = "top_left", existing = None)`
  - opens the same visual picker as the GUI: a blank sheet of the detected format (A4..A0, portrait/landscape), mm grid, live mm size labels, several regions at once, move/resize via handles, per-region corner anchor;
  - `anchor` preselects the anchor for newly drawn regions; `existing` (same forms as `exclude_regions`) opens current zones for editing;
  - returns `exclude_regions` (list) ready for `start_pdf_comparison` / `rerender_pdf_comparison_pages` — **in millimetres from each region's anchor corner** (`unit: "mm"`), which is what makes one zone valid on every sheet format; an empty list means the user removed all zones; `exclude_region` (first item) is kept for older callers.

- `get_pdf_comparison_status(job_id = "")`
  - with `job_id`: returns one job state, progress, live report path, and final summary when available;
  - without `job_id`: lists recent background jobs.

- `list_pdf_comparisons(out_dir = "runs", old_path = "", new_path = "", limit = 20)`
  - lists completed comparison folders, optionally filtered by the two PDF paths — a live scan of one `out_dir` on disk, not a history log.

- `list_comparison_history(limit = 50, source = "")`
  - the persistent comparison log shared by the GUI and this server, stored in `~/.pdfcompare_local/` (the user's home, **not** this checkout), so it survives a fresh MCP clone or a GUI reinstall;
  - one merged, numbered list, newest first: each row has `index` (position, for "restore #5"), a stable `id` (`mcp:<job>` / `ui:<hash>`), `source` (`ui` = GUI History tab, `mcp` = started here), `date`, `result`, the two file names, `out_dir`, `run_dir`;
  - pass `source="ui"` or `source="mcp"` to see one origin; the `index` is valid against the most recent listing — prefer the `id` if another run finished in between.

- `restore_comparison(ref, out_dir = "", run_name = "", confirm = false, source = "")`
  - re-runs a past comparison from history; `ref` is a position (`"5"` / `"#5"`) or a stable `id`;
  - **step 1** (`confirm=false`, default): resolves the record and returns its inputs, options, whether the source PDFs still exist, and a non-colliding `suggested_run_name` — nothing runs yet;
  - **step 2** (`confirm=true`): starts a fresh comparison with those inputs; the original run folder is never touched — the result goes to a new folder (record's `out_dir` + `suggested_run_name` by default; override with `out_dir`/`run_name`). Returns a `job_id` to poll like any other run.

- `cancel_pdf_comparison(job_id, grace_sec = 20)`
  - asks the worker to stop and unwind (a re-render updates a report in place, so a killed worker could leave it half-updated); force-kills only if the worker does not exit within `grace_sec`, and then reports `forced: true`.

## Agent Workflow

1. Call `prepare_pdf_comparison` with the two PDF paths and target output folder.
2. Tell the user:
   - page count for both PDFs;
   - whether similar comparisons already exist;
   - suggested folder names.
3. Ask the user what the result folder should be called.
4. Ask whether title blocks, stamps, author tables, or other zones should be ignored. **Prefer mm + anchor**: `[{"x":0,"y":0,"w":185,"h":55,"unit":"mm","anchor":"bottom_right"}]` is a title block that stays 185×55 mm on A4 and on A0 alike. Percent boxes (`"70,80,30,20"`, top-left) scale with the sheet — the same box covers a quarter of an A0 — so use them only for zones that *should* stretch. Or call `pick_pdf_exclude_region` to let the user draw the areas.
5. Ask for strictness when it matters:
   - `strict`: more sensitive to small differences;
   - `normal`: default;
   - `loose`: ignores more small jitter/noise.
6. If the user did not already mention bbox merging, ask whether to enable experimental merging of nearby bbox regions. Recommend keeping it disabled unless the user explicitly wants grouped boxes. Offer the current limits: disabled by default with `bbox_merge_gap_mm=0`; a typical trial value is `5` mm; `bbox_merge_max_area_ratio=16` plus a page-area/sparse-fill guard limits over-merging.
7. Call `preview_pdf_comparison` with the chosen settings and show the user the returned checklist — old file, new file, tolerances/strictness, automatic alignment, excluded zones (or "none"), and the output folder + name. Ask whether to start as-is or change a specific line. Only after confirmation call `start_pdf_comparison` with the same arguments.
8. Continue other work if needed. Poll `get_pdf_comparison_status(job_id)` when the user asks for progress or before reporting completion.
9. When completed, give the user `report_path` and summarize counts from `summary.counts`. The HTML report shows both page-level `Diff %` and content-relative `FG %`, plus physical changed area in `mm²`.
10. If a specific report row needs higher precision, call `rerender_pdf_comparison_pages` with the existing `run_dir` and target `seq`; the report is rebuilt in place.
11. If the user asks for a semantic AI description, call `preview_pdf_vision_analysis` first and show the exact eligible list plus `external_upload_warning`. Do not infer consent from the configured API key or from an earlier PDF comparison.
12. Only after explicit consent call `analyze_pdf_comparison_with_ai(..., provider="deepseek|qwen", confirm_external_upload=true)`. Return `report_html_path` for browser/mobile viewing, `report_markdown_path` for Markdown, and `report_zip_path` for transfer/download. Treat the model text as advisory and keep the engine metrics as the source of truth.

Do not run `compare_pdfs.py` directly from an agent unless MCP is unavailable. The MCP server preserves background job state in `.pdfcompare_mcp/jobs/`.

## Run Locally

Install dependencies:

```powershell
./scripts/setup.ps1 -WithMcp
```

Start the MCP server manually for smoke testing:

```powershell
./scripts/run_mcp.ps1
```

The server uses stdio, so it waits for an MCP client and does not print a web URL.
Keep the server on stdio/local transport. Non-stdio transport is blocked unless **both** `PDFCOMPARE_MCP_ALLOW_NETWORK=1` and `PDFCOMPARE_MCP_ALLOWED_DIRS` are set — the latter is a `os.pathsep`-separated list of directories the tools may read and write, and it is enforced (paths are resolved first, so symlinks cannot escape). Without it the server would expose the whole user profile. The allowlist also works on stdio if you want to confine a local agent.

For installed MCP clients, prefer the bootstrap wrapper:

```powershell
./scripts/run_mcp_bootstrap.ps1
```

The bootstrap wrapper logs to `.pdfcompare_mcp/bootstrap.log`, installs missing MCP dependencies, and then starts the stdio MCP server.

For optional visual analysis, configure a personal provider key in the environment of the MCP process. Enter secrets locally — never in a chat, prompt, or tool argument.

DeepSeek for the current PowerShell session:

```powershell
$env:DEEPSEEK_API_KEY = "<your key>"
$env:PDFCOMPARE_VISION_PROVIDER = "deepseek"
./scripts/run_mcp.ps1
```

Qwen / Alibaba Model Studio for the current PowerShell session:

```powershell
$env:QWEN_API_KEY = "<your key>"
$env:QWEN_BASE_URL = "<official Alibaba compatible-mode/v1 endpoint>"
$env:QWEN_MODEL = "qwen3.8-max"
$env:PDFCOMPARE_VISION_PROVIDER = "qwen"
./scripts/run_mcp.ps1
```

To keep a key between restarts, add the same variables to the Windows user environment or to the MCP client's local environment configuration, then fully restart the MCP client. Do not commit the values to this repository. Optional tuning variables are `PDFCOMPARE_DEEPSEEK_VISION_MODEL`, `PDFCOMPARE_DEEPSEEK_TIMEOUT_SEC`, `PDFCOMPARE_DEEPSEEK_MAX_TOKENS`, `PDFCOMPARE_QWEN_TIMEOUT_SEC`, and `PDFCOMPARE_QWEN_MAX_TOKENS`. Ordinary PDF comparison remains fully local and does not require any AI key.

**Auto-update is on by default.** On every server start the wrapper pulls `origin/master` and re-runs `setup.ps1 -WithMcp` if the requirements or HEAD changed — so restarting the MCP client is all it takes to update. The MCP checkout is independent of the installed GUI: the installer and the app's auto-update replace `PDFCompareLocal.exe` only and never touch it.

The pull is skipped (and logged) when the checkout is not on `master` or has uncommitted changes. Turn auto-update off with `-NoAutoUpdate` or `PDFCOMPARE_MCP_AUTO_UPDATE=0`, then update by hand:

```powershell
git -C "$env:LOCALAPPDATA\PDFCompareMCP\AutoPDFCompare" pull --ff-only origin master
```

The `check_pdfcompare_update` tool reports the running version, the checkout's commit, how many commits it is behind `origin/master`, and anything that would block the pull (wrong branch, dirty tree). Pass `fetch=false` to check without touching the network.

The one-click clone phase logs to `%TEMP%\pdfcompare_mcp_bootstrap.log`; after the repository exists, bootstrap logs go to `.pdfcompare_mcp/bootstrap.log`.

## MCP Client Config

Use the venv Python if available:

```json
{
  "mcpServers": {
    "pdfcompare": {
      "command": "D:\\GitHub\\PDFCompare\\.venv\\Scripts\\python.exe",
      "args": ["D:\\GitHub\\PDFCompare\\scripts\\pdfcompare_mcp.py"]
    }
  }
}
```

If there is no venv, use the system Python after installing both `requirements/base.txt` and `requirements/mcp.txt`:

```json
{
  "mcpServers": {
    "pdfcompare": {
      "command": "python",
      "args": ["D:\\GitHub\\PDFCompare\\scripts\\pdfcompare_mcp.py"]
    }
  }
}
```

Most MCP clients, including Claude Desktop, Cursor, Open Code-style clients, and local Codex-compatible setups, use this same stdio shape: a command plus args.

Bootstrap config for a user-level install:

```json
{
  "mcpServers": {
    "pdfcompare": {
      "command": "powershell",
      "args": [
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        "$ErrorActionPreference='Stop'; $repo=Join-Path $env:LOCALAPPDATA 'PDFCompareMCP\\AutoPDFCompare'; $log=Join-Path $env:TEMP 'pdfcompare_mcp_bootstrap.log'; if (!(Test-Path $repo)) { New-Item -ItemType Directory -Force -Path (Split-Path $repo) *> $log; git clone https://github.com/mikhalchankasm/AutoPDFCompare.git $repo *>> $log }; & (Join-Path $repo 'scripts\\run_mcp_bootstrap.ps1')"
      ]
    }
  }
}
```

## Direct CLI Fallback

If an agent cannot use MCP, it can still run:

```powershell
python compare_pdfs.py --old "old.pdf" --new "new.pdf" --out-dir runs --run-name "My_Comparison"
python compare_pdfs.py --old "old.pdf" --new "new.pdf" --exclude-region "70,80,30,20" --diff-strictness loose
```

This fallback blocks the calling process and does not provide the MCP background job controls.
