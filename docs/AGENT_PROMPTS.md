# Agent Prompt Buttons

Copy one of these prompts into a local agent when you want it to connect PDFCompare MCP or compare PDFs.

## 1. One-Prompt MCP Setup

```text
Прочитай https://raw.githubusercontent.com/mikhalchankasm/AutoPDFCompare/master/SETUP_PROMPT.md и выполни инструкцию по подключению PDFCompare MCP. Используй stdio transport, имя сервера pdfcompare.
```

## 2. Connect Local Checkout

```text
Set up the local PDFCompare MCP server for this workspace.

Repository: D:\GitHub\PDFCompare
Use stdio transport only.

If dependencies are missing, run:
.\scripts\setup.ps1 -WithMcp

MCP server config:
{
  "mcpServers": {
    "pdfcompare": {
      "command": "D:\\GitHub\\PDFCompare\\.venv\\Scripts\\python.exe",
      "args": ["D:\\GitHub\\PDFCompare\\scripts\\pdfcompare_mcp.py"]
    }
  }
}

After connecting, use PDFCompare MCP tools instead of running compare_pdfs.py directly.
```

## 3. Update Installed MCP

```text
Обнови установленный PDFCompare MCP.

Repository folder: %LOCALAPPDATA%\PDFCompareMCP\AutoPDFCompare

Required flow:
1. Stop the MCP server or ask me to close the MCP client if needed.
2. Run git -C "%LOCALAPPDATA%\PDFCompareMCP\AutoPDFCompare" pull --ff-only origin master.
3. Run powershell -NoProfile -ExecutionPolicy Bypass -File "%LOCALAPPDATA%\PDFCompareMCP\AutoPDFCompare\scripts\setup.ps1" -WithMcp to refresh dependencies.
4. Tell me the old and new git commit hashes.
```

## 4. Compare Two PDFs

```text
Compare these two PDFs through the PDFCompare MCP server.

Old PDF: <old.pdf>
New PDF: <new.pdf>
Output folder: D:\GitHub\PDFCompare\runs

Required flow:
1. Call prepare_pdf_comparison first.
2. Show page counts, similar existing comparisons, and suggested_run_names.
3. Ask me for the final report folder name.
4. Ask whether to ignore any title block/stamp/author areas. If yes, collect percent boxes as x,y,w,h from the top-left page corner.
5. Ask for diff_strictness: strict, normal, or loose.
6. Call start_pdf_comparison with the selected run_name, diff_strictness, and exclude_regions.
7. Poll get_pdf_comparison_status until the job completes.
8. Return the final report_path and summary.counts.
```

## 5. Check Job Status

```text
Check this PDFCompare MCP job and report the current progress.

job_id: <job_id>

Use get_pdf_comparison_status(job_id). If completed, return report_path and summary.counts.
```
