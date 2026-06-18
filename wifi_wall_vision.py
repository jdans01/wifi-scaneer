#!/usr/bin/env python3
"""
WiFi-Wall-Vision v19 - 100% automático, sin preguntas
- Detecta Python 3.13+ en Windows → instala Python 3.12 automáticamente.
- Crea y activa .venv automáticamente.
- Instala todos los paquetes necesarios sin intervención.
- Configura DLLs de RTL-SDR con selección correcta de arquitectura (x64/x32).
"""

from __future__ import annotations

import sys
import os
import subprocess
import urllib.request
import shutil
import struct

# ─────────────────────────────────────────────────────────────
# Arquitectura del proceso Python actual
# ─────────────────────────────────────────────────────────────
_IS_64BIT = struct.calcsize("P") == 8

# pyrtlsdr solo tiene wheel para Python ≤ 3.12
_NEED_PY_MAX = (3, 12)
_TARGET_PY   = "3.12.10"
_TARGET_PY_URL = (
    f"https://www.python.org/ftp/python/{_TARGET_PY}/"
    f"python-{_TARGET_PY}-{'amd64' if _IS_64BIT else 'win32'}.exe"
)

# ─────────────────────────────────────────────────────────────
# Helper: relanzar proceso
# ─────────────────────────────────────────────────────────────

def _reexec(python_exe: str, extra_env: dict | None = None) -> None:
    """
    Relanza este script con python_exe.
    En Windows usamos subprocess.run porque os.execve no reemplaza el proceso
    actual de forma fiable (el padre continúa ejecutándose en paralelo).
    En Unix usamos os.execve que sí reemplaza el proceso.
    """
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    if sys.platform == "win32":
        result = subprocess.run([python_exe] + sys.argv, env=env)
        sys.exit(result.returncode)
    else:
        os.execve(python_exe, [python_exe] + sys.argv, env)

# ─────────────────────────────────────────────────────────────
# Gestión de versión Python (automática, sin preguntas)
# ─────────────────────────────────────────────────────────────

