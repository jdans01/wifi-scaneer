#!/usr/bin/env python3
"""
WiFi-Wall-Vision v18 - Compatible Windows y Linux, venv + Python automático
- En Windows con Python 3.13+: descarga e instala Python 3.12 automáticamente.
- Se autovirtualiza en .venv (recrea si la versión de Python cambia).
- Detecta el SO y adapta todos los comandos automáticamente.
- Instala y configura pyrtlsdr + DLLs en Windows.
- Escaneo de potencia WiFi (RTL-SDR) con gráfica.
- Captura CSI con HackRF (PicoScenes).
- Modelo WiFiCam integrado (descarga automática).
"""

from __future__ import annotations

import sys
import os
import subprocess
import urllib.request
import shutil

# ─────────────────────────────────────────────────────────────
# Constantes de versión objetivo
# ─────────────────────────────────────────────────────────────

# pyrtlsdr requiere Python <= 3.12 (sin wheel para 3.13+)
_NEED_PY_MAX  = (3, 12)
_TARGET_PY    = "3.12.10"   # versión a instalar si hace falta
_TARGET_PY_URL = (
    f"https://www.python.org/ftp/python/{_TARGET_PY}/"
    f"python-{_TARGET_PY}-amd64.exe"
)

# ─────────────────────────────────────────────────────────────
# Gestión automática de versión Python (solo Windows, solo si hace falta)
# ─────────────────────────────────────────────────────────────

def _reexec(python_exe: str, extra_env: dict | None = None) -> None:
    """Reemplaza el proceso actual con python_exe ejecutando este mismo script."""
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    try:
        os.execve(python_exe, [python_exe] + sys.argv, env)
    except (AttributeError, OSError):
        result = subprocess.run([python_exe] + sys.argv, env=env)
        sys.exit(result.returncode)


