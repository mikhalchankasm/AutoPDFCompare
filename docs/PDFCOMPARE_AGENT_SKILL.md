# PDFCompare Agent Skill

Use this instruction block for local agents that support custom skills or reusable rules.

## Goal

Compare two local PDF files through the PDFCompare MCP server. Always prepare first, ask for the result folder name, then start a background job and monitor it by `job_id`.

## Required Flow

1. Call `prepare_pdf_comparison` with:
   - `old_path`: old/base PDF;
   - `new_path`: new/target PDF;
   - `out_dir`: folder for result runs, usually `D:\GitHub\PDFCompare\runs`.
2. Report page counts and similar previous comparisons.
3. Offer the suggested names from `suggested_run_names`.
4. Ask the user for the final folder name.
5. Ask about optional comparison settings if the user did not provide them:
   - whether to ignore title blocks/stamps/author tables;
   - `diff_strictness`: `strict`, `normal`, or `loose`;
   - whether to enable experimental merge of nearby bbox regions. Recommend disabled unless the user explicitly wants grouped boxes. Current default is disabled with `bbox_merge_gap_mm=0`; a typical trial value is `5`; `bbox_merge_max_area_ratio=16` plus page-area/sparse-fill guards limit over-merging.
6. Call `start_pdf_comparison` using the selected `run_name` and selected settings.
7. Tell the user the `job_id`, `run_dir`, and `report_path`.
8. Use `get_pdf_comparison_status(job_id)` for progress and final counts.

## Response Style

Keep responses short and operational:

- page counts;
- similar existing runs, if any;
- selected or suggested run folder;
- current progress;
- final report path.

When discussing change amount, prefer the report's `FG %` and `mm²` metrics over page-level `Diff %` for engineering significance. `Diff %` is still useful as a whole-sheet pixel ratio.

Do not invent comparison results. Use `summary.counts` from the completed job status.

## Fallback

If MCP is unavailable, run the CLI:

```powershell
python D:\GitHub\PDFCompare\compare_pdfs.py --old "<old.pdf>" --new "<new.pdf>" --out-dir "D:\GitHub\PDFCompare\runs" --run-name "<folder>"
```

The CLI fallback is blocking and should only be used when background MCP execution is unavailable.
