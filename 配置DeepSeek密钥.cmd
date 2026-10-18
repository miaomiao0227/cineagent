@echo off
where pythonw.exe >nul 2>nul
if errorlevel 1 (
  python "%~dp0scripts\configure_deepseek.py"
) else (
  start "" pythonw.exe "%~dp0scripts\configure_deepseek.py"
)