def _venv_python_version(venv_dir: str) -> tuple[int, int] | None:
    cfg = os.path.join(venv_dir, "pyvenv.cfg")
    try:
        with open(cfg, encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("version"):
                    ver = line.split("=", 1)[1].strip()
                    parts = ver.split(".")
                    return (int(parts[0]), int(parts[1]))
    except Exception:
        pass
    return None


def _find_compatible_python() -> str | None:
    """Busca Python 3.12 o 3.11 ya instalado en el sistema."""
    for minor in (12, 11):
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

        local  = os.environ.get("LOCALAPPDATA", "")
        pf     = os.environ.get("PROGRAMFILES", "C:\\Program Files")
        for path in [
            os.path.join(local, "Programs", "Python", f"Python3{minor}", "python.exe"),
            rf"C:\Python3{minor}\python.exe",
            os.path.join(pf, f"Python3{minor}", "python.exe"),
        ]:
            if os.path.isfile(path):
                return path
    return None


def _install_python_312() -> str | None:
    """Descarga e instala Python 3.12 para el usuario actual (sin admin)."""
    import tempfile

    local     = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
    dest_dir  = os.path.join(local, "Programs", "Python", "Python312")
    exe_path  = os.path.join(dest_dir, "python.exe")

    if os.path.isfile(exe_path):
        return exe_path

    print(f"\n⚙️  Descargando Python {_TARGET_PY} (~25 MB)...")
    tmp_fd, tmp = tempfile.mkstemp(suffix=".exe", prefix="py_")
    os.close(tmp_fd)
    try:
        def _prog(n, blk, total):
            if total > 0:
                print(f"\r   {min(100, n*blk*100//total)}%...", end="", flush=True)
        urllib.request.urlretrieve(_TARGET_PY_URL, tmp, _prog)
        print()
    except Exception as e:
        print(f"\n   ❌ Descarga fallida: {e}")
        os.remove(tmp)
        return None

    print(f"⚙️  Instalando Python {_TARGET_PY} (usuario, sin admin)...")
    try:
        r = subprocess.run(
            [tmp, "/quiet", "InstallAllUsers=0", "PrependPath=0",
             "Include_launcher=0", f"TargetDir={dest_dir}"],
            timeout=300,
        )
    except Exception as e:
        print(f"   ❌ Instalación fallida: {e}")
        return None
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass

    if r.returncode != 0:
        print(f"   ❌ Instalador salió con código {r.returncode}")
        return None

    if os.path.isfile(exe_path):
        print(f"   ✅ Python {_TARGET_PY} instalado.")
        return exe_path
    print("   ❌ No se encontró python.exe tras instalar.")
    return None


def _ensure_compatible_python_windows() -> None:
    """En Windows con Python 3.13+: cambia a Python 3.12 automáticamente."""
    if sys.platform != "win32":
        return
    if (sys.version_info.major, sys.version_info.minor) <= _NEED_PY_MAX:
        return
    if os.environ.get("_WIFIVISION_PYTHON_OK") == "1":
        return

    print(f"\n⚙️  Python {sys.version_info.major}.{sys.version_info.minor} detectado."
          f" RTL-SDR necesita Python 3.12.")

    py_exec = _find_compatible_python()
    if py_exec:
        print(f"   ✅ Python 3.12 encontrado: {py_exec}")
    else:
        print("   Instalando Python 3.12 automáticamente...")
        py_exec = _install_python_312()

    if py_exec is None:
        print("   ❌ No se pudo obtener Python 3.12. RTL-SDR no estará disponible.")
        os.environ["_WIFIVISION_PYTHON_OK"] = "1"
        return

    # Determinar la versión del ejecutable objetivo para comparar con el venv
    try:
        _r = subprocess.run(
            [py_exec, "-c",
             "import sys; print(sys.version_info.major, sys.version_info.minor)"],
            capture_output=True, text=True, timeout=10,
        )
        _parts = _r.stdout.strip().split()
        target_ver = (int(_parts[0]), int(_parts[1]))
    except Exception:
        target_ver = (3, 12)  # fallback

    # Eliminar venv si no fue creado con la versión objetivo
    venv_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv")
    if os.path.isdir(venv_dir):
        vv = _venv_python_version(venv_dir)
        if vv != target_ver:
            ver_str = f"{vv[0]}.{vv[1]}" if vv else "desconocida"
            print(f"   ♻️  Eliminando venv Python {ver_str} para recrear con {target_ver[0]}.{target_ver[1]}...")
            shutil.rmtree(venv_dir, ignore_errors=True)

    print(f"🚀 Relanzando con Python 3.12...")
    _reexec(py_exec, {"_WIFIVISION_PYTHON_OK": "1", "_WIFIVISION_VENV_ACTIVE": ""})


_ensure_compatible_python_windows()

# ─────────────────────────────────────────────────────────────
# Bootstrap de entorno virtual (automático)
# ─────────────────────────────────────────────────────────────

def _bootstrap_venv() -> None:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    venv_dir   = os.path.join(script_dir, ".venv")
    _win       = sys.platform == "win32"
    py_in_venv = os.path.join(venv_dir,
                               "Scripts" if _win else "bin",
                               "python.exe" if _win else "python")

    if sys.prefix != sys.base_prefix:
        # Ya dentro de un venv — verificar que la versión coincide
        vv = _venv_python_version(venv_dir)
        cv = (sys.version_info.major, sys.version_info.minor)
        if not vv or vv == cv:
            return
        print(f"♻️  Venv Python {vv} ≠ Python {cv}. Recreando...")
        shutil.rmtree(venv_dir, ignore_errors=True)

    if os.environ.get("_WIFIVISION_VENV_ACTIVE") == "1":
        return

    cv = (sys.version_info.major, sys.version_info.minor)

    if os.path.isfile(py_in_venv):
        # Verificar que el venv coincide con el Python actual antes de activarlo
        vv = _venv_python_version(venv_dir)
        if vv and vv != cv:
            print(f"♻️  Venv es Python {vv[0]}.{vv[1]}, actual es {cv[0]}.{cv[1]}. Recreando...")
            shutil.rmtree(venv_dir, ignore_errors=True)
        else:
            print("🚀 Activando entorno virtual...")
            _reexec(py_in_venv, {"_WIFIVISION_VENV_ACTIVE": "1"})

    print("⚙️  Creando entorno virtual (.venv)...")
    import venv as _vm
    _vm.create(venv_dir, with_pip=True, clear=True)
    print("   ✅ Entorno virtual creado.")
    print("🚀 Activando entorno virtual...")
    _reexec(py_in_venv, {"_WIFIVISION_VENV_ACTIVE": "1"})


_bootstrap_venv()

# ─────────────────────────────────────────────────────────────
# A partir de aquí: venv activo con Python correcto
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

# ─────────────────────────────────────────────────────────────
# Instalación automática de paquetes (sin preguntas)
# ─────────────────────────────────────────────────────────────

def _pip_install(pip_name: str) -> bool:
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--quiet",
         "--disable-pip-version-check", pip_name],
        capture_output=True,
    )
    if result.returncode != 0:
        last = (result.stderr or result.stdout or b"").decode(errors="replace").strip().splitlines()
        if last:
            print(f"   pip error: {last[-1]}")
    return result.returncode == 0


