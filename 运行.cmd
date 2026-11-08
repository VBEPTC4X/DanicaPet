@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" "%~dp0app.py"
) else (
  echo .venv not found. Run:
  echo   python -m venv .venv
  echo   .venv\Scripts\python.exe -m pip install PySide6
  pause
)
