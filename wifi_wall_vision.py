#!/usr/bin/env python3
"""
WiFi-Wall-Vision v15 - Automatización completa con visualización gráfica
- Instala y configura pyrtlsdr + DLLs automáticamente.
- Escaneo de potencia WiFi (RTL-SDR).
- Gráfica de barras del espectro tras el escaneo (requiere matplotlib).
- Captura CSI con HackRF (PicoScenes).
- Modelo WiFiCam integrado (descarga automática).
"""

import sys
import os
import time
import glob
import subprocess
import urllib.request
import shutil
import zipfile
import platform

# ------------------------------------------------------------
# Helpers de instalación dinámica
# ------------------------------------------------------------

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
    """Importa un módulo por su ruta completa (p.ej. 'matplotlib.pyplot')."""
    import importlib
    try:
        return importlib.import_module(module_path)
    except ImportError:
        return None
    except Exception as e:
        print(f"⚠️  No se pudo importar {module_path}: {e}")
        return None


def ensure_package(pip_name: str, module_path: str | None = None):
    """
    Garantiza que un paquete está disponible.
    Pregunta al usuario antes de instalar.
    Devuelve el módulo importado o None.
    """
    if module_path is None:
        module_path = pip_name

    mod = _import(module_path)
    if mod is not None:
        return mod

    print(f"\n⚠️  El módulo '{pip_name}' no está instalado.")
    resp = input(f"   ¿Quieres instalarlo ahora? [S/n]: ").strip().lower()
    if resp not in ("", "s", "si", "y", "yes"):
        print("   Omitido. Las funciones relacionadas no estarán disponibles.")
        return None

    print(f"   Instalando {pip_name}...")
    if _pip_install(pip_name):
        mod = _import(module_path)
        if mod is not None:
            print(f"   ✅ {pip_name} instalado correctamente.")
            return mod
        print(f"   ❌ No se pudo importar {pip_name} tras instalarlo.")
    return None


# ------------------------------------------------------------
# Configuración de DLLs en Windows (RTL-SDR)
# ------------------------------------------------------------

def ensure_rtlsdr_dlls() -> bool:
    if platform.system() != "Windows":
        return True

    dll_names = ["rtlsdr.dll", "libusb-1.0.dll"]
    if all(os.path.exists(d) for d in dll_names):
        try:
            os.add_dll_directory(os.getcwd())
        except Exception:
            pass
        return True

    print("🌐 Faltan las DLL de RTL-SDR. Descargándolas automáticamente...")
    dll_url = (
        "https://github.com/osmocom/rtl-sdr/releases/download/v0.6.0/"
        "rtl-sdr-0.6.0-win32.zip"
    )
    zip_path = "rtl-sdr-dlls.zip"
    try:
        urllib.request.urlretrieve(dll_url, zip_path)
        with zipfile.ZipFile(zip_path, "r") as z:
            for name in z.namelist():
                if name.endswith(".dll"):
                    z.extract(name, ".")
        os.remove(zip_path)
        os.add_dll_directory(os.getcwd())
        print("✅ DLLs instaladas correctamente.")
        return True
    except Exception as e:
        print(f"❌ Error al descargar DLLs: {e}")
        return False


def _load_rtlsdr():
    """Carga pyrtlsdr gestionando DLLs en Windows."""
    if platform.system() == "Windows":
        ensure_rtlsdr_dlls()

    mod = _import("rtlsdr")
    if mod is not None:
        return mod

    print("\n⚠️  El módulo 'pyrtlsdr' no está instalado.")
    resp = input("   ¿Quieres instalarlo ahora? [S/n]: ").strip().lower()
    if resp not in ("", "s", "si", "y", "yes"):
        return None

    print("   Instalando pyrtlsdr...")
    if _pip_install("pyrtlsdr"):
        if platform.system() == "Windows":
            ensure_rtlsdr_dlls()
        mod = _import("rtlsdr")
        if mod is not None:
            print("   ✅ pyrtlsdr instalado correctamente.")
            return mod
        print("   ❌ No se pudo importar pyrtlsdr tras instalarlo.")
    return None


# ------------------------------------------------------------
# Importaciones opcionales (carga diferida)
# ------------------------------------------------------------

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
    global _tqdm
    if _tqdm is None:
        mod = ensure_package("tqdm")
        _tqdm = mod.tqdm if mod is not None else None
    return _tqdm

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

_np = None
_cv2 = None
_tqdm = None
_plt = None
_rtlsdr = None


# ------------------------------------------------------------
# Detección de hardware
# ------------------------------------------------------------

