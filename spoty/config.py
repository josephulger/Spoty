"""
Spoty - merkezi ayarlar ve klasor yollari.

Tum moduller (downloader, player, library, arayuz) buradan yol bilgisi alir.
Boylece klasor yapisini tek yerden degistirebiliriz.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

# Bu dosya: <proje>/spoty/config.py
#   .parent        -> <proje>/spoty
#   .parent.parent -> <proje> (proje koku)
# PyInstaller ile paketlenmisse (frozen), veriler exe'nin yaninda tutulur;
# yoksa iceride kalir ve gunumleri kaybederiz.
if getattr(sys, "frozen", False):
    PROJECT_ROOT: Path = Path(sys.executable).resolve().parent
else:
    PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent

# Bu bilgisayari kullanan kisinin adi (calma sayaci "kim kac kere dinledi"
# gostersin diye). Makineye ozeldir, PROJECT_ROOT'ta durur, senkron edilmez --
# kutuphane bulutta paylasilsa bile herkes kendi adini kendi bilgisayarinda
# ayarlar (bkz. spoty/core/cloud.py).
USER_NAME_FILE: Path = PROJECT_ROOT / "user_name.txt"


def get_user_name() -> str:
    try:
        return USER_NAME_FILE.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def set_user_name(name: str) -> None:
    USER_NAME_FILE.write_text((name or "").strip(), encoding="utf-8")

# Indirilen mp3'lerin yerel onbellegi (asil kutuphane buluttadir, bkz. cloud.py;
# burasi bu bilgisayarda daha once calinmis/indirilmis dosyalari tutar)
MUSIC_DIR: Path = PROJECT_ROOT / "music"

# Indirilen videolarin gidecegi klasor (muzik kutuphanesinden ayri tutulur)
VIDEO_DIR: Path = PROJECT_ROOT / "video"

# Veritabani vb. verilerin tutuldugu klasor (ses/son calinan sarki gibi
# makineye ozel ayarlar; kutuphanenin kendisi artik burada degil)
DATA_DIR: Path = PROJECT_ROOT / "data"
DB_PATH: Path = DATA_DIR / "spoty.db"

# Klasorler yoksa otomatik olustur (uygulama her acildiginda garanti)
MUSIC_DIR.mkdir(parents=True, exist_ok=True)
VIDEO_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Surum / guncelleme (GitHub Releases). pyproject.toml'daki version ile birlikte
# elle guncellenir; her yeni .exe paketlemesinde ikisi de artmali.
APP_VERSION: str = "1.1.0"
GITHUB_REPO: str = "josephulger/Spoty"

# Paylasilan bulut kutuphanesi (Supabase). Doldurulursa (bkz. spoty/core/cloud.py)
# kutuphane/calma listeleri/calma sayaclari yerelde degil bu projede tutulur;
# muzik dosyalari da 'spoty-music' depolama kovasina yuklenir. Boylece iki
# kisi hicbir klasor senkronu kurmadan ayni kutuphaneyi gorur.
SUPABASE_URL: str = "https://zzccpoliwbaaebbjopfc.supabase.co"
SUPABASE_ANON_KEY: str = "sb_publishable_ONxpfoUvWgRcbHXZQWfXNA_9TBjrgpe"
SUPABASE_BUCKET: str = "spoty-music"

# Indirme varsayilanlari
AUDIO_FORMAT: str = "mp3"
AUDIO_QUALITY: str = "192"  # kbps
SEARCH_LIMIT: int = 10      # aramada gosterilecek sonuc sayisi

# Video indirme varsayilanlari
# "bv*+ba/b" = en iyi goruntu + en iyi ses ayri ayri indirilir, ffmpeg BIRLESTIRIR.
# Birlestirme "stream copy"dir: yeniden kodlama YOK -> kalite kaybi YOK.
VIDEO_FORMAT: str = "bv*+ba/b"
VIDEO_CONTAINER: str = "mp4"


def find_ffmpeg_dir() -> str | None:
    """ffmpeg.exe'nin bulundugu klasoru dondurur (yt-dlp'ye 'ffmpeg_location' olarak verilir).

    Once exe ile birlikte paketlenmis ffmpeg'e bakar, sonra sistem PATH'ine,
    sonra winget'in ffmpeg'i kurdugu standart konuma duser. Hicbiri yoksa None
    doner (yt-dlp yine PATH'i kendi dener).
    """
    if getattr(sys, "frozen", False):
        bundled = Path(sys.executable).resolve().parent / "ffmpeg.exe"
        if bundled.exists():
            return str(bundled.parent)

    exe = shutil.which("ffmpeg")
    if exe:
        return str(Path(exe).parent)

    # winget (Gyan.FFmpeg) genelde buraya alias koyar:
    localappdata = os.environ.get("LOCALAPPDATA", "")
    if localappdata:
        winget_links = Path(localappdata) / "Microsoft" / "WinGet" / "Links"
        if (winget_links / "ffmpeg.exe").exists():
            return str(winget_links)

    return None
