r"""
Spoty - webview arayüz giriş noktası.

Çalıştırmak için (proje kökünden):
    .\.venv\Scripts\python.exe -m spoty.webmain
"""
from __future__ import annotations

from pathlib import Path

import webview

from spoty.web_app import Api


def main() -> None:
    api = Api()
    index = Path(__file__).resolve().parent / "web" / "index.html"
    icon = Path(__file__).resolve().parent.parent / "spoty.ico"  # proje kökündeki uygulama ikonu
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