def _venv_python_version(venv_dir: str) -> tuple[int, int] | None:
    """Lee la versión de Python del pyvenv.cfg del venv."""
    cfg = os.path.join(venv_dir, "pyvenv.cfg")
    try:
        with open(cfg, encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("version"):
                    ver = line.split("=", 1)[1].strip()   # "3.14.3"
                    parts = ver.split(".")
                    return (int(parts[0]), int(parts[1]))
    except Exception:
        pass
    return None


def _find_compatible_python() -> str | None:
    """
    Busca Python 3.11 o 3.12 ya instalado en Windows.
    Prueba el Python Launcher (py.exe) y rutas comunes de instalación.
    """
    for minor in (12, 11):
        # Python Launcher para Windows (viene con Python >= 3.3)
        try:
            r = subprocess.run(
                ["py", f"-3.{minor}", "-c", "import sys; print(sys.executable)"],
                capture_output=True, text=True, timeout=10,
            )
            if r.returncode == 0:
                exe = r.stdout.strip()
                if os.path.isfile(exe):
                    return exe
        except Exception:
            pass

        # Rutas típicas de instalación manual y Microsoft Store
        local_app = os.environ.get("LOCALAPPDATA", "")
        program_files = os.environ.get("PROGRAMFILES", "C:\\Program Files")
        candidates = [
            os.path.join(local_app, "Programs", "Python", f"Python3{minor}", "python.exe"),
            os.path.join(local_app, "Programs", "Python", f"Python{3}{minor}", "python.exe"),
            rf"C:\Python3{minor}\python.exe",
            os.path.join(program_files, f"Python 3.{minor}", "python.exe"),
            os.path.join(program_files, f"Python3{minor}", "python.exe"),
        ]
        for path in candidates:
            if os.path.isfile(path):
                return path

    return None


def _install_python_312() -> str | None:
    """
    Descarga e instala Python 3.12 silenciosamente para el usuario actual.
    No requiere permisos de administrador (InstallAllUsers=0).
    Devuelve la ruta al python.exe instalado, o None si falló.
    """
    import tempfile

    local_app  = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
    target_dir = os.path.join(local_app, "Programs", "Python", "Python312")
    exe_path   = os.path.join(target_dir, "python.exe")

    if os.path.isfile(exe_path):
        return exe_path   # ya instalado por una ejecución anterior

    print(f"\n🌐 Descargando Python {_TARGET_PY} (~25 MB)...")
    print(f"   Fuente: {_TARGET_PY_URL}")

    tmp_fd, tmp_installer = tempfile.mkstemp(suffix=".exe", prefix="py_installer_")
    os.close(tmp_fd)

    try:
        def _progress(count, block, total):
            if total > 0:
                pct = min(100, count * block * 100 // total)
                print(f"\r   {pct}% descargado...", end="", flush=True)

        urllib.request.urlretrieve(_TARGET_PY_URL, tmp_installer, _progress)
        print()   # nueva línea tras la barra de progreso
    except Exception as e:
        print(f"\n   ❌ Error al descargar: {e}")
        try:
            os.remove(tmp_installer)
        except OSError:
            pass
        return None

    print(f"🔧 Instalando Python {_TARGET_PY} en: {target_dir}")
    print("   (instalación silenciosa de usuario, sin privilegios de administrador)")
    try:
        result = subprocess.run(
            [
                tmp_installer,
                "/quiet",
                "InstallAllUsers=0",
                "PrependPath=0",        # no modificar PATH del sistema
                "Include_launcher=0",   # no instalar py.exe de nuevo
                f"TargetDir={target_dir}",
            ],
            timeout=300,
        )
    except Exception as e:
        print(f"   ❌ Error durante la instalación: {e}")
        return None
    finally:
        try:
            os.remove(tmp_installer)
        except OSError:
            pass

    if result.returncode != 0:
        print(f"   ❌ El instalador salió con código {result.returncode}.")
        print("   Instala Python 3.12 manualmente: https://www.python.org/downloads/")
        return None

    if os.path.isfile(exe_path):
        print(f"   ✅ Python {_TARGET_PY} instalado.")
        return exe_path

    print("   ❌ No se encontró python.exe tras la instalación.")
    return None


def _ensure_compatible_python_windows() -> None:
    """
    En Windows con Python >= 3.13:
      1. Busca Python 3.11/3.12 ya instalado.
      2. Si no existe, descarga e instala Python 3.12.
      3. Re-ejecuta este script con la versión compatible.
    """
    if sys.platform != "win32":
        return
    # Comparar solo major.minor (sys.version_info es una tupla larga, ej. (3,12,10,'final',0))
    if (sys.version_info.major, sys.version_info.minor) <= _NEED_PY_MAX:
        return
    if os.environ.get("_WIFIVISION_PYTHON_OK") == "1":
        # Ya pasamos por aquí; seguimos aunque la versión no sea ideal
        return

    print(f"\n⚠️  Python {sys.version_info.major}.{sys.version_info.minor} detectado.")
    print(f"   pyrtlsdr (RTL-SDR) solo tiene wheels para Python ≤ 3.12.")
    print("   Buscando Python 3.12 en el sistema...")

    py_exec = _find_compatible_python()

    if py_exec:
        print(f"   ✅ Encontrado: {py_exec}")
    else:
        print("   No encontrado.")
        resp = input(f"   ¿Instalar Python {_TARGET_PY} automáticamente? [S/n]: ").strip().lower()
        if resp not in ("", "s", "si", "y", "yes"):
            print("   Omitido — pyrtlsdr no estará disponible.")
            os.environ["_WIFIVISION_PYTHON_OK"] = "1"
            return
        py_exec = _install_python_312()

    if py_exec is None:
        print("   ❌ No se pudo obtener Python 3.12. Continuando con la versión actual.")
        os.environ["_WIFIVISION_PYTHON_OK"] = "1"
        return

    # Borrar el venv creado con Python 3.14 para que se recree con 3.12
    script_dir = os.path.dirname(os.path.abspath(__file__))
    venv_dir   = os.path.join(script_dir, ".venv")
    if os.path.isdir(venv_dir):
        venv_ver = _venv_python_version(venv_dir)
        cur_ver  = (sys.version_info.major, sys.version_info.minor)
        if venv_ver and venv_ver != cur_ver:
            print(f"   ♻️  Eliminando venv de Python {venv_ver[0]}.{venv_ver[1]} para recrearlo con 3.12...")
            shutil.rmtree(venv_dir, ignore_errors=True)

    print(f"🚀 Relanzando con Python {_TARGET_PY[:4]}...")
    _reexec(py_exec, {"_WIFIVISION_PYTHON_OK": "1", "_WIFIVISION_VENV_ACTIVE": ""})


_ensure_compatible_python_windows()

# ─────────────────────────────────────────────────────────────
# Bootstrap de entorno virtual
# ─────────────────────────────────────────────────────────────

def _bootstrap_venv() -> None:
    """
    Crea y activa .venv/ junto al script si no estamos ya dentro de un venv.
    Si el venv existente fue creado con una versión distinta de Python, lo recrea.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    venv_dir   = os.path.join(script_dir, ".venv")
    _win       = sys.platform == "win32"

    python_in_venv = os.path.join(
        venv_dir,
        "Scripts" if _win else "bin",
        "python.exe" if _win else "python",
    )

    # Ya dentro del venv correcto → nada que hacer
    if sys.prefix != sys.base_prefix:
        venv_ver = _venv_python_version(venv_dir)
        cur_ver  = (sys.version_info.major, sys.version_info.minor)
        if venv_ver and venv_ver == cur_ver:
            return
        # Versión distinta → recrear (puede pasar si el usuario cambió Python)
        print(f"♻️  Venv de Python {venv_ver} detectado; recreando con Python {cur_ver}...")
        shutil.rmtree(venv_dir, ignore_errors=True)

    if os.environ.get("_WIFIVISION_VENV_ACTIVE") == "1":
        return

    if not os.path.isfile(python_in_venv):
        print("🔧 Creando entorno virtual en .venv/ ...")
        import venv as _venv_mod
        _venv_mod.create(venv_dir, with_pip=True, clear=True)
        print("✅ Entorno virtual creado.")

    print("🚀 Relanzando dentro del entorno virtual...")
    _reexec(python_in_venv, {"_WIFIVISION_VENV_ACTIVE": "1"})


_bootstrap_venv()

# ─────────────────────────────────────────────────────────────
# A partir de aquí: dentro del venv con la versión correcta de Python
# ─────────────────────────────────────────────────────────────

import time
import glob
import zipfile
import platform
import importlib

# ─────────────────────────────────────────────────────────────
# Constantes de plataforma
# ─────────────────────────────────────────────────────────────

IS_WINDOWS = platform.system() == "Windows"
IS_LINUX   = platform.system() == "Linux"
IS_MACOS   = platform.system() == "Darwin"

# ¿Hay entorno gráfico disponible?
def _has_display() -> bool:
    if IS_WINDOWS or IS_MACOS:
        return True
    # Linux: verificar variable DISPLAY o WAYLAND_DISPLAY
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))

HAS_DISPLAY = _has_display()

# ─────────────────────────────────────────────────────────────
# Instalación dinámica de paquetes
# ─────────────────────────────────────────────────────────────

def _pip_install(pip_name: str, show_output: bool = False) -> bool:
    """Instala un paquete con pip. show_output=True muestra stderr si falla."""
    try:
        kwargs: dict = {}
        if not show_output:
            kwargs["stdout"] = subprocess.DEVNULL
            kwargs["stderr"] = subprocess.PIPE
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", pip_name],
            **kwargs,
        )
        if result.returncode != 0:
            if not show_output and result.stderr:
                # Mostrar solo la última línea de error (suele ser la relevante)
                last = result.stderr.decode(errors="replace").strip().splitlines()
                if last:
                    print(f"   pip: {last[-1]}")
            return False
        return True
    except Exception as e:
        print(f"   ❌ Error al instalar {pip_name}: {e}")
        return False


def _invalidate_import_cache(module_name: str) -> None:
    """
    Limpia el caché de importación para que Python redescubra un módulo
    recién instalado con pip sin necesidad de reiniciar el intérprete.
    """
    # Eliminar entradas negativas (módulos que no se encontraron antes)
    sys.modules.pop(module_name, None)
    # Refrescar los finders (PathFinder reconstruye sys.path_importer_cache)
    importlib.invalidate_caches()


def _import(module_path: str):
    try:
        return importlib.import_module(module_path)
    except ImportError:
        return None
    except Exception as e:
        print(f"⚠️  No se pudo importar {module_path}: {e}")
        return None


def ensure_package(pip_name: str, module_path: str | None = None):
    """Importa un módulo, preguntando al usuario para instalarlo si no existe."""
    if module_path is None:
        module_path = pip_name

    mod = _import(module_path)
    if mod is not None:
        return mod

    print(f"\n⚠️  El módulo '{pip_name}' no está instalado.")
    resp = input(f"   ¿Instalarlo ahora? [S/n]: ").strip().lower()
    if resp not in ("", "s", "si", "y", "yes"):
        print("   Omitido.")
        return None

    print(f"   Instalando {pip_name}...")
    if _pip_install(pip_name, show_output=True):
        _invalidate_import_cache(module_path.split(".")[0])
        mod = _import(module_path)
        if mod is not None:
            print(f"   ✅ {pip_name} instalado.")
            return mod
        print(f"   ❌ No se pudo importar {pip_name} tras instalarlo.")
    return None


# ─────────────────────────────────────────────────────────────
# RTL-SDR: DLLs en Windows / udev en Linux
# ─────────────────────────────────────────────────────────────

def _register_dll_dir(directory: str) -> None:
    """Registra un directorio de DLLs en Windows (os.add_dll_directory + PATH)."""
    abs_dir = os.path.abspath(directory)
    try:
        os.add_dll_directory(abs_dir)
    except Exception:
        pass
    os.environ["PATH"] = abs_dir + os.pathsep + os.environ.get("PATH", "")


def _python_scripts_dir() -> str:
    """Devuelve el directorio Scripts/ (Windows) del Python activo."""
    return os.path.join(os.path.dirname(sys.executable))


def _copy_dlls_to_scripts(dll_dir: str) -> None:
    """
    Copia las DLLs al directorio de python.exe del venv.
    Es la ubicación más fiable en Windows: siempre está en PATH
    y Python carga extensiones .pyd desde ahí sin necesitar add_dll_directory.
    """
    scripts = _python_scripts_dir()
    try:
        for fname in os.listdir(dll_dir):
            if fname.lower().endswith(".dll"):
                src = os.path.join(dll_dir, fname)
                dst = os.path.join(scripts, fname)
                if not os.path.exists(dst):
                    shutil.copy2(src, dst)
    except Exception:
        pass


def _check_python_version_rtlsdr() -> None:
    """
    pyrtlsdr publica wheels hasta Python 3.12.
    En Python 3.13+ no hay wheel precompilado; pip intentará compilar desde
    código C, lo que requiere Visual Studio Build Tools y puede fallar.
    Avisamos al usuario con la solución concreta.
    """
    major, minor = sys.version_info.major, sys.version_info.minor
    if major == 3 and minor >= 13:
        print(f"\n⚠️  Python {major}.{minor} detectado.")
        print("   pyrtlsdr no tiene wheel para Python 3.13+.")
        print("   Para evitar errores de compilación, instala Python 3.11 o 3.12:")
        print("   https://www.python.org/downloads/")
        print("   Luego vuelve a ejecutar este script con esa versión.")
        print("   (Continuando de todas formas — puede que funcione si tienes")
        print("    Visual Studio Build Tools instalado)")


def _find_dll_in_known_dirs() -> str | None:
    """
    Busca rtlsdr.dll en:
    - site-packages del venv activo
    - directorio del script
    - directorio Scripts/ del venv
    """
    search_dirs: list[str] = []

    # site-packages
    try:
        import site
        try:
            search_dirs += site.getsitepackages()
        except Exception:
            pass
        try:
            search_dirs.append(site.getusersitepackages())
        except Exception:
            pass
    except Exception:
        pass

    # Directorio del script y Scripts/ del venv
    search_dirs.append(os.path.dirname(os.path.abspath(__file__)))
    search_dirs.append(_python_scripts_dir())

    # También ./rtlsdr_dlls/ si existe
    local_dlls = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rtlsdr_dlls")
    if os.path.isdir(local_dlls):
        search_dirs.append(local_dlls)

    for root in search_dirs:
        if not os.path.isdir(root):
            continue
        for dirpath, _, filenames in os.walk(root):
            lower = [f.lower() for f in filenames]
            if "rtlsdr.dll" in lower:
                return dirpath

    return None


def _download_rtlsdr_dlls() -> str | None:
    """
    Descarga las DLLs de RTL-SDR desde GitHub Releases.
    Usa tempfile para el zip (sin problemas de permisos en CWD).
    Extrae en <script_dir>/rtlsdr_dlls/ y también copia a Scripts/.
    """
    import tempfile

    mirrors = [
        "https://github.com/rtlsdrblog/rtl-sdr-blog/releases/latest/download/Release.zip",
        "https://github.com/osmocom/rtl-sdr/releases/latest/download/rtl-sdr-win64.zip",
    ]

    dll_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rtlsdr_dlls")
    os.makedirs(dll_dir, exist_ok=True)

    print("🌐 Descargando DLLs de RTL-SDR...")
    for url in mirrors:
        host = url.split("/")[2]
        repo = "/".join(url.split("/")[3:5])
        print(f"   → {host}/{repo} ...")
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".zip", prefix="rtlsdr_")
        os.close(tmp_fd)
        try:
            urllib.request.urlretrieve(url, tmp_path)
            with zipfile.ZipFile(tmp_path, "r") as z:
                dll_entries = [n for n in z.namelist() if n.lower().endswith(".dll")]
                if not dll_entries:
                    print("   ✗ El zip no contiene DLLs.")
                    continue
                for entry in dll_entries:
                    data = z.read(entry)
                    dest = os.path.join(dll_dir, os.path.basename(entry))
                    with open(dest, "wb") as f:
                        f.write(data)
            print(f"   ✅ DLLs descargadas en: {dll_dir}")
            # Copiar también al Scripts/ del venv (máxima compatibilidad)
            _copy_dlls_to_scripts(dll_dir)
            return dll_dir
        except Exception as e:
            print(f"   ✗ Falló: {e}")
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    return None


def _ensure_rtlsdr_dlls_windows() -> bool:
    """
    Garantiza que rtlsdr.dll es cargable en Windows.
    Estrategia:
      1. ctypes ya puede cargarla (en PATH).
      2. Buscar en site-packages / Scripts / rtlsdr_dlls → registrar.
      3. Descargar de GitHub Releases → copiar a Scripts/.
      4. Instrucciones manuales.
    """
    import ctypes

    # ── 1. Ya cargable ────────────────────────────────────────────────────
    try:
        ctypes.CDLL("rtlsdr")
        return True
    except OSError:
        pass

    # ── 2. Buscar en ubicaciones conocidas ────────────────────────────────
    found_dir = _find_dll_in_known_dirs()
    if found_dir:
        _register_dll_dir(found_dir)
        _copy_dlls_to_scripts(found_dir)
        try:
            ctypes.CDLL("rtlsdr")
            return True
        except OSError:
            pass  # continuar a descarga

    # ── 3. Descargar ──────────────────────────────────────────────────────
    dll_dir = _download_rtlsdr_dlls()
    if dll_dir:
        _register_dll_dir(dll_dir)
        try:
            ctypes.CDLL("rtlsdr")
            return True
        except OSError:
            pass  # DLL descargada pero aún no cargable (raro)

    # ── 4. Instrucciones manuales ─────────────────────────────────────────
    scripts = _python_scripts_dir()
    print("\n❌ No se pudo preparar rtlsdr.dll automáticamente.")
    print(f"   Copia manualmente rtlsdr.dll y libusb-1.0.dll a:")
    print(f"   {scripts}")
    print()
    print("   Descarga las DLLs de:")
    print("   https://github.com/rtlsdrblog/rtl-sdr-blog/releases/latest")
    print("   (archivo Release.zip → carpeta x64/)")
    print()
    print("   También necesitas el driver USB:")
    print("   https://zadig.akeo.ie  →  RTL-SDR → WinUSB")
    return False


def _check_rtlsdr_linux() -> None:
    """
    En Linux, verifica que el módulo del kernel conflictivo esté bloqueado
    y que las reglas udev estén instaladas, imprimiendo guía si no.
    """
    # Verificar si dvb_usb_rtl28xxu está cargado (bloquea el acceso como SDR)
    try:
        lsmod = subprocess.run(
            ["lsmod"], capture_output=True, text=True, timeout=5
        )
        if "dvb_usb_rtl28xxu" in lsmod.stdout:
            print("⚠️  El módulo 'dvb_usb_rtl28xxu' está cargado y puede bloquear el RTL-SDR.")
            print("   Para bloquearlo permanentemente:")
            print("   echo 'blacklist dvb_usb_rtl28xxu' | sudo tee /etc/modprobe.d/rtlsdr.conf")
            print("   sudo modprobe -r dvb_usb_rtl28xxu")
    except Exception:
        pass

    # Verificar reglas udev
    udev_paths = [
        "/etc/udev/rules.d/rtl-sdr.rules",
        "/lib/udev/rules.d/rtl-sdr.rules",
        "/usr/lib/udev/rules.d/rtl-sdr.rules",
    ]
    if not any(os.path.exists(p) for p in udev_paths):
        print("⚠️  Reglas udev de RTL-SDR no encontradas.")
        print("   Instálalas con:  sudo apt install rtl-sdr")
        print("   o manualmente:   https://github.com/osmocom/rtl-sdr")


def _subprocess_can_import(module: str) -> bool:
    """
    Verifica si un módulo es importable lanzando un proceso Python limpio.
    Esto evita el problema del caché de importación del proceso actual
    y confirma si el paquete está realmente disponible en disco.
    """
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        capture_output=True,
        timeout=15,
    )
    return result.returncode == 0


def _load_rtlsdr():
    """Carga pyrtlsdr en Windows/Linux con gestión completa de DLLs."""
    if IS_LINUX:
        _check_rtlsdr_linux()

    # ── Paso 1: preparar DLLs en Windows antes del primer intento ────────
    if IS_WINDOWS:
        _ensure_rtlsdr_dlls_windows()

    # ── Paso 2: intentar importar en el proceso actual ────────────────────
    _invalidate_import_cache("rtlsdr")
    try:
        mod = importlib.import_module("rtlsdr")
        return mod
    except ImportError:
        pass  # no instalado → continuar
    except OSError as e:
        # Instalado pero DLL no encontrada
        print(f"\n⚠️  pyrtlsdr instalado pero falta una DLL: {e}")
        if IS_WINDOWS:
            _ensure_rtlsdr_dlls_windows()
            _invalidate_import_cache("rtlsdr")
            try:
                mod = importlib.import_module("rtlsdr")
                print("   ✅ pyrtlsdr cargado.")
                return mod
            except Exception as e2:
                print(f"   ❌ Sigue fallando: {e2}")
        return None
    except Exception as e:
        print(f"⚠️  Error inesperado al importar rtlsdr: {e}")
        return None

    # ── Paso 3: instalar ──────────────────────────────────────────────────
    if IS_WINDOWS:
        _check_python_version_rtlsdr()

    print("\n⚠️  El módulo 'pyrtlsdr' no está instalado.")
    resp = input("   ¿Instalarlo ahora? [S/n]: ").strip().lower()
    if resp not in ("", "s", "si", "y", "yes"):
        return None

    print("   Instalando pyrtlsdr...")
    ok = _pip_install("pyrtlsdr", show_output=True)
    if not ok:
        print("   ❌ pip no pudo instalar pyrtlsdr.")
        if IS_WINDOWS and sys.version_info >= (3, 13):
            print("   Causa probable: no hay wheel para Python 3.13+.")
            print("   Solución: usa Python 3.11 o 3.12.")
            print("   Descarga: https://www.python.org/downloads/")
        return None

    # ── Paso 4: verificar con proceso limpio (sin caché de este proceso) ──
    if not _subprocess_can_import("rtlsdr"):
        # pip dijo OK pero el módulo no es importable → C extension sin compilar
        print("   ⚠️  pyrtlsdr instalado pero no es importable.")
        if IS_WINDOWS and sys.version_info >= (3, 13):
            print("   No hay wheel precompilado para Python 3.13+.")
            print("   ► Instala Python 3.11 o 3.12 y vuelve a ejecutar el script.")
            print("     https://www.python.org/downloads/")
        else:
            print("   Revisa el error con:  pip install pyrtlsdr  (sin --quiet)")
        return None

    # ── Paso 5: registrar DLLs y cargar en el proceso actual ─────────────
    if IS_WINDOWS:
        _ensure_rtlsdr_dlls_windows()

    _invalidate_import_cache("rtlsdr")
    try:
        mod = importlib.import_module("rtlsdr")
        print("   ✅ pyrtlsdr instalado y cargado.")
        return mod
    except OSError as e:
        print(f"   ❌ DLL no encontrada al importar: {e}")
        print(f"   Copia rtlsdr.dll a: {_python_scripts_dir()}")
        return None
    except Exception as e:
        print(f"   ❌ Error al importar: {e}")
        return None


# ─────────────────────────────────────────────────────────────
# Módulos opcionales con carga diferida
# ─────────────────────────────────────────────────────────────

_np      = None
_cv2     = None
_tqdm_fn = None  # tqdm.tqdm, no el módulo
_plt     = None  # matplotlib.pyplot
_rtlsdr  = None


def _get_numpy():
    global _np
    if _np is None:
        _np = ensure_package("numpy")
    return _np

def _get_cv2():
    global _cv2
    if _cv2 is None:
        _cv2 = ensure_package("opencv-python", "cv2")
    return _cv2

def _get_tqdm():
    global _tqdm_fn
    if _tqdm_fn is None:
        mod = ensure_package("tqdm")
        if mod is not None:
            _tqdm_fn = mod.tqdm
    return _tqdm_fn

def _get_plt():
    global _plt
    if _plt is None:
        _plt = ensure_package("matplotlib", "matplotlib.pyplot")
    return _plt

def _get_rtlsdr():
    global _rtlsdr
    if _rtlsdr is None:
        _rtlsdr = _load_rtlsdr()
    return _rtlsdr


# ─────────────────────────────────────────────────────────────
# Utilidades de sistema multiplataforma
# ─────────────────────────────────────────────────────────────

def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Ejecuta un comando, devolviendo siempre un CompletedProcess (nunca lanza)."""
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=10, **kwargs)
    except FileNotFoundError:
        r = subprocess.CompletedProcess(cmd, returncode=127)
        r.stdout = ""
        r.stderr = f"Comando no encontrado: {cmd[0]}"
        return r
    except Exception as e:
        r = subprocess.CompletedProcess(cmd, returncode=1)
        r.stdout = ""
        r.stderr = str(e)
        return r


def _open_file(path: str) -> None:
    """Abre un archivo con el visor predeterminado del SO."""
    try:
        if IS_WINDOWS:
            os.startfile(path)
        elif IS_MACOS:
            subprocess.Popen(["open", path])
        else:
            # Linux: intentar varios launchers
            for launcher in ("xdg-open", "eog", "feh", "display"):
                if shutil.which(launcher):
                    subprocess.Popen([launcher, path])
                    return
            print(f"   (Abre manualmente el archivo: {path})")
    except Exception as e:
        print(f"   No se pudo abrir el visor: {e}")


def _detect_wifi_interface_linux() -> str:
    """Detecta la interfaz WiFi activa en Linux (no asume wlan0)."""
    # Método 1: iw dev
    r = _run(["iw", "dev"])
    if r.returncode == 0:
        for line in r.stdout.splitlines():
            line = line.strip()
            if line.startswith("Interface "):
                return line.split()[-1]

    # Método 2: ip link show type wireless (kernels modernos)
    r = _run(["ip", "-o", "link", "show", "type", "ether"])
    # no filtra por wireless, pero lo intentamos con /sys/class/net
    try:
        for iface_dir in glob.glob("/sys/class/net/*/wireless"):
            iface = iface_dir.split("/")[4]
            return iface
    except Exception:
        pass

    # Fallback
    return "wlan0"


def _require_sudo_linux(cmd: list[str]) -> list[str]:
    """En Linux añade sudo si el proceso no es root."""
    if IS_LINUX and os.geteuid() != 0:
        return ["sudo"] + cmd
    return cmd


# ─────────────────────────────────────────────────────────────
# Detección de hardware
# ─────────────────────────────────────────────────────────────

def detect_rtlsdr() -> bool:
    rtlsdr = _get_rtlsdr()
    if rtlsdr is None:
        return False
    try:
        sdr = rtlsdr.RtlSdr()
        _ = sdr.get_center_freq()
        sdr.close()
        print("✅ RTL-SDR detectado y funcional.")
        return True
    except Exception as e:
        print(f"❌ No se pudo abrir el RTL-SDR: {e}")
        if IS_WINDOWS:
            print("   Instala el driver WinUSB con Zadig: https://zadig.akeo.ie")
        elif IS_LINUX:
            _check_rtlsdr_linux()
        return False


def detect_hackrf() -> bool:
    r = _run(["hackrf_info"])
    if r.returncode == 0 and "Found HackRF" in r.stdout:
        print("✅ HackRF detectado.")
        return True
    if r.returncode == 127:
        print("ℹ️  hackrf_info no encontrado (HackRF no instalado o no en PATH).")
    return False


# ─────────────────────────────────────────────────────────────
# Escaneo de redes WiFi cercanas
# ─────────────────────────────────────────────────────────────

def scan_nearby_wifi() -> None:
    print("\n📡 Redes WiFi cercanas:\n")

    if IS_WINDOWS:
        r = _run(["netsh", "wlan", "show", "networks", "mode=bssid"])
        print(r.stdout or r.stderr or "Sin resultados.")
        return

    if IS_MACOS:
        airport = (
            "/System/Library/PrivateFrameworks/Apple80211.framework"
            "/Versions/Current/Resources/airport"
        )
        r = _run([airport, "-s"])
        if r.returncode == 0:
            print(r.stdout)
            return
        # macOS 14+: airport se eliminó, usar wdutil
        r = _run(["wdutil", "info"])
        print(r.stdout or r.stderr or "Sin resultados.")
        return

    # Linux: probar varios métodos en orden de preferencia
    iface = _detect_wifi_interface_linux()

    # 1. nmcli (NetworkManager, presente en la mayoría de distros de escritorio)
    if shutil.which("nmcli"):
        r = _run([
            "nmcli", "-f", "SSID,BSSID,SIGNAL,CHAN,SECURITY",
            "dev", "wifi", "list", "--rescan", "yes",
        ])
        if r.returncode == 0 and r.stdout.strip():
            print(r.stdout)
            return

    # 2. iwlist (wireless-tools)
    if shutil.which("iwlist"):
        r = _run(_require_sudo_linux(["iwlist", iface, "scan"]))
        if r.returncode == 0:
            # Filtrar líneas relevantes para no saturar la pantalla
            for line in r.stdout.splitlines():
                stripped = line.strip()
                if any(k in stripped for k in ("ESSID", "Address", "Signal", "Channel", "Encryption")):
                    print(f"  {stripped}")
            return

    # 3. iw scan
    if shutil.which("iw"):
        r = _run(_require_sudo_linux(["iw", iface, "scan"]))
        if r.returncode == 0:
            for line in r.stdout.splitlines():
                stripped = line.strip()
                if any(k in stripped for k in ("SSID", "signal", "freq", "BSS ")):
                    print(f"  {stripped}")
            return

    print("❌ No se encontró ninguna herramienta de escaneo WiFi.")
    print("   Instala una de estas: nmcli (NetworkManager), iwlist (wireless-tools), iw")


# ─────────────────────────────────────────────────────────────
# Escaneo de potencia RTL-SDR + gráfica
# ─────────────────────────────────────────────────────────────

_WIFI_CHANNELS  = list(range(1, 14))
_WIFI_FREQS_MHZ = [2412 + (ch - 1) * 5 for ch in _WIFI_CHANNELS]


def plot_power_scan(results: list) -> None:
    plt = _get_plt()
    if plt is None:
        print("⚠️  matplotlib no disponible. No se puede generar la gráfica.")
        return

    channels = [r[0] for r in results]
    powers   = [r[2] for r in results]
    freqs    = [r[1] for r in results]

    fig, ax = plt.subplots(figsize=(12, 6))
    bars = ax.bar(channels, powers, color="teal", alpha=0.7)
    ax.axhline(y=-80, color="red", linestyle="--", linewidth=1, label="Umbral de ruido típico")
    ax.set_xlabel("Canal WiFi")
    ax.set_ylabel("Potencia (dBm)")
    ax.set_title("Espectro WiFi 2.4 GHz")
    ax.set_xticks(channels)
    ax.set_xticklabels([f"{ch}\n({int(f)} MHz)" for ch, f in zip(channels, freqs)])
    ax.legend()
    ax.grid(axis="y", linestyle=":", alpha=0.6)

    for bar, power in zip(bars, powers):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.5,
            f"{power:.1f}",
            ha="center", va="bottom", fontsize=8,
        )

    fig.tight_layout()
    out = "wifi_spectrum.png"
    fig.savefig(out)
    print(f"💾 Gráfica guardada como '{out}'")

    if HAS_DISPLAY:
        plt.show()
    else:
        print("   (Entorno sin pantalla: abre el archivo manualmente.)")
        plt.close(fig)


