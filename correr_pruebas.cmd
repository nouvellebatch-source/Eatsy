@echo off
rem Corre las pruebas del backend (no necesitan base de datos).
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m unittest discover -s tests -v
) else (
    python -m unittest discover -s tests -v
)
pause
