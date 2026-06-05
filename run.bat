@echo off
REM Double-click (or `run.bat report`) to launch the SpikeInterface menu via uv.
REM PYTHONUTF8=1 keeps the full-screen Unicode shield/box-drawing legible on
REM legacy cmd.exe; %~dp0 = this script's folder, so cwd does not matter.
setlocal
set "PYTHONUTF8=1"
cd /d "%~dp0"
uv run python "%~dp0SpikeInterface_Menu.py" %*
endlocal