def _invalidate_import_cache(module_name: str) -> None:
    sys.modules.pop(module_name, None)
    importlib.invalidate_caches()


def _import(module_path: str):
    try:
        return importlib.import_module(module_path)
    except ImportError:
        return None
    except Exception:
        return None


def ensure_package(pip_name: str, module_path: str | None = None):
    """Importa un módulo; lo instala automáticamente si no existe."""
    if module_path is None:
        module_path = pip_name

    mod = _import(module_path)
    if mod is not None:
        return mod

    print(f"⚙️  Instalando {pip_name}...")
    if _pip_install(pip_name):
        _invalidate_import_cache(module_path.split(".")[0])
        mod = _import(module_path)
        if mod is not None:
            print(f"   ✅ {pip_name} listo.")
            return mod
    print(f"   ❌ No se pudo instalar {pip_name}.")
    return None


# ─────────────────────────────────────────────────────────────
# RTL-SDR: DLLs en Windows / udev en Linux
# ─────────────────────────────────────────────────────────────

def _scripts_dir() -> str:
    """Directorio de python.exe del venv activo (siempre está en PATH)."""
    return os.path.dirname(sys.executable)


def _register_dll_dir(directory: str) -> None:
    abs_dir = os.path.abspath(directory)
    try:
        os.add_dll_directory(abs_dir)
    except Exception:
        pass
    os.environ["PATH"] = abs_dir + os.pathsep + os.environ.get("PATH", "")


def _copy_dlls_to_scripts(src_dir: str) -> None:
    """
    Copia todas las DLLs al directorio de python.exe y crea alias
    rtlsdr.dll ↔ librtlsdr.dll porque pyrtlsdr busca 'librtlsdr'
    mientras el binario oficial se llama 'rtlsdr.dll'.
    """
    dst = _scripts_dir()
    for fname in os.listdir(src_dir):
        if fname.lower().endswith(".dll"):
            try:
                shutil.copy2(os.path.join(src_dir, fname),
                             os.path.join(dst, fname))
            except Exception:
                pass

    # Crear/actualizar alias rtlsdr.dll -> librtlsdr.dll (siempre se sobrescribe
    # para no dejar un alias desactualizado tras una nueva descarga)
    src = os.path.join(dst, "rtlsdr.dll")
    alias = os.path.join(dst, "librtlsdr.dll")
    if os.path.isfile(src):
        try:
            shutil.copy2(src, alias)
        except Exception:
            pass