def wifi_power_scan_rtlsdr() -> list | None:
    np     = _get_numpy()
    tqdm   = _get_tqdm()
    rtlsdr = _get_rtlsdr()

    if rtlsdr is None:
        print("❌ pyrtlsdr no disponible.")
        return None
    if np is None:
        print("❌ numpy no disponible.")
        return None

    try:
        sdr = rtlsdr.RtlSdr()
        sdr.sample_rate = 2.048e6
        sdr.gain = "auto"
    except Exception as e:
        print(f"❌ No se pudo abrir el RTL-SDR: {e}")
        return None

    print("📊 Escaneando canales WiFi 2.4 GHz...")
    results  = []
    iterable = zip(_WIFI_FREQS_MHZ, _WIFI_CHANNELS)
    if tqdm is not None:
        iterable = tqdm(iterable, total=len(_WIFI_CHANNELS), desc="Barriendo canales")

    try:
        for freq_mhz, ch in iterable:
            sdr.center_freq = freq_mhz * 1e6
            time.sleep(0.3)
            samples  = sdr.read_samples(256 * 1024)
            power    = np.mean(np.abs(samples) ** 2)
            power_db = 10 * np.log10(power + 1e-12) - 30
            results.append((ch, freq_mhz, power_db))
    finally:
        sdr.close()

    print("\nCanal | Frecuencia (MHz) | Potencia (dBm)")
    print("-" * 45)
    for ch, f, p in results:
        print(f"  {ch:2}  |     {f:7.1f}      |   {p:6.1f}")

    csv_path = "wifi_power_scan.csv"
    with open(csv_path, "w", encoding="utf-8") as fp:
        fp.write("Canal,Frecuencia_MHz,Potencia_dBm\n")
        for ch, f, p in results:
            fp.write(f"{ch},{f},{p:.2f}\n")
    print(f"💾 Datos guardados en '{csv_path}'")

    if _get_plt() is not None:
        resp = input("\n¿Generar gráfica del espectro? [S/n]: ").strip().lower()
        if resp in ("", "s", "si", "y", "yes"):
            plot_power_scan(results)

    return results


