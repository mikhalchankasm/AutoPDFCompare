@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>&1
if %errorlevel%==0 (
  py -3 pdfcompare_gui.py
) else (
  python pdfcompare_gui.py
)

if %errorlevel% neq 0 pause
