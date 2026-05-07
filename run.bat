@echo off
:: WiFi-Wall-Vision - Launcher para Windows
:: Ejecuta el script dentro del entorno virtual (.venv).
:: Si .venv no existe, el propio script lo crea automáticamente.

setlocal

:: Directorio del script
set "SCRIPT_DIR=%~dp0"
set "VENV_PYTHON=%SCRIPT_DIR%.venv\Scripts\python.exe"
set "MAIN=%SCRIPT_DIR%wifi_wall_vision.py"

:: Si ya existe el venv, úsalo directamente (evita una re-ejecución extra)
if exist "%VENV_PYTHON%" (
    echo [WiFi-Wall-Vision] Usando entorno virtual existente...
    set "_WIFIVISION_VENV_ACTIVE=1"
    "%VENV_PYTHON%" "%MAIN%" %*
) else (
    echo [WiFi-Wall-Vision] Primer arranque - se creara el entorno virtual...
    python "%MAIN%" %*
)

if %ERRORLEVEL% neq 0 (
    echo.
    echo ERROR: El script termino con codigo %ERRORLEVEL%.
    echo Asegurate de tener Python 3.9+ instalado y en el PATH.
    pause
)
endlocal