# ─────────────────────────────────────────────────────────────
# Captura CSI con HackRF (PicoScenes)
# ─────────────────────────────────────────────────────────────

def _picoscenes_binary() -> str | None:
    """Devuelve el nombre/ruta del binario PicoScenes según el SO."""
    for name in ("PicoScenes", "picoscenes"):
        if shutil.which(name):
            return name
    # Windows: buscar en rutas típicas de instalación
    if IS_WINDOWS:
        for candidate in [
            r"C:\Program Files\PicoScenes\PicoScenes.exe",
            r"C:\PicoScenes\PicoScenes.exe",
        ]:
            if os.path.exists(candidate):
                return candidate
    return None


def capture_csi_hackrf(duration: int = 10) -> str | None:
    tqdm = _get_tqdm()
    ps   = _picoscenes_binary()

    if ps is None:
        print("❌ PicoScenes no encontrado.")
        if IS_WINDOWS:
            print("   Descárgalo de https://ps.zpj.io e instálalo.")
        else:
            print("   Instálalo desde https://ps.zpj.io o con:")
            print("   sudo apt install picoscenes   (si está en tu repo)")
        return None

    out_dir = os.path.join(os.getcwd(), "csi_captures")
    os.makedirs(out_dir, exist_ok=True)

    cmd = [
        ps, "-d", "debug",
        "-i", "hackrf0",
        "--mode", "logger",
        "--freq", "2447",
        "--rx-gain", "60",
        "--output-dir", out_dir,
    ]
    print(f"📥 Grabando {duration}s de CSI con HackRF...")
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"❌ No se pudo lanzar PicoScenes: {e}")
        return None

    if tqdm is not None:
        for _ in tqdm(range(duration), desc="Capturando CSI", unit="s"):
            time.sleep(1)
    else:
        for i in range(duration):
            time.sleep(1)
            print(f"  {i+1}/{duration}s...", end="\r", flush=True)
        print()

    proc.terminate()
    proc.wait()

    files = glob.glob(os.path.join(out_dir, "*.csi")) or glob.glob("*.csi")
    if files:
        latest = max(files, key=os.path.getctime)
        print(f"✅ Captura guardada: {latest}")
        return latest

    print("❌ No se generó archivo CSI.")
    return None


