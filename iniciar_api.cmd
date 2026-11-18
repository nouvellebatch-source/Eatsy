@echo off
rem Arranca la API de Eatsy. El emulador Android la ve en http://10.0.2.2:8000
rem y el panel web en http://127.0.0.1:8000
cd /d "%~dp0"

rem Si el .env no tiene secreto JWT, se genera uno aleatorio la primera vez.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0generar_secreto.ps1"

if not exist ".env" (
    echo Falta el archivo .env. Copia .env.example como .env y llena DB_HOST, DB_USER, DB_PASSWORD y DB_NAME.
    pause
    exit /b 1
)

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000
) else (
    python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
)
pause