def detect_rtlsdr() -> bool:
    rtlsdr = _get_rtlsdr()
    if rtlsdr is None:
        return False
    try:
        sdr = rtlsdr.RtlSdr()
        info = str(sdr.get_center_freq())  # operación mínima para verificar apertura
        sdr.close()
        print("✅ RTL-SDR detectado y funcional.")
        return True
    except Exception as e:
        print(f"❌ No se pudo abrir el RTL-SDR: {e}")
        print("   Asegúrate de que el dispositivo esté conectado y el driver correcto instalado.")
        return False


def detect_hackrf() -> bool:
    try:
        result = subprocess.run(
            ["hackrf_info"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and "Found HackRF" in result.stdout:
            print("✅ HackRF detectado.")
            return True
    except Exception:
        pass
    return False


# ------------------------------------------------------------
# Escaneo de potencia WiFi + gráfica
# ------------------------------------------------------------

# Canales 2.4 GHz estándar (1-13)
_WIFI_CHANNELS = list(range(1, 14))
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
    fig.savefig("wifi_spectrum.png")
    print("💾 Gráfica guardada como 'wifi_spectrum.png'")
    plt.show()


def wifi_power_scan_rtlsdr(duration: int = 10) -> list | None:
    np = _get_numpy()
    tqdm = _get_tqdm()
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
    results = []
    iterator = (
        tqdm(zip(_WIFI_FREQS_MHZ, _WIFI_CHANNELS), total=len(_WIFI_CHANNELS), desc="Barriendo canales")
        if tqdm is not None
        else zip(_WIFI_FREQS_MHZ, _WIFI_CHANNELS)
    )

    try:
        for freq_mhz, ch in iterator:
            sdr.center_freq = freq_mhz * 1e6
            time.sleep(0.3)
            samples = sdr.read_samples(256 * 1024)
            power = np.mean(np.abs(samples) ** 2)
            power_dbm = 10 * np.log10(power + 1e-12) - 30
            results.append((ch, freq_mhz, power_dbm))
    finally:
        sdr.close()

    print("\nCanal | Frecuencia (MHz) | Potencia (dBm)")
    print("-" * 45)
    for ch, f, p in results:
        print(f"  {ch:2}  |     {f:7.1f}      |   {p:6.1f}")

    csv_path = "wifi_power_scan.csv"
    with open(csv_path, "w") as fp:
        fp.write("Canal,Frecuencia_MHz,Potencia_dBm\n")
        for ch, f, p in results:
            fp.write(f"{ch},{f},{p:.2f}\n")
    print(f"💾 Datos guardados en '{csv_path}'")

    if _get_plt() is not None:
        resp = input("\n¿Generar gráfica del espectro? [S/n]: ").strip().lower()
        if resp in ("", "s", "si", "y", "yes"):
            plot_power_scan(results)

    return results


# ------------------------------------------------------------
# Captura CSI con HackRF (PicoScenes)
# ------------------------------------------------------------

def capture_csi_hackrf(duration: int = 10) -> str | None:
    tqdm = _get_tqdm()

    if not shutil.which("PicoScenes"):
        print("❌ PicoScenes no instalado. Descárgalo de https://ps.zpj.io")
        return None

    out_dir = "./csi_captures"
    os.makedirs(out_dir, exist_ok=True)

    cmd = [
        "PicoScenes", "-d", "debug",
        "-i", "hackrf0",
        "--mode", "logger",
        "--freq", "2447",
        "--rx-gain", "60",
    ]
    print(f"📥 Grabando {duration}s de CSI con HackRF...")
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if tqdm is not None:
        for _ in tqdm(range(duration), desc="Capturando CSI", unit="s"):
            time.sleep(1)
    else:
        for i in range(duration):
            time.sleep(1)
            print(f"  {i+1}/{duration}s...", end="\r")
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


def filter_csi_files() -> list:
    candidates = []
    for ext in ("*.csi", "*.pcap", "*.npy"):
        candidates.extend(glob.glob(ext))
    for f in glob.glob("*.dat"):
        if os.path.getsize(f) > 1_000_000:
            candidates.append(f)
    return sorted(set(candidates))


def load_csi_file(path: str):
    np = _get_numpy()
    if np is None:
        raise RuntimeError("numpy no disponible")

    if path.endswith(".npy"):
        data = np.load(path)
        # Normalizar a shape (frames, subcarriers, 2)
        if data.ndim == 2:
            data = data[:, :, np.newaxis]
            data = np.concatenate([np.abs(data), np.angle(data)], axis=-1)
        return data

    try:
        import importlib
        csikit = importlib.import_module("CSIKit.reader")
        reader = csikit.get_reader(path)
        csi_data = reader.read_file(path)
        frames = []
        for frame in csi_data.frames:
            mat = frame.csi_matrix[0, 0, :]
            frames.append(np.stack([np.abs(mat), np.angle(mat)], axis=1))
        return np.array(frames)
    except ImportError:
        pass  # CSIKit not available, fall back

    # Fallback: leer como complejo crudo
    raw = np.fromfile(path, dtype=np.complex64)
    if raw.size == 0:
        raise ValueError("Archivo vacío o formato no soportado.")
    n_sub = 30
    n_frames = raw.size // n_sub
    raw = raw[: n_frames * n_sub].reshape(n_frames, n_sub)
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
        print("✅ Listo.")
        return dest
    except Exception as e:
        print(f"❌ Error al descargar el demo: {e}")
        return None


# ------------------------------------------------------------
# Modelo WiFiCam (VAE)
# ------------------------------------------------------------

_MODEL = None
_DEVICE = None
_N_SUB = 30   # subcarriers
_N_FRAMES = 200


def _build_wificam(torch, nn):
    class Encoder(nn.Module):
        def __init__(self, input_dim: int = _N_FRAMES * _N_SUB, latent_dim: int = 128):
            super().__init__()
            self.fc1 = nn.Linear(input_dim, 512)
            self.fc_mu = nn.Linear(512, latent_dim)
            self.fc_logvar = nn.Linear(512, latent_dim)

        def forward(self, x):
            h = torch.relu(self.fc1(x))
            return self.fc_mu(h), self.fc_logvar(h)

    class Decoder(nn.Module):
        def __init__(self, latent_dim: int = 128):
            super().__init__()
            self.fc = nn.Linear(latent_dim, 256)
            self.deconv = nn.Sequential(
                nn.ConvTranspose2d(256, 128, 4, 2, 1), nn.ReLU(),
                nn.ConvTranspose2d(128,  64, 4, 2, 1), nn.ReLU(),
                nn.ConvTranspose2d( 64,  32, 4, 2, 1), nn.ReLU(),
                nn.ConvTranspose2d( 32,   1, 4, 2, 1), nn.Sigmoid(),
            )

        def forward(self, z):
            h = torch.relu(self.fc(z))
            h = h.view(-1, 256, 1, 1)
            return self.deconv(h)

    class WiFiCam(nn.Module):
        def __init__(self):
            super().__init__()
            self.encoder = Encoder()
            self.decoder = Decoder()

        def _reparam(self, mu, logvar):
            std = torch.exp(0.5 * logvar)
            return mu + std * torch.randn_like(std)

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
    model = _build_wificam(torch, nn).to(device)

    try:
        checkpoint = torch.load(model_path, map_location=device)
        state = checkpoint.get("state_dict", checkpoint)
        model.load_state_dict(state, strict=False)
    except Exception as e:
        print(f"⚠️  No se pudo cargar el checkpoint exacto: {e}")
        print("   Se usará el modelo con pesos aleatorios (resultado demostrativo).")

    model.eval()
    _MODEL = model
    _DEVICE = device
    print("✅ Modelo de IA listo.")
    return model, device


def preprocess_csi(csi_array) -> object:
    np = _get_numpy()
    n_frames, n_sub = csi_array.shape[:2]

    # Ajustar número de frames
    if n_frames > _N_FRAMES:
        idx = np.linspace(0, n_frames - 1, _N_FRAMES, dtype=int)
        csi_array = csi_array[idx]
    elif n_frames < _N_FRAMES:
        pad = _N_FRAMES - n_frames
        csi_array = np.pad(csi_array, ((0, pad), (0, 0), (0, 0)), mode="edge")

    # Ajustar número de subcarriers
    if n_sub > _N_SUB:
        idx = np.linspace(0, n_sub - 1, _N_SUB, dtype=int)
        csi_array = csi_array[:, idx, :]
    elif n_sub < _N_SUB:
        pad = _N_SUB - n_sub
        csi_array = np.pad(csi_array, ((0, 0), (0, pad), (0, 0)), mode="edge")

    # Normalizar amplitud al rango [0, 1]
    amp = csi_array[:, :, 0]
    a_min, a_max = amp.min(), amp.max()
    if a_max > a_min:
        csi_array = csi_array.copy().astype(float)
        csi_array[:, :, 0] = (amp - a_min) / (a_max - a_min)

    return csi_array


def generate_image(model, csi_array, device) -> object:
    import torch

    np = _get_numpy()
    # Usar solo la amplitud: shape (N_FRAMES, N_SUB) → aplanar a vector
    amp = csi_array[:, :, 0].astype(float)
    x = torch.tensor(amp.flatten(), dtype=torch.float32).unsqueeze(0).to(device)

    with torch.no_grad():
        img_tensor, _, _ = model(x)

    img = img_tensor.squeeze().cpu().numpy()
    img = (img * 255).clip(0, 255).astype(np.uint8)
    return img


# ------------------------------------------------------------
# Menú principal
# ------------------------------------------------------------

def _pause():
    input("\nPresiona Enter para continuar...")


def main():
    has_rtlsdr = detect_rtlsdr()
    has_hackrf = detect_hackrf()
    csi_data = None

    while True:
        print("\n" + "=" * 60)
        print("       WiFi-Wall-Vision  –  Menú Principal")
        print("=" * 60)
        rtlsdr_tag = "" if has_rtlsdr else " [no disponible]"
        hackrf_tag = "" if has_hackrf else " [no disponible]"
        print("[1] Re-escanear dispositivos SDR")
        print("[2] Mostrar redes WiFi cercanas")
        print(f"[3] Escaneo de potencia WiFi (RTL-SDR){rtlsdr_tag}")
        print(f"[4] Capturar CSI con HackRF{hackrf_tag}")
        print("[5] Cargar archivo CSI del disco")
        print("[6] Descargar dataset demo")
        print("[7] Generar imagen con IA")
        print("[8] Salir")
        op = input("Opción: ").strip()

        if op == "1":
            has_rtlsdr = detect_rtlsdr()
            has_hackrf = detect_hackrf()
            _pause()

        elif op == "2":
            print("\n📡 Redes WiFi cercanas:")
            if os.name == "nt":
                subprocess.run(["netsh", "wlan", "show", "networks", "mode=bssid"])
            else:
                iface = "wlan0"
                result = subprocess.run(
                    ["sudo", "iwlist", iface, "scan"],
                    capture_output=True, text=True,
                )
                if result.returncode != 0:
                    # Intentar con nmcli como alternativa
                    result = subprocess.run(
                        ["nmcli", "-f", "SSID,BSSID,SIGNAL,CHAN,SECURITY", "dev", "wifi"],
                        capture_output=True, text=True,
                    )
                print(result.stdout or result.stderr or "Sin resultados.")
            _pause()

        elif op == "3":
            if not has_rtlsdr:
                print("⚠️  RTL-SDR no disponible. Usa '[1] Re-escanear' primero.")
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
                        print(f"✅ Datos CSI cargados: {csi_data.shape}")
                    except Exception as e:
                        print(f"❌ Error al cargar: {e}")
            _pause()

        elif op == "5":
            files = filter_csi_files()
            if not files:
                print("No se encontraron archivos CSI (.csi, .pcap, .npy, .dat) en la carpeta actual.")
                print("Usa la opción [6] para descargar el dataset demo.")
            else:
                print("\nArchivos disponibles:")
                for i, f in enumerate(files):
                    size_mb = os.path.getsize(f) / 1e6
                    print(f"  [{i}] {f}  ({size_mb:.1f} MB)")
                print("  [D] Descargar y usar demo")
                sel = input("Selecciona: ").strip().lower()
                if sel == "d":
                    path = download_demo()
                    if path:
                        np = _get_numpy()
                        csi_data = np.load(path)
                        if csi_data.ndim == 2:
                            csi_data = csi_data[:, :, np.newaxis]
                        print(f"✅ Demo cargado: {csi_data.shape}")
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
                np = _get_numpy()
                raw = np.load(path)
                if raw.ndim == 2:
                    raw = raw[:, :, np.newaxis]
                    raw = np.concatenate([np.abs(raw), np.angle(raw)], axis=-1)
                csi_data = raw
                print(f"✅ Dataset demo cargado: {csi_data.shape}")
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
                        prep = preprocess_csi(csi_data)
                        img = generate_image(model, prep, device)
                        out_path = "vista_traves_pared.png"
                        cv2 = _get_cv2()
                        if cv2 is not None:
                            cv2.imwrite(out_path, img)
                            print(f"💾 Imagen guardada: {out_path}")
                            cv2.imshow("Resultado WiFi-Wall-Vision", img)
                            cv2.waitKey(0)
                            cv2.destroyAllWindows()
                        else:
                            # Fallback: guardar con matplotlib
                            plt = _get_plt()
                            if plt is not None:
                                plt.imsave(out_path, img, cmap="gray")
                                print(f"💾 Imagen guardada: {out_path}")
                                plt.imshow(img, cmap="gray")
                                plt.title("Resultado WiFi-Wall-Vision")
                                plt.axis("off")
                                plt.show()
                            else:
                                print("❌ Ni OpenCV ni matplotlib disponibles para mostrar la imagen.")
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
