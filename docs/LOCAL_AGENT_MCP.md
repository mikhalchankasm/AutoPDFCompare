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

- `start_pdf_comparison(old_path, new_path, out_dir, run_name, dpi = 250, stroke_tol = 2.0, diff_strictness = "normal", exclude_regions = None, bbox_merge_gap_mm = 0.0, bbox_merge_max_area_ratio = 16.0, workers = 0, lang = "ru", keep_debug_images = false)`
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

- `rerender_pdf_comparison_pages(run_dir, seqs = [4], dpi = 500, stroke_tol = 0, diff_strictness = "strict", exclude_regions = [...])`
  - re-renders selected rows of an existing report in place and rebuilds one combined report;
  - use after a full compare when a user says "recalculate sheet 4 with higher precision";
  - `exclude_regions` accepts the same text/JSON/list forms as `start_pdf_comparison`; an empty string means "inherit from the original run";
  - `page_settings` can provide different settings per row, e.g. `[{"seq":4,"dpi":500,"stroke_tol":0,"diff_strictness":"strict"},{"seq":7,"dpi":300,"diff_strictness":"loose","exclude_regions":"70,80,30,20"}]`.

- `pick_pdf_exclude_region(pdf_path, page_number = 1, anchor = "top_left", existing = None)`
  - opens the same visual picker as the GUI: a blank sheet of the detected format (A4..A0, portrait/landscape), mm grid, live mm size labels, several regions at once, move/resize via handles, per-region corner anchor;
  - `anchor` preselects the anchor for newly drawn regions; `existing` (same forms as `exclude_regions`) opens current zones for editing;
  - returns `exclude_regions` (list) ready for `start_pdf_comparison` / `rerender_pdf_comparison_pages` — **in millimetres from each region's anchor corner** (`unit: "mm"`), which is what makes one zone valid on every sheet format; an empty list means the user removed all zones; `exclude_region` (first item) is kept for older callers.

- `get_pdf_comparison_status(job_id = "")`
  - with `job_id`: returns one job state, progress, live report path, and final summary when available;
  - without `job_id`: lists recent background jobs.

- `list_pdf_comparisons(out_dir = "runs", old_path = "", new_path = "", limit = 20)`
  - lists completed comparison folders, optionally filtered by the two PDF paths.

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
7. Call `start_pdf_comparison` with `run_name`, `diff_strictness`, `exclude_regions`, and the selected bbox merge settings.
8. Continue other work if needed. Poll `get_pdf_comparison_status(job_id)` when the user asks for progress or before reporting completion.
9. When completed, give the user `report_path` and summarize counts from `summary.counts`. The HTML report shows both page-level `Diff %` and content-relative `FG %`, plus physical changed area in `mm²`.
10. If a specific report row needs higher precision, call `rerender_pdf_comparison_pages` with the existing `run_dir` and target `seq`; the report is rebuilt in place.

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