def _dll_has_v4_support(path: str) -> bool:
    """
    Verifica que la DLL exporte rtlsdr_set_dithering, función presente solo
    en el fork de rtlsdrblog (necesaria para RTL-SDR v4 con tuner R828D).
    El driver clásico de osmocom no la tiene y falla al usarse con v4.
    """
    import ctypes
    try:
        lib = ctypes.CDLL(path)
        return hasattr(lib, "rtlsdr_set_dithering")
    except OSError:
        return False


def _dll_loadable() -> bool:
    """Verifica si rtlsdr/librtlsdr es cargable con ctypes y soporta v4."""
    scripts = _scripts_dir()
    for name in ("rtlsdr", "librtlsdr"):
        full = os.path.join(scripts, f"{name}.dll")
        if os.path.isfile(full) and _dll_has_v4_support(full):
            return True
    return False


def _download_rtlsdr_dlls() -> str | None:
    """
    Descarga el zip de RTL-SDR, extrae solo las DLLs de la arquitectura
    correcta (x64 para Python 64-bit, x32 para 32-bit) y las copia a Scripts/.
    """
    import tempfile

    arch_hint = "x64" if _IS_64BIT else "x32"
    # Solo el fork de rtlsdrblog soporta RTL-SDR v4 (función rtlsdr_set_dithering).
    # El driver clásico de osmocom NO sirve para v4, así que no se usa como mirror.
    mirrors = [
        "https://github.com/rtlsdrblog/rtl-sdr-blog/releases/latest/download/Release.zip",
    ]

    dll_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rtlsdr_dlls")
    os.makedirs(dll_dir, exist_ok=True)

    cached = os.path.join(dll_dir, "rtlsdr.dll")
    if os.path.isfile(cached):
        if _dll_has_v4_support(cached):
            return dll_dir
        # DLL antigua cacheada (sin soporte v4) de un intento previo: descartarla
        print("   ♻️  DLL cacheada sin soporte RTL-SDR v4, descargando de nuevo...")
        shutil.rmtree(dll_dir, ignore_errors=True)
        os.makedirs(dll_dir, exist_ok=True)

    print("⚙️  Descargando DLLs de RTL-SDR...")
    for url in mirrors:
        host = "/".join(url.split("/")[2:5])
        print(f"   → {host} ...")
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".zip", prefix="rtlsdr_")
        os.close(tmp_fd)
        try:
            urllib.request.urlretrieve(url, tmp_path)
            with zipfile.ZipFile(tmp_path, "r") as z:
                all_dlls = [n for n in z.namelist() if n.lower().endswith(".dll")]
                # Preferir DLLs en subcarpeta x64/ (o x32/)
                arch_dlls = [n for n in all_dlls if f"/{arch_hint}/" in n.lower() or
                             n.lower().startswith(arch_hint + "/")]
                chosen = arch_dlls if arch_dlls else all_dlls
                if not chosen:
                    print("   ✗ zip sin DLLs.")
                    continue
                for entry in chosen:
                    data = z.read(entry)
                    dest = os.path.join(dll_dir, os.path.basename(entry))
                    with open(dest, "wb") as f:
                        f.write(data)

            extracted = os.path.join(dll_dir, "rtlsdr.dll")
            if not os.path.isfile(extracted) or not _dll_has_v4_support(extracted):
                print("   ✗ DLL extraída no soporta RTL-SDR v4, probando siguiente mirror...")
                continue

            _copy_dlls_to_scripts(dll_dir)
            _register_dll_dir(dll_dir)
            print(f"   ✅ DLLs ({arch_hint}) listas, con soporte RTL-SDR v4.")
            return dll_dir
        except Exception as e:
            print(f"   ✗ {e}")
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
    return None


def _ensure_rtlsdr_dlls_windows() -> bool:
    """Garantiza que rtlsdr.dll es cargable. Totalmente automático."""
    if _dll_loadable():
        return True

    # Buscar en dll_dir local o Scripts/
    for search_dir in [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "rtlsdr_dlls"),
        _scripts_dir(),
    ]:
        if os.path.isfile(os.path.join(search_dir, "rtlsdr.dll")):
            _register_dll_dir(search_dir)
            _copy_dlls_to_scripts(search_dir)
            if _dll_loadable():
                return True

    # Descargar
    dll_dir = _download_rtlsdr_dlls()
    if dll_dir and _dll_loadable():
        return True

    print(f"\n   ⚠️  rtlsdr.dll no cargable. Copia manualmente a: {_scripts_dir()}")
    print("   Descarga: https://github.com/rtlsdrblog/rtl-sdr-blog/releases/latest")
    print("   Driver USB: https://zadig.akeo.ie  →  RTL-SDR → WinUSB")
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


