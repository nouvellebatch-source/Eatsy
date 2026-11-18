@echo off
rem Crea los datos de prueba en la base: restaurante, sucursal, menu, admin y cliente.
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m app.seed_demo
) else (
    python -m app.seed_demo
)
pause
