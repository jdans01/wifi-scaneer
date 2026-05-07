@echo off
:: WiFi-Wall-Vision - Launcher para Windows
setlocal

set "SCRIPT_DIR=%~dp0"
set "VENV_PYTHON=%SCRIPT_DIR%.venv\Scripts\python.exe"
set "MAIN=%SCRIPT_DIR%wifi_wall_vision.py"

:: Verificar que Python esté disponible
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo.
    echo ERROR: Python no encontrado en el PATH.
    echo Descargalo de: https://www.python.org/downloads/
    echo Marca "Add Python to PATH" durante la instalacion.
    pause
    exit /b 1
)

:: Si ya existe el venv con la versión correcta, úsalo directamente
if exist "%VENV_PYTHON%" (
    set "_WIFIVISION_VENV_ACTIVE=1"
    "%VENV_PYTHON%" "%MAIN%" %*
) else (
    python "%MAIN%" %*
)

:: El script ya muestra "Presiona Enter para cerrar" en Windows,
:: así que aquí solo capturamos el código de salida para diagnóstico.
set EXIT_CODE=%ERRORLEVEL%
if %EXIT_CODE% neq 0 (
    echo.
    echo [run.bat] El script salio con codigo de error: %EXIT_CODE%
    pause
)
endlocal