def _preload_rtlsdr_deps() -> None:
    """
    Pre-carga libusb-1.0.dll y rtlsdr.dll/librtlsdr.dll por ruta completa
    antes de que Python intente importar el módulo rtlsdr.
    Esto garantiza que Windows encuentre las dependencias aunque no estén
    en %PATH% del sistema (solo en add_dll_directory o Scripts/).
    """
    import ctypes
    scripts = _scripts_dir()
    for dll in ("libusb-1.0.dll", "rtlsdr.dll", "librtlsdr.dll"):
        path = os.path.join(scripts, dll)
        if os.path.isfile(path):
            try:
                ctypes.CDLL(path)
            except OSError:
                pass


def _load_rtlsdr():
    """Carga pyrtlsdr automáticamente (sin preguntas)."""
    if IS_LINUX:
        _check_rtlsdr_linux()

    # Asegurar DLLs antes del primer import (Windows)
    if IS_WINDOWS:
        _ensure_rtlsdr_dlls_windows()
        _preload_rtlsdr_deps()   # pre-cargar dependencias por ruta completa

    _invalidate_import_cache("rtlsdr")

    # Primer intento de import
    try:
        return importlib.import_module("rtlsdr")
    except ImportError:
        pass
    except (OSError, AttributeError) as e:
        # DLL no encontrada, o cargada pero sin soporte v4
        # (AttributeError: "function 'rtlsdr_set_dithering' not found").
        if IS_WINDOWS:
            if "rtlsdr_set_dithering" in str(e):
                print("   ⚠️  DLL sin soporte RTL-SDR v4 detectada, forzando redescarga...")
                dll_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rtlsdr_dlls")
                shutil.rmtree(dll_dir, ignore_errors=True)
            _ensure_rtlsdr_dlls_windows()
            _preload_rtlsdr_deps()
            _invalidate_import_cache("rtlsdr")
            try:
                return importlib.import_module("rtlsdr")
            except Exception:
                pass
        return None
    except Exception:
        return None

    # Instalar automáticamente
    print("⚙️  Instalando pyrtlsdr...")
    if not _pip_install("pyrtlsdr"):
        # Verificar si es problema de Python 3.13+
        ver = (sys.version_info.major, sys.version_info.minor)
        if IS_WINDOWS and ver > (3, 12):
            print(f"   ❌ No hay wheel de pyrtlsdr para Python {ver[0]}.{ver[1]}.")
            print("   Reinicia el script; instalará Python 3.12 automáticamente.")
        else:
            print("   ❌ pip falló al instalar pyrtlsdr.")
        return None

    if IS_WINDOWS:
        _ensure_rtlsdr_dlls_windows()
        _preload_rtlsdr_deps()

    _invalidate_import_cache("rtlsdr")
    try:
        mod = importlib.import_module("rtlsdr")
        print("   ✅ pyrtlsdr listo.")
        return mod
    except (OSError, AttributeError) as e:
        if IS_WINDOWS and "rtlsdr_set_dithering" in str(e):
            print("   ⚠️  DLL sin soporte RTL-SDR v4 detectada, forzando redescarga...")
            dll_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rtlsdr_dlls")
            shutil.rmtree(dll_dir, ignore_errors=True)
            _ensure_rtlsdr_dlls_windows()
            _preload_rtlsdr_deps()
            _invalidate_import_cache("rtlsdr")
            try:
                mod = importlib.import_module("rtlsdr")
                print("   ✅ pyrtlsdr listo.")
                return mod
            except Exception as e2:
                print(f"   ❌ pyrtlsdr instalado pero no cargable: {e2}")
                return None
        print(f"   ❌ pyrtlsdr instalado pero no cargable: {e}")
        return None
    except Exception as e:
        print(f"   ❌ pyrtlsdr instalado pero no cargable: {e}")
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
# Modo sin hardware: visión aproximada solo con la tarjeta WiFi
# normal (sin RTL-SDR, HackRF ni PicoScenes)
# ─────────────────────────────────────────────────────────────

