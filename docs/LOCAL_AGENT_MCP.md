# Local Agent MCP

PDFCompare exposes a local MCP server so any local LLM agent with stdio MCP support can compare PDFs without knowing the internal Python API.

For one-click setup buttons, see the repository `README.md`. For copy-paste setup prompts, see `SETUP_PROMPT.md` and `docs/AGENT_PROMPTS.md`.

## Tools

- `prepare_pdf_comparison(old_path, new_path, out_dir = "runs", lang = "ru")`
  - validates both PDF paths;
  - counts pages in both files;
  - checks `out_dir` for similar previous comparisons;
  - suggests result folder names;
  - tells the agent to ask the user which folder name to use.

- `start_pdf_comparison(old_path, new_path, out_dir, run_name, dpi = 250, stroke_tol = 2.0, workers = 0, lang = "ru", keep_debug_images = false)`
  - starts the comparison in a background Python process;
  - returns `job_id`, `run_dir`, `report_path`, status file, event log, and worker log.
  - optional `diff_strictness`: `strict`, `normal`, or `loose`;
  - optional `exclude_regions`: list of page areas to ignore, for example `[{"x":70,"y":80,"w":30,"h":20}]`.

- `get_pdf_comparison_status(job_id = "")`
  - with `job_id`: returns one job state, progress, live report path, and final summary when available;
  - without `job_id`: lists recent background jobs.

- `list_pdf_comparisons(out_dir = "runs", old_path = "", new_path = "", limit = 20)`
  - lists completed comparison folders, optionally filtered by the two PDF paths.

- `cancel_pdf_comparison(job_id)`
  - terminates a running background job.

## Agent Workflow

1. Call `prepare_pdf_comparison` with the two PDF paths and target output folder.
2. Tell the user:
   - page count for both PDFs;
   - whether similar comparisons already exist;
   - suggested folder names.
3. Ask the user what the result folder should be called.
4. Ask whether title blocks, stamps, author tables, or other zones should be ignored. Use percent coordinates `x,y,w,h` from top-left of the page.
5. Ask for strictness when it matters:
   - `strict`: more sensitive to small differences;
   - `normal`: default;
   - `loose`: ignores more small jitter/noise.
6. Call `start_pdf_comparison` with `run_name`, `diff_strictness`, and `exclude_regions`.
7. Continue other work if needed. Poll `get_pdf_comparison_status(job_id)` when the user asks for progress or before reporting completion.
8. When completed, give the user `report_path` and summarize counts from `summary.counts`.

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
Keep the server on stdio/local transport. Non-stdio transport is blocked unless `PDFCOMPARE_MCP_ALLOW_NETWORK=1` is set; do not enable it unless you also add an output-path allowlist for your environment.

For installed MCP clients, prefer the bootstrap wrapper:

```powershell
./scripts/run_mcp_bootstrap.ps1
```

The bootstrap wrapper logs to `.pdfcompare_mcp/bootstrap.log`, installs missing MCP dependencies, and then starts the stdio MCP server. It does not auto-update by default. To opt in for a trusted private setup, run it with `-AutoUpdate` or set `PDFCOMPARE_MCP_AUTO_UPDATE=1`; auto-update only pulls `origin/master` when the checkout is clean and currently on `master`.

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

If there is no venv, use the system Python after installing both `requirements.txt` and `requirements-mcp.txt`:

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
