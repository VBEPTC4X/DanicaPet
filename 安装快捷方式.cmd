@echo off
rem Create a desktop shortcut for DanicaPet.
setlocal
cd /d "%~dp0"

if exist "%~dp0DanicaPet.exe" (
  start "" "%~dp0DanicaPet.exe" --install-shortcut
  exit /b 0
)

if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" "%~dp0app.py" --install-shortcut
  exit /b 0
)

where pythonw >nul 2>nul
if not errorlevel 1 (
  start "" pythonw "%~dp0app.py" --install-shortcut
  exit /b 0
)

echo Neither DanicaPet.exe nor a Python environment was found here.
echo For the source version: python -m venv .venv
echo                       .venv\Scripts\python.exe -m pip install PySide6
pause
exit /b 1