def _scan_wifi_rssi() -> list[tuple[str, int]]:
    """Devuelve (ssid, rssi_dbm) de las redes visibles, multiplataforma."""
    results: list[tuple[str, int]] = []

    if IS_WINDOWS:
        r = _run(["netsh", "wlan", "show", "networks", "mode=Bssid"])
        ssid = None
        for line in r.stdout.splitlines():
            line = line.strip()
            if line.startswith("SSID"):
                ssid = line.split(":", 1)[1].strip() or "(oculta)"
            elif line.startswith("Signal") and ssid:
                try:
                    pct = int(line.split(":", 1)[1].strip().rstrip("%"))
                    results.append((ssid, -100 + pct))
                except ValueError:
                    pass
        return results

    if IS_MACOS:
        airport = (
            "/System/Library/PrivateFrameworks/Apple80211.framework"
            "/Versions/Current/Resources/airport"
        )
        r = _run([airport, "-s"])
        for line in r.stdout.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 3:
                try:
                    results.append((parts[0], int(parts[2])))
                except ValueError:
                    pass
        return results

    # Linux
    if shutil.which("nmcli"):
        r = _run(["nmcli", "-t", "-f", "SSID,SIGNAL", "dev", "wifi", "list", "--rescan", "yes"])
        for line in r.stdout.splitlines():
            if ":" not in line:
                continue
            ssid, sig = line.rsplit(":", 1)
            try:
                pct = int(sig)
                results.append((ssid or "(oculta)", -100 + pct))
            except ValueError:
                pass
        if results:
            return results

    if shutil.which("iwlist"):
        iface = _detect_wifi_interface_linux()
        r = _run(_require_sudo_linux(["iwlist", iface, "scan"]))
        ssid = None
        for line in r.stdout.splitlines():
            line = line.strip()
            if line.startswith("ESSID"):
                ssid = line.split(":", 1)[1].strip('"') or "(oculta)"
            elif "Signal level" in line and ssid:
                try:
                    dbm = int(line.split("Signal level=")[1].split(" ")[0])
                    results.append((ssid, dbm))
                except (IndexError, ValueError):
                    pass

    return results


def wifi_rssi_vision() -> None:
    """
    Genera una imagen aproximada de intensidad de señal WiFi usando
    solo el adaptador WiFi normal (sin RTL-SDR/HackRF/PicoScenes).
    Pide muestras en varias posiciones físicas y construye un mapa
    simple de intensidad (no es CSI real, es una aproximación con RSSI).
    """
    np = _get_numpy()
    if np is None:
        print("❌ numpy no disponible.")
        return

    raw = input("¿Cuántas posiciones vas a muestrear? (mín. 2, recomendado 4-9) [4]: ").strip()
    try:
        n_pos = max(2, int(raw)) if raw else 4
    except ValueError:
        n_pos = 4

    grid = int(np.ceil(np.sqrt(n_pos)))
    samples: list[float] = []
    networks_seen: set[str] = set()

    for i in range(n_pos):
        input(f"\n📍 Posición {i + 1}/{n_pos}: muévete al punto deseado y presiona Enter...")
        readings = _scan_wifi_rssi()
        if not readings:
            print("   ⚠️  No se detectaron redes. Se usará -100 dBm.")
            samples.append(-100.0)
            continue
        avg_dbm = sum(d for _, d in readings) / len(readings)
        best_ssid, best_dbm = max(readings, key=lambda r: r[1])
        networks_seen.update(s for s, _ in readings)
        print(f"   📶 {len(readings)} redes vistas. Más fuerte: {best_ssid} ({best_dbm} dBm). "
              f"Promedio: {avg_dbm:.1f} dBm")
        samples.append(avg_dbm)

    while len(samples) < grid * grid:
        samples.append(min(samples))

    arr  = np.array(samples[: grid * grid]).reshape(grid, grid)
    rng  = arr.max() - arr.min()
    norm = (arr - arr.min()) / rng if rng > 0 else np.zeros_like(arr)
    img  = (norm * 255).astype(np.uint8)

    print(f"\n✅ Mapa de {grid}x{grid} construido a partir de {len(networks_seen)} redes detectadas.")
    print("   (Esto es una aproximación basada en RSSI, no una imagen CSI real.)")
    _save_and_show_image(img, "wifi_rssi_vision.png")


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


