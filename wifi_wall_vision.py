#!/usr/bin/env python3
"""
WiFi-Wall-Vision v16 - Compatible Windows y Linux
- Detecta el SO y adapta todos los comandos automáticamente.
- Instala y configura pyrtlsdr + DLLs en Windows.
- Escaneo de potencia WiFi (RTL-SDR) con gráfica.
- Captura CSI con HackRF (PicoScenes).
- Modelo WiFiCam integrado (descarga automática).
"""

from __future__ import annotations  # permite type hints en Python 3.9

import sys
import os
import time
import glob
import subprocess
import urllib.request
import shutil
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

def _pip_install(pip_name: str) -> bool:
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet", pip_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except Exception as e:
        print(f"   ❌ Error al instalar {pip_name}: {e}")
        return False


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
    if _pip_install(pip_name):
        mod = _import(module_path)
        if mod is not None:
            print(f"   ✅ {pip_name} instalado.")
            return mod
        print(f"   ❌ No se pudo importar {pip_name} tras instalarlo.")
    return None


# ─────────────────────────────────────────────────────────────
# RTL-SDR: DLLs en Windows / udev en Linux
# ─────────────────────────────────────────────────────────────

def _ensure_rtlsdr_dlls_windows() -> bool:
    """Descarga las DLL de RTL-SDR en Windows si no están presentes."""
    dll_names = ["rtlsdr.dll", "libusb-1.0.dll"]
    if all(os.path.exists(d) for d in dll_names):
        try:
            os.add_dll_directory(os.getcwd())
        except Exception:
            pass
        return True

    print("🌐 Faltan DLL de RTL-SDR. Descargando...")
    url = (
        "https://github.com/osmocom/rtl-sdr/releases/download/v0.6.0/"
        "rtl-sdr-0.6.0-win32.zip"
    )
    zip_path = "rtl-sdr-dlls.zip"
    try:
        urllib.request.urlretrieve(url, zip_path)
        with zipfile.ZipFile(zip_path, "r") as z:
            for name in z.namelist():
                if name.endswith(".dll"):
                    z.extract(name, ".")
        os.remove(zip_path)
        os.add_dll_directory(os.getcwd())
        print("✅ DLLs instaladas.")
        return True
    except Exception as e:
        print(f"❌ Error al descargar DLLs: {e}")
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


def _load_rtlsdr():
    """Carga pyrtlsdr gestionando dependencias según el SO."""
    if IS_WINDOWS:
        _ensure_rtlsdr_dlls_windows()
    elif IS_LINUX:
        _check_rtlsdr_linux()

    mod = _import("rtlsdr")
    if mod is not None:
        return mod

    print("\n⚠️  El módulo 'pyrtlsdr' no está instalado.")
    resp = input("   ¿Instalarlo ahora? [S/n]: ").strip().lower()
    if resp not in ("", "s", "si", "y", "yes"):
        return None

    print("   Instalando pyrtlsdr...")
    if _pip_install("pyrtlsdr"):
        if IS_WINDOWS:
            _ensure_rtlsdr_dlls_windows()
        mod = _import("rtlsdr")
        if mod is not None:
            print("   ✅ pyrtlsdr instalado.")
            return mod
    print("   ❌ No se pudo importar pyrtlsdr.")
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


def _print_sysinfo() -> None:
    print(f"\nSistema: {platform.system()} {platform.release()} | Python {sys.version.split()[0]}")
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
    main()
