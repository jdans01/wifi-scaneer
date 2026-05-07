#!/usr/bin/env bash
# WiFi-Wall-Vision - Launcher para Linux / macOS
# Ejecuta el script dentro del entorno virtual (.venv).
# Si .venv no existe, el propio script lo crea automáticamente.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"
MAIN="$SCRIPT_DIR/wifi_wall_vision.py"

# Verificar que Python 3 esté disponible
if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 no encontrado. Instálalo con:"
    echo "  Ubuntu/Debian: sudo apt install python3 python3-venv"
    echo "  Fedora:        sudo dnf install python3"
    echo "  macOS:         brew install python"
    exit 1
fi

PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)

if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 9 ]; }; then
    echo "ERROR: Se requiere Python 3.9 o superior (encontrado: $PY_VERSION)"
    exit 1
fi

# Verificar que el módulo venv esté disponible
if ! python3 -c "import venv" &>/dev/null; then
    echo "ERROR: El módulo 'venv' no está disponible."
    echo "  Ubuntu/Debian: sudo apt install python3-venv"
    exit 1
fi

if [ -x "$VENV_PYTHON" ]; then
    # Venv ya existe → lanzar directamente (evita re-ejecución extra)
    echo "[WiFi-Wall-Vision] Usando entorno virtual existente..."
    export _WIFIVISION_VENV_ACTIVE=1
    exec "$VENV_PYTHON" "$MAIN" "$@"
else
    # Primer arranque → el script creará el venv por sí mismo
    echo "[WiFi-Wall-Vision] Primer arranque - se creará el entorno virtual..."
    exec python3 "$MAIN" "$@"
fi