def capture_csi_rtlsdr(duration: int = 10, channel: int = 6, n_sub: int = 30) -> str | None:
    """
    Captura "pseudo-CSI" con un RTL-SDR (incluye RTL-SDR v4): no extrae CSI
    real de tramas 802.11 (el RTL-SDR no puede decodificar WiFi), pero
    construye una matriz tiempo x frecuencia vía FFT del espectro capturado
    en el canal WiFi elegido. Sirve como entrada aproximada al mismo
    pipeline de IA que usa CSI real (PicoScenes/HackRF).
    """
    np     = _get_numpy()
    tqdm   = _get_tqdm()
    rtlsdr = _get_rtlsdr()

    if rtlsdr is None:
        print("❌ pyrtlsdr no disponible.")
        return None
    if np is None:
        print("❌ numpy no disponible.")
        return None

    if channel not in _WIFI_CHANNELS:
        channel = 6
    freq_mhz = _WIFI_FREQS_MHZ[_WIFI_CHANNELS.index(channel)]

    try:
        sdr = rtlsdr.RtlSdr()
        sdr.sample_rate  = 2.4e6
        sdr.center_freq  = freq_mhz * 1e6
        sdr.gain         = "auto"
    except Exception as e:
        print(f"❌ No se pudo abrir el RTL-SDR: {e}")
        return None

    chunk_size = 4096
    n_frames   = max(1, int(duration * sdr.sample_rate / chunk_size))

    print(f"📥 Grabando {duration}s de pseudo-CSI (canal {channel}, {freq_mhz} MHz) con RTL-SDR...")
    frames = []
    try:
        iterable = range(n_frames)
        if tqdm is not None:
            iterable = tqdm(iterable, desc="Capturando pseudo-CSI", unit="frame")
        for _ in iterable:
            samples = sdr.read_samples(chunk_size)
            spectrum = np.fft.fftshift(np.fft.fft(samples))
            idx = np.linspace(0, len(spectrum) - 1, n_sub, dtype=int)
            bins = spectrum[idx]
            frames.append(np.stack([np.abs(bins), np.angle(bins)], axis=-1))
    finally:
        sdr.close()

    csi_array = np.array(frames)  # (n_frames, n_sub, 2)

    out_dir = os.path.join(os.getcwd(), "csi_captures")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"rtlsdr_pseudo_csi_ch{channel}_{int(time.time())}.npy")
    np.save(out_path, csi_array)
    print(f"✅ Captura guardada: {out_path}  (forma {csi_array.shape})")
    print("   ⚠️  Esto es una aproximación espectral, no CSI 802.11 real.")
    return out_path


# ─────────────────────────────────────────────────────────────
# Captura CSI con PicoScenes (cualquier NIC/SDR compatible,
# no solo HackRF: Intel AX200/AX210, Atheros ath9k, USRP, etc.)
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


