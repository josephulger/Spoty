"""
Spoty - GitHub Releases uzerinden otomatik guncelleme.

Yalnizca paketlenmis (frozen/PyInstaller) exe'de anlamlidir; gelistirme
ortaminda (python -m spoty.webmain) guncelleme kontrolu yapilmaz.

Akis:
  1) check_latest()   -> en son surumu GitHub API'sinden okur, mevcutla kiyaslar.
  2) start_update()   -> yeni surumun zip'ini indirir, gecici klasore acar,
                         calisan exe kapanip yeni dosyalar ustune kopyalanana
                         kadar bekleyen bir .bat olusturup baslatir, sonra
                         uygulamayi kapatir (main() cagirir).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable, Optional

from spoty import config

_API_URL = f"https://api.github.com/repos/{config.GITHUB_REPO}/releases/latest"
_HEADERS = {"Accept": "application/vnd.github+json", "User-Agent": "Spoty-Updater"}


def _version_tuple(v: str) -> tuple:
    v = (v or "").strip().lstrip("vV")
    parts = []
    for p in v.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    return tuple(parts) or (0,)


def is_newer(latest: str, current: str) -> bool:
    return _version_tuple(latest) > _version_tuple(current)


def check_latest() -> dict:
    """En son GitHub release bilgisini doner. Hata/offline durumunda {}."""
    try:
        req = urllib.request.Request(_API_URL, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:  # noqa: BLE001  (internet yok / API hatasi -> sessizce vazgec)
        return {}

    tag = str(data.get("tag_name") or "")
    asset_url = ""
    for a in data.get("assets") or []:
        name = str(a.get("name") or "")
        if name.lower().endswith(".zip"):
            asset_url = a.get("browser_download_url") or ""
            break

    if not tag or not asset_url:
        return {}

    return {
        "version": tag.lstrip("vV"),
        "url": asset_url,
        "notes": str(data.get("body") or ""),
        "available": is_newer(tag, config.APP_VERSION),
    }


def _install_dir() -> Path:
    return Path(sys.executable).resolve().parent


def start_update(
    asset_url: str,
    on_progress: Optional[Callable[[str, float], None]] = None,
) -> None:
    """Yeni surumu indirip kurar ve uygulamayi yeniden baslatir.

    Bu fonksiyon donmez: son adimda mevcut process'i kapatir (os._exit).
    Ayri bir thread'den cagirilmasi beklenir (arayuz kilitlenmesin diye).
    """
    if not getattr(sys, "frozen", False):
        raise RuntimeError("Guncelleme yalnizca paketlenmis exe'de calisir")

    def report(phase: str, pct: float) -> None:
        if on_progress:
            try:
                on_progress(phase, pct)
            except Exception:  # noqa: BLE001
                pass

    tmp_dir = Path(tempfile.mkdtemp(prefix="spoty_update_"))
    zip_path = tmp_dir / "update.zip"
    extract_dir = tmp_dir / "extracted"

    report("indiriliyor", 0.0)
    req = urllib.request.Request(asset_url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp, open(zip_path, "wb") as f:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = resp.read(1024 * 256)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if total:
                report("indiriliyor", round(done * 100.0 / total, 1))

    report("açılıyor", 100.0)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(extract_dir)

    # Zip'in icinde tek bir ust klasor bekleniyor (orn. "Spoty/Spoty.exe").
    entries = [p for p in extract_dir.iterdir() if p.is_dir()]
    src_dir = entries[0] if len(entries) == 1 else extract_dir
    dst_dir = _install_dir()

    pid = os.getpid()
    bat_path = tmp_dir / "spoty_update.bat"
    bat_path.write_text(
        "@echo off\r\n"
        # tasklist ciktisinda PID metin arama YANLIS eslesebilir (orn. 12 icin
        # 123 de eslesir) ve sonsuza kadar beklemede kalir; Wait-Process pid'i
        # tam esler ve process zaten kapanmissa hemen doner.
        f'powershell -NoProfile -Command "Wait-Process -Id {pid} -Timeout 15 -ErrorAction SilentlyContinue"\r\n'
        # robocopy sinirli deneme yapar (AV/gezgin dosyayi kisa sure kilitleyebilir)
        # yoksa varsayilan olarak dakikalarca donebilir.
        f'robocopy "{src_dir}" "{dst_dir}" /E /IS /IT /R:10 /W:1 /NFL /NDL /NJH /NJS\r\n'
        f'start "" "{dst_dir / "Spoty.exe"}"\r\n'
        f'rmdir /s /q "{tmp_dir}"\r\n',
        encoding="utf-8",
    )

    report("yeniden başlatılıyor", 100.0)
    subprocess.Popen(
        ["cmd", "/c", str(bat_path)],
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
        close_fds=True,
    )
    os._exit(0)


def start_update_async(asset_url: str, on_progress: Optional[Callable[[str, float], None]] = None) -> None:
    threading.Thread(target=start_update, args=(asset_url, on_progress), daemon=True).start()