# ─────────────────────────────────────────────────────────────
# Manejo de archivos CSI
# ─────────────────────────────────────────────────────────────

def filter_csi_files() -> list:
    candidates = []
    for ext in ("*.csi", "*.pcap", "*.npy"):
        candidates.extend(glob.glob(ext))
    for f in glob.glob("*.dat"):
        try:
            if os.path.getsize(f) > 1_000_000:
                candidates.append(f)
        except OSError:
            pass
    return sorted(set(candidates))


def load_csi_file(path: str):
    np = _get_numpy()
    if np is None:
        raise RuntimeError("numpy no disponible")

    if path.endswith(".npy"):
        data = np.load(path)
        if data.ndim == 2:
            data = data[:, :, np.newaxis]
            data = np.concatenate([np.abs(data), np.angle(data)], axis=-1)
        return data

    # Intentar con CSIKit si está disponible
    csikit = _import("CSIKit.reader")
    if csikit is not None:
        try:
            reader = csikit.get_reader(path)
            csi_data = reader.read_file(path)
            frames = []
            for frame in csi_data.frames:
                mat = frame.csi_matrix[0, 0, :]
                frames.append(np.stack([np.abs(mat), np.angle(mat)], axis=1))
            return np.array(frames)
        except Exception:
            pass  # Fallback al método crudo

    # Leer como complejo crudo
    raw = np.fromfile(path, dtype=np.complex64)
    if raw.size == 0:
        raise ValueError(f"Archivo vacío o formato no soportado: {path}")
    n_sub    = 30
    n_frames = raw.size // n_sub
    raw      = raw[: n_frames * n_sub].reshape(n_frames, n_sub)
    return np.stack([np.abs(raw), np.angle(raw)], axis=-1)


