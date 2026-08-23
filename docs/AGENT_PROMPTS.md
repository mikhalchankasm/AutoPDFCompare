# Agent Prompt Buttons

Copy one of these prompts into a local agent when you want it to connect PDFCompare MCP or compare PDFs.

## 1. One-Prompt MCP Setup

```text
Прочитай https://raw.githubusercontent.com/mikhalchankasm/AutoPDFCompare/master/docs/SETUP_PROMPT.md и выполни инструкцию по подключению PDFCompare MCP. Используй stdio transport, имя сервера pdfcompare.
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
4. Ask whether to ignore any title block/stamp/author areas. If yes, prefer millimetres from a corner: [{"x":0,"y":0,"w":185,"h":55,"unit":"mm","anchor":"bottom_right"}] keeps a title block at 185x55 mm on every sheet format. Percent boxes (x,y,w,h from the top-left corner) scale with the sheet, so use them only when the zone should stretch with it.
5. Ask for diff_strictness: strict, normal, or loose.
6. If I did not already say whether to merge nearby bbox regions, ask me. Treat merge as experimental and recommend keeping it disabled unless I explicitly want grouped boxes. Explain the available limits: bbox_merge_gap_mm defaults to 0 mm (disabled); a typical trial value is 5 mm; bbox_merge_max_area_ratio defaults to 16, with page-area and sparse-fill guards to avoid huge empty rectangles.
7. Call start_pdf_comparison with the selected run_name, diff_strictness, exclude_regions, and bbox merge settings.
8. Poll get_pdf_comparison_status until the job completes.
9. Return the final report_path and summary.counts. When judging change severity, prefer the content-relative FG % and physical mm² metrics over whole-page Diff %, since Diff % is dominated by empty page area on engineering drawings.
```

## 5. Check Job Status

```text
Check this PDFCompare MCP job and report the current progress.

job_id: <job_id>

Use get_pdf_comparison_status(job_id). If completed, return report_path and summary.counts.
```

## 6. Describe Changed Sheets with External Vision AI

```text
Prepare an optional DeepSeek or Qwen visual description for this completed PDFCompare run:

run_dir: <completed run folder>

Required two-step flow:
1. Call preview_pdf_vision_analysis(run_dir, provider="deepseek|qwen"). This step must not access the network.
2. Show me the exact eligible_sheets list, all skipped counts, and external_upload_warning.
3. If setup_required=true, show key_setup.message. Never request or accept an API key in chat or a tool argument.
4. Ask whether I explicitly approve sending the listed JPEG evidence montages to the selected external API.
5. Do not treat a configured API key or my approval of the local comparison as consent.
6. Only after I approve, call analyze_pdf_comparison_with_ai(run_dir, provider="...", confirm_external_upload=true).
7. Return report_html_path, report_markdown_path, and report_zip_path. Mention that each sheet has lossless whole-sheet OLD/NEW PNGs and detail crops suitable for close review. Treat model descriptions as advisory; preserve engine metrics as facts.

Never send added, removed, one-sided, non-matched, unchanged, or explicitly excluded rows.
```
