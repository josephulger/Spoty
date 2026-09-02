r"""
Spoty - webview arayüz giriş noktası.

Çalıştırmak için (proje kökünden):
    .\.venv\Scripts\python.exe -m spoty.webmain
"""
from __future__ import annotations

import sys
from pathlib import Path

import webview

from spoty.web_app import Api

# Windows gorev cubugu kimligi (AppUserModelID).
# Sabitlenen kisayol da AYNI degeri tasimali; tools/fix_shortcut.ps1 onu yazar.
APP_ID = "Ulger.Spoty"


def _set_windows_app_id() -> None:
    """Uygulamanin gorev cubugu kimligini bildirir.

    Ayarlanmazsa Windows kimligi calisan .exe'den turetir. Uygulama Python ile
    calistigi icin (pythonw.exe ya da setuptools'un urettigi launcher) o kimlik
    Python'a ait olur: gorev cubugunda Python ikonu gorunur ve sabitlenen
    kisayolla eslesmez, her acilista ayri bir ikon cikar.
    Kendi kimligimizi bildirince Windows pencerenin ikonunu (spoty.ico) kullanir.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:  # noqa: BLE001  (kimlik ayarlanamazsa uygulama yine calissin)
        pass


def _resource_dir() -> Path:
    """spoty paketinin kaynak dosyalarinin (web/, ico) bulundugu klasor.

    Paketlenmis (frozen/PyInstaller) exe'de __file__ gercek bir dosyayi
    gostermez (kod PYZ arsivinden yuklenir); bu durumda PyInstaller'in
    verileri actigi sys._MEIPASS kullanilir. Normal calistirmada spoty
    paketinin kendi klasorudur.
    """
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "spoty"  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent


def main() -> None:
    _set_windows_app_id()   # pencere olusturulmadan ONCE cagrilmali
    api = Api()
    resource_dir = _resource_dir()
    index = resource_dir / "web" / "index.html"
    icon = resource_dir / "spoty.ico" if getattr(sys, "frozen", False) else resource_dir.parent / "spoty.ico"
    window = webview.create_window(
        "Spoty",
        url=index.as_uri(),
        width=1100,
        height=720,
        min_size=(940, 600),
        background_color="#121212",
        js_api=api,
    )
    window.events.closing += api.save_state  # kapanışta ses/son şarkı kaydet
    webview.start(icon=str(icon))  # pencere/görev çubuğu ikonu


if __name__ == "__main__":
    main()
