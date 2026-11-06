@echo off
cd /d "%~dp0"
if exist "KeyGen.exe" (
    start "" "KeyGen.exe"
) else (
    start "" pythonw "keygen.py"
)
