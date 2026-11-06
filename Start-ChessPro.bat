@echo off
cd /d "%~dp0"
if exist "ChessPro.exe" (
    start "" "ChessPro.exe"
) else (
    start "" pythonw "main.py"
)
