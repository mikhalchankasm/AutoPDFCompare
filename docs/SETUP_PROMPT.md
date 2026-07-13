# PDFCompare MCP Setup Prompt

Скопируйте этот prompt в локального агента, которому нужно подключить PDFCompare MCP.

```text
Set up PDFCompare MCP for this Windows machine.

Repository: https://github.com/mikhalchankasm/AutoPDFCompare
Local install folder: %LOCALAPPDATA%\PDFCompareMCP\AutoPDFCompare
MCP server name: pdfcompare

Requirements:
- Git must be available in PATH.
- Python 3.12+ must be available in PATH.
- Use stdio transport only.
- This setup runs local PowerShell and code from the repository's master branch. Continue only if the user trusts this repository.

Install:
1. If %LOCALAPPDATA%\PDFCompareMCP\AutoPDFCompare does not exist, clone:
   git clone https://github.com/mikhalchankasm/AutoPDFCompare.git "%LOCALAPPDATA%\PDFCompareMCP\AutoPDFCompare"
2. Configure the MCP client with this server:
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

The bootstrap command installs missing dependencies with scripts/setup.ps1 -WithMcp and starts scripts/run_mcp.ps1.

Updating:
- The MCP server is a separate git checkout. It is NOT updated by the GUI installer or by the app's auto-update — those only replace PDFCompareLocal.exe.
- By default the bootstrap pulls origin/master on every server start, so restarting the MCP client is enough to update. The pull is skipped (with a note in .pdfcompare_mcp/bootstrap.log) if the checkout is not on master or has local changes.
- To turn auto-update off, pass -NoAutoUpdate to scripts/run_mcp_bootstrap.ps1 or set PDFCOMPARE_MCP_AUTO_UPDATE=0 in the MCP server environment. Then update manually:
   git -C "%LOCALAPPDATA%\PDFCompareMCP\AutoPDFCompare" pull --ff-only origin master
   powershell -NoProfile -ExecutionPolicy Bypass -File "%LOCALAPPDATA%\PDFCompareMCP\AutoPDFCompare\scripts\setup.ps1" -WithMcp
- Call the check_pdfcompare_update tool to see whether the checkout is behind master (it reports the version, the commit, how many commits behind, and anything blocking the pull).

After connecting, use PDFCompare MCP tools:
- check_pdfcompare_update if the user asks about updates or something behaves like an old version;
- prepare_pdf_comparison first;
- ask whether title blocks/stamps/author tables should be ignored; use percent boxes x,y,w,h from the top-left page corner;
- ask whether strictness should be strict, normal, or loose;
- then start_pdf_comparison with the selected run_name, diff_strictness, and exclude_regions;
- poll get_pdf_comparison_status until completion;
- return report_path and summary.counts to the user.
```
