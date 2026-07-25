"""
Spoty - Arama ve indirme cekirdegi (yt-dlp + ffmpeg).

Bu modul arayuzden tamamen bagimsizdir:
  - search(sorgu)             -> YouTube'da isimle arar, sonuc listesi dondurur
  - download(sonuc)           -> secilen sonucu mp3 olarak indirir,
                                 kapak resmi + sarki/sanatci bilgisini icine gomer
  - download_video_from_url() -> linki mp4 olarak video/ klasorune indirir
                                 (en iyi kalite, yeniden kodlama yok)

Terminalden tek basina da calistirilabilir (en altta __main__ bolumu):
    python -m spoty.core.downloader
    python -m spoty.core.downloader "daft punk one more time"
    python -m spoty.core.downloader --video "https://www.youtube.com/watch?v=..."
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import yt_dlp

from spoty import config


# ---------------------------------------------------------------------------
# Veri tasiyici siniflar (sadece bilgi tutar, mantik icermez)
# ---------------------------------------------------------------------------
@dataclass
class SearchResult:
    """Aramadan donen tek bir sonucu temsil eder."""
    video_id: str
    title: str
    uploader: str          # kanal / yukleyen adi
    duration: int          # saniye cinsinden sure (0 = bilinmiyor)
    url: str               # izleme adresi (indirme bunu kullanir)
    thumbnail: Optional[str]  # kucuk resim adresi (arayuzde onizleme icin)

    @property
    def duration_str(self) -> str:
        """Sureyi 'd:ss' formatinda metne cevirir (orn. 3:24)."""
        m, s = divmod(int(self.duration or 0), 60)
        return f"{m}:{s:02d}"


@dataclass
class DownloadedTrack:
    """Basariyla indirilen bir sarkinin sonucu."""
    title: str
    artist: str
    duration: int
    filepath: str          # diskteki mp3 yolu
    source_url: str        # nereden indirildigi


@dataclass
class DownloadedVideo:
    """Basariyla indirilen bir videonun sonucu (video/ klasorune iner)."""
    title: str
    uploader: str
    duration: int
    filepath: str          # diskteki video yolu (genelde .mp4)
    source_url: str
    width: int = 0         # cozunurluk (0 = bilinmiyor)
    height: int = 0
    ext: str = ""          # gercek uzanti: mp4 (nadiren mkv/webm)

    @property
    def resolution_str(self) -> str:
        """Cozunurlugu '1920x1080' gibi metne cevirir (bilinmiyorsa '-')."""
        return f"{self.width}x{self.height}" if self.width and self.height else "-"


# Tip kisaltmasi: indirme ilerlemesini bildiren fonksiyon
ProgressHook = Callable[[dict], None]


# ---------------------------------------------------------------------------
# 1) ARAMA
# ---------------------------------------------------------------------------
def search(query: str, limit: int = config.SEARCH_LIMIT) -> list[SearchResult]:
    """YouTube'da `query` icin arama yapar ve en fazla `limit` sonuc dondurur.

    Hizli olmasi icin 'extract_flat' kullanir: her sonucu tam tek tek cozmek
    yerine sadece liste bilgisini (baslik, sure, kanal, id) ceker.
    """
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,      # hizli liste cekme
        "default_search": "ytsearch",
        "skip_download": True,
    }

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)

    results: list[SearchResult] = []
    for entry in (info or {}).get("entries", []) or []:
        if not entry:
            continue
        vid = entry.get("id", "")
        results.append(
            SearchResult(
                video_id=vid,
                title=entry.get("title") or "(baslik yok)",
                uploader=entry.get("uploader") or entry.get("channel") or "",
                duration=int(entry.get("duration") or 0),
                url=entry.get("url") or f"https://www.youtube.com/watch?v={vid}",
                thumbnail=entry.get("thumbnail"),
            )
        )
    return results


# ---------------------------------------------------------------------------
# 2) INDIRME
# ---------------------------------------------------------------------------
def _download_opts(progress_hook: Optional[ProgressHook]) -> dict:
    """Indirme icin ortak yt-dlp ayarlarini hazirlar (mp3 + kapak + metadata)."""
    config.MUSIC_DIR.mkdir(parents=True, exist_ok=True)

    # Dosya adi sablonu: "<baslik> [<id>].<uzanti>" -> ayni isimde cakismayi onler
    outtmpl = str(config.MUSIC_DIR / "%(title)s [%(id)s].%(ext)s")

    opts: dict = {
        "format": "bestaudio/best",
        "outtmpl": outtmpl,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,        # link bir listeye aitse bile tek sarki indir
        "writethumbnail": True,    # kapak resmini gecici olarak indir (gomulecek)
        "postprocessors": [
            # 1) Sesi mp3'e cevir (ffmpeg)
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": config.AUDIO_FORMAT,
                "preferredquality": config.AUDIO_QUALITY,
            },
            # 2) Sarki adi / sanatci gibi etiketleri yaz (ffmpeg)
            {"key": "FFmpegMetadata", "add_metadata": True},
            # 3) Kapagi mp3 icine gom (ffmpeg) -- TikTok/YouTube kapagi calisir
            {"key": "EmbedThumbnail", "already_have_thumbnail": False},
        ],
    }

    # ffmpeg'i PATH'te bulamazsa winget konumundan bulup yt-dlp'ye soyle
    ffmpeg_dir = config.find_ffmpeg_dir()
    if ffmpeg_dir:
        opts["ffmpeg_location"] = ffmpeg_dir

    if progress_hook:
        opts["progress_hooks"] = [progress_hook]

    return opts


def download_from_url(
    url: str,
    progress_hook: Optional[ProgressHook] = None,
) -> DownloadedTrack:
    """Herhangi bir destekli linki (TikTok, YouTube, ...) mp3 olarak indirir.

    yt-dlp'nin destekledigi tum siteler calisir. Kapak + metadata gomulur.
    Arama akisi (download) da bu fonksiyonu kullanir.
    """
    opts = _download_opts(progress_hook)

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        # Link coklu icerik (oynatma listesi) cozerse ilk ogeyi al
        if info and (info.get("_type") == "playlist" or info.get("entries")):
            entries = [e for e in (info.get("entries") or []) if e]
            if entries:
                info = entries[0]
        filepath = _resolve_output_path(ydl, info)

    return DownloadedTrack(
        title=info.get("title") or info.get("track") or "Bilinmeyen",
        artist=(
            info.get("artist")
            or info.get("creator")
            or info.get("uploader")
            or info.get("channel")
            or ""
        ),
        duration=int(info.get("duration") or 0),
        filepath=filepath,
        source_url=url,
    )


def download(
    result: SearchResult,
    progress_hook: Optional[ProgressHook] = None,
) -> DownloadedTrack:
    """Bir arama sonucunu mp3 olarak indirir (kapak + metadata gomulu).

    Asil isi download_from_url yapar; burada arama sonucundaki bilgilerle
    eksik kalan alanlari tamamliyoruz.
    """
    track = download_from_url(result.url, progress_hook)
    if not track.title or track.title == "Bilinmeyen":
        track.title = result.title
    if not track.artist:
        track.artist = result.uploader
    if not track.duration:
        track.duration = result.duration
    return track


# ---------------------------------------------------------------------------
# 3) VIDEO INDIRME (mp4, kalite kaybi olmadan)
# ---------------------------------------------------------------------------
def _video_opts(
    progress_hook: Optional[ProgressHook],
    postprocessor_hook: Optional[ProgressHook] = None,
) -> dict:
    """Video indirme icin yt-dlp ayarlari (en iyi kalite -> mp4 kapsayici).

    Kalite kaybi YOK: goruntu ve ses ayri ayri en iyi halleriyle indirilir,
    ffmpeg bunlari yalnizca BIRLESTIRIR/kapsayici degistirir (stream copy).
    Yeniden kodlama yapilmaz.
    """
    config.VIDEO_DIR.mkdir(parents=True, exist_ok=True)

    outtmpl = str(config.VIDEO_DIR / "%(title)s [%(id)s].%(ext)s")

    opts: dict = {
        "format": config.VIDEO_FORMAT,           # bv*+ba/b -> en iyi goruntu + en iyi ses
        "merge_output_format": config.VIDEO_CONTAINER,   # birlesme mp4 kapsayicisinda
        "outtmpl": outtmpl,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,        # link bir listeye aitse bile tek video indir
        "writethumbnail": True,    # kapak (mp4 icine gomulecek)
        "postprocessors": [
            # Birlesme olmayan (tek dosya webm) durumlarda da mp4'e cevir.
            # Remux = stream copy -> yine kalite kaybi yok.
            {"key": "FFmpegVideoRemuxer", "preferedformat": config.VIDEO_CONTAINER},
            # Baslik/kanal gibi etiketleri dosyaya yaz
            {"key": "FFmpegMetadata", "add_metadata": True},
            # Kapagi videonun icine gom
            {"key": "EmbedThumbnail", "already_have_thumbnail": False},
        ],
    }

    ffmpeg_dir = config.find_ffmpeg_dir()
    if ffmpeg_dir:
        opts["ffmpeg_location"] = ffmpeg_dir

    if progress_hook:
        opts["progress_hooks"] = [progress_hook]
    # ffmpeg asamalari (birlestirme/remux/kapak) uzun surebilir -> ayri hook
    if postprocessor_hook:
        opts["postprocessor_hooks"] = [postprocessor_hook]

    return opts


def download_video_from_url(
    url: str,
    progress_hook: Optional[ProgressHook] = None,
    postprocessor_hook: Optional[ProgressHook] = None,
) -> DownloadedVideo:
    """Bir linki VIDEO olarak (mp4) `video/` klasorune indirir.

    En yuksek kaliteli goruntu + ses secilir ve ffmpeg ile birlestirilir;
    yeniden kodlama yapilmadigi icin kalite kaybi olmaz. Cok nadiren bir kodek
    mp4 kapsayicisina remux edilemezse dosya .mkv/.webm olarak kalir --
    donen `ext` alani gercek uzantiyi soyler.

    Muzik kutuphanesine EKLENMEZ (calici yalnizca ses calar).
    """
    opts = _video_opts(progress_hook, postprocessor_hook)

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if info and (info.get("_type") == "playlist" or info.get("entries")):
            entries = [e for e in (info.get("entries") or []) if e]
            if entries:
                info = entries[0]
        filepath = _resolve_video_path(ydl, info)

    return DownloadedVideo(
        title=info.get("title") or "Bilinmeyen",
        uploader=(info.get("uploader") or info.get("channel") or ""),
        duration=int(info.get("duration") or 0),
        filepath=filepath,
        source_url=url,
        width=int(info.get("width") or 0),
        height=int(info.get("height") or 0),
        ext=Path(filepath).suffix.lstrip("."),
    )


def _resolve_video_path(ydl: "yt_dlp.YoutubeDL", info: dict) -> str:
    """Birlestirme + remux sonrasi olusan kesin video yolunu bulur."""
    # En guvenilir yol: yt-dlp'nin bildirdigi son dosya yolu
    for req in info.get("requested_downloads") or []:
        fp = req.get("filepath")
        if fp:
            return str(Path(fp))

    # Yedek yol: beklenen mp4 adi; yoksa ayni govdeye sahip baska uzantiyi ara
    base = Path(ydl.prepare_filename(info))
    guess = base.with_suffix(f".{config.VIDEO_CONTAINER}")
    if guess.exists():
        return str(guess)
    for cand in base.parent.glob(base.stem + ".*"):
        if cand.suffix.lower() not in (".jpg", ".png", ".webp", ".part"):
            return str(cand)
    return str(guess)


def download_preview(url: str, seconds: int = 6) -> Optional[str]:
    """Bir linkin SADECE ilk `seconds` saniyesini geçici bir mp3 olarak indirir.

    İndirmeden önce "doğru şarkı mı?" diye dinlemek için (önizleme). Kütüphaneye
    eklenmez. yt-dlp `download_ranges` ile yalnız ilk bölümü çeker → çok hızlı.

    Her önizlemede BENZERSIZ ad kullanılır: önceki klip çalıcı tarafından açık (kilitli)
    tutulduğundan üzerine yazılamaz; benzersiz adla kilit çakışması olmaz. Eski (kilitsiz)
    klipler en iyi çabayla temizlenir.
    """
    import uuid

    from yt_dlp.utils import download_range_func

    pdir = config.DATA_DIR / "preview"
    pdir.mkdir(parents=True, exist_ok=True)
    for old in pdir.glob("clip*"):  # serbest olan eski klipleri sil (kilitliyse atla)
        try:
            old.unlink()
        except Exception:  # noqa: BLE001
            pass

    base = pdir / f"clip_{uuid.uuid4().hex[:8]}"
    opts = {
        "format": "bestaudio/best",
        "outtmpl": str(base) + ".%(ext)s",
        "download_ranges": download_range_func(None, [(0, seconds)]),
        "force_keyframes_at_cuts": True,
        "quiet": True,
        "no_warnings": True,
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "128"}
        ],
    }
    ff = config.find_ffmpeg_dir()
    if ff:
        opts["ffmpeg_location"] = ff

    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])

    mp3 = Path(str(base) + ".mp3")
    return str(mp3) if mp3.exists() else None


def _resolve_output_path(ydl: "yt_dlp.YoutubeDL", info: dict) -> str:
    """Indirme + donusturme sonrasi olusan kesin mp3 yolunu bulur."""
    # En guvenilir yol: yt-dlp'nin bildirdigi son dosya yolu
    for req in info.get("requested_downloads") or []:
        fp = req.get("filepath")
        if fp:
            return str(Path(fp))
    # Yedek yol: orijinal adi al, uzantiyi .mp3 yap
    base = ydl.prepare_filename(info)
    return str(Path(base).with_suffix(f".{config.AUDIO_FORMAT}"))


# ===========================================================================
# Terminal testi (manuel kullanim) -- arayuz olmadan deneme yapmak icin
# ===========================================================================
def _print_results(results: list[SearchResult]) -> None:
    if not results:
        print("Hic sonuc bulunamadi.")
        return
    print("\nSonuclar:")
    for i, r in enumerate(results, start=1):
        kanal = f"  [{r.uploader}]" if r.uploader else ""
        print(f"  {i:>2}. {r.title}{kanal}   {r.duration_str}")


def _terminal_progress(d: dict) -> None:
    """yt-dlp ilerlemesini tek satirda gosterir."""
    status = d.get("status")
    if status == "downloading":
        pct = (d.get("_percent_str") or "").strip()
        spd = (d.get("_speed_str") or "").strip()
        print(f"\r  indiriliyor... {pct}  {spd}        ", end="", flush=True)
    elif status == "finished":
        print("\r  ses indirildi, ffmpeg ile mp3'e ceviriliyor...           ")


def _verify_embedded(path: str) -> None:
    """Indirilen mp3'un icindeki etiket + kapagi okuyup ekrana yazar.

    Boylece 'metadata ve kapak gercekten gomuldu mu?' sorusunu, dosyaya
    sag tiklamadan, dogrudan terminalden teyit edebilirsin.
    """
    try:
        from mutagen.mp3 import MP3
    except Exception as e:  # mutagen yoksa testi atla
        print(f"  (etiket okunamadi: {e})")
        return

    try:
        audio = MP3(path)
        tags = audio.tags
        title = str(tags.get("TIT2")) if tags and tags.get("TIT2") else "-"
        artist = str(tags.get("TPE1")) if tags and tags.get("TPE1") else "-"
        has_cover = bool(tags) and any(k.startswith("APIC") for k in tags.keys())
        print("\n  --- mp3 icindeki bilgiler (dogrulama) ---")
        print(f"  Sarki adi (TIT2) : {title}")
        print(f"  Sanatci   (TPE1) : {artist}")
        print(f"  Kapak resmi      : {'VAR' if has_cover else 'YOK'}")
        print(f"  Sure             : {int(audio.info.length)} sn")
    except Exception as e:
        print(f"  (mp3 okunamadi: {e})")


def _cli() -> None:
    # Turkce karakterler terminalde duzgun gorunsun
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

    # "--video" bayragi: linki mp3 yerine mp4 olarak indir
    args = [a for a in sys.argv[1:] if a not in ("--video", "-v")]
    want_video = len(args) != len(sys.argv[1:])

    # Arama terimi veya link: komut satirindan ya da soruyla
    if args:
        query = " ".join(args)
    else:
        query = input("Aranacak sarki (veya link yapistir): ").strip()
    if not query:
        print("Bos giris. Cikiliyor.")
        return

    # --video ile link verildiyse: mp4 indir
    if want_video:
        if not (query.startswith("http://") or query.startswith("https://")):
            print("--video yalnizca link ile kullanilir (arama sonucu icin degil).")
            return
        print(f"\nVideo indiriliyor (en iyi kalite -> mp4):\n  {query}")
        try:
            video = download_video_from_url(query, progress_hook=_terminal_progress)
        except Exception as e:  # noqa: BLE001
            print(f"\nINDIRME HATASI: {e}")
            return
        print("\nBASARILI ✔")
        print(f"  Dosya       : {video.filepath}")
        print(f"  Baslik      : {video.title}")
        print(f"  Kanal       : {video.uploader}")
        print(f"  Cozunurluk  : {video.resolution_str}")
        print(f"  Uzanti      : {video.ext}")
        if video.ext.lower() != config.VIDEO_CONTAINER:
            print("  NOT: kodek mp4'e remux edilemedi, dosya bu uzantiyla birakildi.")
        return

    # Link mi? (TikTok / YouTube / ...) -> dogrudan indir, arama yapma
    if query.startswith("http://") or query.startswith("https://"):
        print(f"\nLink algilandi, dogrudan indiriliyor:\n  {query}")
        try:
            track = download_from_url(query, progress_hook=_terminal_progress)
        except Exception as e:
            print(f"\nINDIRME HATASI: {e}")
            return
        print("\nBASARILI ✔")
        print(f"  Dosya  : {track.filepath}")
        print(f"  Baslik : {track.title}")
        print(f"  Sanatci: {track.artist}")
        _verify_embedded(track.filepath)
        return

    print(f"\n'{query}' icin araniyor...")
    results = search(query)
    _print_results(results)
    if not results:
        return

    raw = input("\nIndirilecek numara (iptal icin Enter): ").strip()
    if not raw:
        print("Iptal edildi.")
        return
    if not raw.isdigit() or not (1 <= int(raw) <= len(results)):
        print("Gecersiz numara.")
        return

    secim = results[int(raw) - 1]
    print(f"\nSeciliyor: {secim.title}")
    try:
        track = download(secim, progress_hook=_terminal_progress)
    except Exception as e:
        print(f"\nINDIRME HATASI: {e}")
        return

    print("\nBASARILI ✔")
    print(f"  Dosya  : {track.filepath}")
    print(f"  Baslik : {track.title}")
    print(f"  Sanatci: {track.artist}")
    _verify_embedded(track.filepath)


if __name__ == "__main__":
    _cli()