def download_demo() -> str | None:
    dest = "demo_csi.npy"
    if os.path.exists(dest):
        print(f"✅ Usando demo existente: {dest}")
        return dest
    print("🌐 Descargando dataset demo...")
    try:
        urllib.request.urlretrieve(
            "https://github.com/StrohmayerJ/wificam/raw/main/data/sample_csi.npy",
            dest,
        )
        print("✅ Descarga completa.")
        return dest
    except Exception as e:
        print(f"❌ Error al descargar el demo: {e}")
        return None


# ─────────────────────────────────────────────────────────────
# Modelo WiFiCam (VAE)
# ─────────────────────────────────────────────────────────────

_MODEL   = None
_DEVICE  = None
_N_SUB   = 30
_N_FRAMES = 200


def _build_wificam(torch, nn):
    class Encoder(nn.Module):
        def __init__(self, input_dim: int = _N_FRAMES * _N_SUB, latent_dim: int = 128):
            super().__init__()
            self.fc1      = nn.Linear(input_dim, 512)
            self.fc_mu    = nn.Linear(512, latent_dim)
            self.fc_logvar = nn.Linear(512, latent_dim)

        def forward(self, x):
            h = torch.relu(self.fc1(x))
            return self.fc_mu(h), self.fc_logvar(h)

    class Decoder(nn.Module):
        def __init__(self, latent_dim: int = 128):
            super().__init__()
            self.fc     = nn.Linear(latent_dim, 256)
            self.deconv = nn.Sequential(
                nn.ConvTranspose2d(256, 128, 4, 2, 1), nn.ReLU(),
                nn.ConvTranspose2d(128,  64, 4, 2, 1), nn.ReLU(),
                nn.ConvTranspose2d( 64,  32, 4, 2, 1), nn.ReLU(),
                nn.ConvTranspose2d( 32,   1, 4, 2, 1), nn.Sigmoid(),
            )

        def forward(self, z):
            h = torch.relu(self.fc(z))
            return self.deconv(h.view(-1, 256, 1, 1))

    class WiFiCam(nn.Module):
        def __init__(self):
            super().__init__()
            self.encoder = Encoder()
            self.decoder = Decoder()

        def _reparam(self, mu, logvar):
            return mu + torch.exp(0.5 * logvar) * torch.randn_like(mu)

        def forward(self, x):
            mu, logvar = self.encoder(x)
            return self.decoder(self._reparam(mu, logvar)), mu, logvar

    return WiFiCam()


