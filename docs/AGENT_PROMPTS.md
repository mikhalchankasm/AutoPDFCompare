# Agent Prompt Buttons

Copy one of these prompts into a local agent when you want it to connect PDFCompare MCP or compare PDFs.

## 1. Connect PDFCompare MCP

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

## 2. Compare Two PDFs

```text
Compare these two PDFs through the PDFCompare MCP server.

Old PDF: <old.pdf>
New PDF: <new.pdf>
Output folder: D:\GitHub\PDFCompare\runs

Required flow:
1. Call prepare_pdf_comparison first.
2. Show page counts, similar existing comparisons, and suggested_run_names.
3. Ask me for the final report folder name.
4. Call start_pdf_comparison with the selected run_name.
5. Poll get_pdf_comparison_status until the job completes.
6. Return the final report_path and summary.counts.
```

## 3. Check Job Status

```text
Check this PDFCompare MCP job and report the current progress.

job_id: <job_id>

Use get_pdf_comparison_status(job_id). If completed, return report_path and summary.counts.
```