def detect_csi_interfaces(has_hackrf: bool) -> list[str]:
    """
    Detecta interfaces compatibles con PicoScenes disponibles en el sistema.
    No asume HackRF: incluye también NICs WiFi (Intel AX/Atheros vía
    /sys/class/net en Linux) y USRP si las herramientas están presentes.
    """
    candidates: list[str] = []

    if has_hackrf:
        candidates.append("hackrf0")

    if IS_LINUX:
        try:
            for iface_dir in glob.glob("/sys/class/net/*/wireless"):
                iface = iface_dir.split("/")[4]
                if iface not in candidates:
                    candidates.append(iface)
        except Exception:
            pass
        if shutil.which("uhd_find_devices"):
            r = _run(["uhd_find_devices"])
            if r.returncode == 0 and r.stdout.strip():
                candidates.append("usrp0")

    return candidates


def capture_csi(interface: str, duration: int = 10) -> str | None:
    """Captura CSI con PicoScenes usando cualquier interfaz soportada."""
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
        "-i", interface,
        "--mode", "logger",
        "--freq", "2447",
        "--rx-gain", "60",
        "--output-dir", out_dir,
    ]
    print(f"📥 Grabando {duration}s de CSI con interfaz '{interface}'...")
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
        csi_interfaces = detect_csi_interfaces(has_hackrf)
        r_tag = "" if has_rtlsdr else "  [sin dispositivo]"
        c_tag = "" if (csi_interfaces or has_rtlsdr) else "  [sin dispositivo]"
        d_tag = f"  ({csi_data.shape[0]} frames cargados)" if csi_data is not None else "  [sin datos]"
        print(f"[1] Re-escanear dispositivos SDR")
        print(f"[2] Mostrar redes WiFi cercanas")
        print(f"[3] Escaneo de potencia WiFi RTL-SDR{r_tag}")
        print(f"[4] Capturar CSI (cualquier NIC/SDR compatible con PicoScenes){c_tag}")
        print(f"[5] Modo sin hardware: visión aproximada solo con WiFi")
        print(f"[6] Cargar archivo CSI del disco")
        print(f"[7] Descargar dataset demo")
        print(f"[8] Generar imagen con IA{d_tag}")
        print(f"[9] Salir")
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
            sources = [("picoscenes", iface) for iface in csi_interfaces]
            if has_rtlsdr:
                sources.append(("rtlsdr", "rtlsdr (pseudo-CSI vía FFT, aproximado)"))

            if not sources:
                print("⚠️  No se detectó ninguna fuente para CSI "
                      "(PicoScenes: HackRF/NIC WiFi/USRP, o un RTL-SDR conectado).")
                print("   Usa [5] para una alternativa sin hardware especial.")
            else:
                if len(sources) == 1:
                    kind, label = sources[0]
                else:
                    print("\nFuentes disponibles para captura CSI:")
                    for i, (_, label) in enumerate(sources):
                        print(f"  [{i}] {label}")
                    sel = input("Selecciona [0]: ").strip()
                    idx = int(sel) if sel.isdigit() and int(sel) < len(sources) else 0
                    kind, label = sources[idx]

                if kind == "rtlsdr":
                    path = capture_csi_rtlsdr()
                else:
                    path = capture_csi(label)

                if path:
                    try:
                        csi_data = load_csi_file(path)
                        print(f"✅ CSI cargado: {csi_data.shape}")
                    except Exception as e:
                        print(f"❌ Error al cargar CSI: {e}")
            _pause()

        elif op == "5":
            wifi_rssi_vision()
            _pause()

        elif op == "6":
            files = filter_csi_files()
            if not files:
                print("No se encontraron archivos CSI en la carpeta actual.")
                print("Extensiones buscadas: .csi  .pcap  .npy  .dat (>1 MB)")
                print("Usa [7] para descargar el dataset demo.")
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

        elif op == "7":
            path = download_demo()
            if path:
                try:
                    csi_data = load_csi_file(path)
                    print(f"✅ Dataset demo cargado: {csi_data.shape}")
                except Exception as e:
                    print(f"❌ Error al cargar demo: {e}")
            _pause()

        elif op == "8":
            if csi_data is None:
                print("⚠️  Primero carga datos CSI (opciones 4, 6 o 7).")
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

        elif op == "9":
            print("👋 Saliendo.")
            break

        else:
            print("❌ Opción no válida. Elige entre 1 y 9.")


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