def get_model():
    global _MODEL, _DEVICE
    if _MODEL is not None:
        return _MODEL, _DEVICE

    torch = ensure_package("torch")
    if torch is None:
        print("❌ PyTorch no disponible.")
        return None, None

    import torch.nn as nn

    model_path = "wificam_model.pt"
    if not os.path.exists(model_path):
        print("🌐 Descargando modelo WiFiCam (~154 MB)...")
        try:
            urllib.request.urlretrieve(
                "https://github.com/StrohmayerJ/wificam/releases/download/v1.0/model.pt",
                model_path,
            )
            print("✅ Modelo descargado.")
        except Exception as e:
            print(f"❌ Error al descargar el modelo: {e}")
            return None, None

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model  = _build_wificam(torch, nn).to(device)

    try:
        checkpoint = torch.load(model_path, map_location=device)
        state      = checkpoint.get("state_dict", checkpoint)
        model.load_state_dict(state, strict=False)
    except Exception as e:
        print(f"⚠️  Checkpoint parcial: {e}")
        print("   Usando pesos aleatorios (resultado demostrativo).")

    model.eval()
    _MODEL  = model
    _DEVICE = device
    print("✅ Modelo de IA listo.")
    return model, device


def preprocess_csi(csi_array):
    np = _get_numpy()
    n_frames, n_sub = csi_array.shape[:2]

    if n_frames > _N_FRAMES:
        idx = np.linspace(0, n_frames - 1, _N_FRAMES, dtype=int)
        csi_array = csi_array[idx]
    elif n_frames < _N_FRAMES:
        csi_array = np.pad(csi_array, ((0, _N_FRAMES - n_frames), (0, 0), (0, 0)), mode="edge")

    if n_sub > _N_SUB:
        idx = np.linspace(0, n_sub - 1, _N_SUB, dtype=int)
        csi_array = csi_array[:, idx, :]
    elif n_sub < _N_SUB:
        csi_array = np.pad(csi_array, ((0, 0), (0, _N_SUB - n_sub), (0, 0)), mode="edge")

    amp = csi_array[:, :, 0].astype(float)
    a_min, a_max = amp.min(), amp.max()
    if a_max > a_min:
        csi_array = csi_array.copy().astype(float)
        csi_array[:, :, 0] = (amp - a_min) / (a_max - a_min)

    return csi_array


def generate_image(model, csi_array, device):
    import torch
    np = _get_numpy()

    amp = csi_array[:, :, 0].astype(float)
    x   = torch.tensor(amp.flatten(), dtype=torch.float32).unsqueeze(0).to(device)

    with torch.no_grad():
        img_tensor, _, _ = model(x)

    img = img_tensor.squeeze().cpu().numpy()
    return (img * 255).clip(0, 255).astype(np.uint8)


