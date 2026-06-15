# PDFCompare MCP Setup Prompt

Скопируйте этот prompt в локального агента, которому нужно подключить PDFCompare MCP.

```text
Set up PDFCompare MCP for this Windows machine.

Repository: https://github.com/mikhalchankasm/AutoPDFCompare
Local install folder: %LOCALAPPDATA%\PDFCompareMCP\AutoPDFCompare
MCP server name: pdfcompare

Requirements:
- Git must be available in PATH.
- Python 3.10+ must be available in PATH.
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

The bootstrap command installs missing dependencies with scripts/setup.ps1 -WithMcp and starts scripts/run_mcp.ps1. It does not auto-update code by default.

To update later:
1. Stop the MCP server or close the MCP client.
2. Run:
   git -C "%LOCALAPPDATA%\PDFCompareMCP\AutoPDFCompare" pull --ff-only origin master
3. Run:
   powershell -NoProfile -ExecutionPolicy Bypass -File "%LOCALAPPDATA%\PDFCompareMCP\AutoPDFCompare\scripts\setup.ps1" -WithMcp
4. Start the MCP client again.

For a trusted private setup that should update on each server start, add -AutoUpdate to scripts/run_mcp_bootstrap.ps1 or set PDFCOMPARE_MCP_AUTO_UPDATE=1 in the MCP server environment.

After connecting, use PDFCompare MCP tools:
- prepare_pdf_comparison first;
- then start_pdf_comparison with the selected run_name;
- poll get_pdf_comparison_status until completion;
- return report_path and summary.counts to the user.
```
