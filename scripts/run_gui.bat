@echo off
setlocal
set "ROOT=%~dp0"
if not exist "%ROOT%pdfcompare_gui.py" set "ROOT=%~dp0..\"
cd /d "%ROOT%"

if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" "%ROOT%pdfcompare_gui.py"
  exit /b 0
)

if exist ".venv\Scripts\python.exe" (
  start "" ".venv\Scripts\python.exe" "%ROOT%pdfcompare_gui.py"
  exit /b 0
)

set "_WHERE=%SystemRoot%\System32\where.exe"
if exist "%_WHERE%" (
  "%_WHERE%" pyw >nul 2>&1
) else (
  where pyw >nul 2>&1
)
if %errorlevel%==0 (
  start "" pyw -3 "%ROOT%pdfcompare_gui.py"
  exit /b 0
)

if exist "%_WHERE%" (
  "%_WHERE%" pythonw >nul 2>&1
) else (
  where pythonw >nul 2>&1
)
if %errorlevel%==0 (
  start "" pythonw "%ROOT%pdfcompare_gui.py"
  exit /b 0
)

echo Python GUI launcher was not found.
echo Run scripts\setup.ps1 first, or install Python 3.
pause