def _save_and_show_image(img, out_path: str) -> None:
    """Guarda la imagen y la muestra con el método disponible."""
    cv2 = _get_cv2()
    plt = _get_plt()

    saved = False

    if cv2 is not None:
        cv2.imwrite(out_path, img)
        saved = True
        if HAS_DISPLAY:
            try:
                cv2.imshow("WiFi-Wall-Vision", img)
                cv2.waitKey(0)
                cv2.destroyAllWindows()
                return
            except Exception:
                pass  # cv2 sin GUI (headless OpenCV)

    if plt is not None:
        plt.imsave(out_path, img, cmap="gray")
        saved = True
        if HAS_DISPLAY:
            fig, ax = plt.subplots()
            ax.imshow(img, cmap="gray")
            ax.set_title("WiFi-Wall-Vision")
            ax.axis("off")
            plt.show()
            return

    if saved:
        print(f"💾 Imagen guardada: {out_path}")
        if not HAS_DISPLAY:
            print("   (Entorno sin pantalla. Abriendo con visor del sistema...)")
            _open_file(out_path)
    else:
        print("❌ Ni OpenCV ni matplotlib están disponibles para guardar la imagen.")


# ─────────────────────────────────────────────────────────────
# Menú principal
# ─────────────────────────────────────────────────────────────

def _pause() -> None:
    input("\nPresiona Enter para continuar...")


def _venv_info() -> str:
    in_venv = sys.prefix != sys.base_prefix
    if not in_venv:
        return "NO (sistema)"
    venv_path = sys.prefix
    # Mostrar ruta relativa si está junto al script
    try:
        rel = os.path.relpath(venv_path, os.path.dirname(os.path.abspath(__file__)))
        return f"sí ({rel})"
    except ValueError:
        return f"sí ({venv_path})"


def _print_sysinfo() -> None:
    print(f"\nSistema : {platform.system()} {platform.release()} | Python {sys.version.split()[0]}")
    print(f"Venv    : {_venv_info()}")
    print(f"Pantalla: {'disponible' if HAS_DISPLAY else 'NO detectada (modo headless)'}")


def main() -> None:
    _print_sysinfo()
    has_rtlsdr = detect_rtlsdr()
    has_hackrf = detect_hackrf()
    csi_data   = None

    while True:
        print("\n" + "=" * 62)
        print("        WiFi-Wall-Vision  –  Menú Principal")
        print(f"        SO: {platform.system()}  |  Pantalla: {'Sí' if HAS_DISPLAY else 'No'}")
        print("=" * 62)
        r_tag = "" if has_rtlsdr else "  [sin dispositivo]"
        h_tag = "" if has_hackrf else "  [sin dispositivo]"
        d_tag = f"  ({csi_data.shape[0]} frames cargados)" if csi_data is not None else "  [sin datos]"
        print(f"[1] Re-escanear dispositivos SDR")
        print(f"[2] Mostrar redes WiFi cercanas")
        print(f"[3] Escaneo de potencia WiFi RTL-SDR{r_tag}")
        print(f"[4] Capturar CSI con HackRF{h_tag}")
        print(f"[5] Cargar archivo CSI del disco")
        print(f"[6] Descargar dataset demo")
        print(f"[7] Generar imagen con IA{d_tag}")
        print(f"[8] Salir")
        op = input("Opción: ").strip()

        if op == "1":
            has_rtlsdr = detect_rtlsdr()
            has_hackrf = detect_hackrf()
            _pause()

        elif op == "2":
            scan_nearby_wifi()
            _pause()

        elif op == "3":
            if not has_rtlsdr:
                print("⚠️  RTL-SDR no disponible. Conecta el dispositivo y usa [1] para re-escanear.")
            else:
                wifi_power_scan_rtlsdr()
            _pause()

        elif op == "4":
            if not has_hackrf:
                print("⚠️  HackRF no disponible.")
            else:
                path = capture_csi_hackrf()
                if path:
                    try:
                        csi_data = load_csi_file(path)
                        print(f"✅ CSI cargado: {csi_data.shape}")
                    except Exception as e:
                        print(f"❌ Error al cargar CSI: {e}")
            _pause()

        elif op == "5":
            files = filter_csi_files()
            if not files:
                print("No se encontraron archivos CSI en la carpeta actual.")
                print("Extensiones buscadas: .csi  .pcap  .npy  .dat (>1 MB)")
                print("Usa [6] para descargar el dataset demo.")
            else:
                print("\nArchivos disponibles:")
                for i, f in enumerate(files):
                    try:
                        size_mb = os.path.getsize(f) / 1e6
                    except OSError:
                        size_mb = 0
                    print(f"  [{i}] {f}  ({size_mb:.1f} MB)")
                print("  [D] Descargar y usar demo")
                sel = input("Selecciona: ").strip().lower()
                if sel == "d":
                    path = download_demo()
                    if path:
                        try:
                            csi_data = load_csi_file(path)
                            print(f"✅ Demo cargado: {csi_data.shape}")
                        except Exception as e:
                            print(f"❌ Error: {e}")
                elif sel.isdigit():
                    idx = int(sel)
                    if 0 <= idx < len(files):
                        try:
                            csi_data = load_csi_file(files[idx])
                            print(f"✅ Cargado: {csi_data.shape}")
                        except Exception as e:
                            print(f"❌ Error: {e}")
                    else:
                        print("Índice fuera de rango.")
                else:
                    print("Entrada inválida.")
            _pause()

        elif op == "6":
            path = download_demo()
            if path:
                try:
                    csi_data = load_csi_file(path)
                    print(f"✅ Dataset demo cargado: {csi_data.shape}")
                except Exception as e:
                    print(f"❌ Error al cargar demo: {e}")
            _pause()

        elif op == "7":
            if csi_data is None:
                print("⚠️  Primero carga datos CSI (opciones 4, 5 o 6).")
            else:
                model, device = get_model()
                if model is None:
                    print("❌ No se pudo cargar el modelo de IA.")
                else:
                    print("🎨 Preprocesando y generando imagen...")
                    try:
                        prep     = preprocess_csi(csi_data)
                        img      = generate_image(model, prep, device)
                        out_path = "vista_traves_pared.png"
                        _save_and_show_image(img, out_path)
                    except Exception as e:
                        print(f"❌ Error al generar imagen: {e}")
            _pause()

        elif op == "8":
            print("👋 Saliendo.")
            break

        else:
            print("❌ Opción no válida. Elige entre 1 y 8.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Interrumpido por el usuario.")
    except Exception as _exc:
        import traceback
        print("\n" + "=" * 60)
        print("❌ ERROR INESPERADO — copia este texto si necesitas ayuda:")
        print("=" * 60)
        traceback.print_exc()
        print("=" * 60)
    finally:
        # En Windows: mantener la ventana abierta para que el usuario lea los mensajes
        if sys.platform == "win32":
            input("\nPresiona Enter para cerrar...")
