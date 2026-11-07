@echo off
rem Create a desktop shortcut for DanicaPet (no Chinese text here: the exe does the naming)
setlocal
set "APP=%~dp0DanicaPet.exe"
if not exist "%APP%" (
  echo DanicaPet.exe not found next to this file.
  pause
  exit /b 1
)
start "" "%APP%" --install-shortcut
exit /b 0
