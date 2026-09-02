"""
Spoty - webview arayüzü için Python<->JS köprüsü (Api).

Çekirdek servisleri (downloader, player, library, metadata, settings) HTML/JS
arayüze açar. just_playback ile ses YİNE Python'da çalar; JS yalnız komut yollar
ve durumu (ilerleme, şimdi-çalan) gösterir. Tüm metotlar JS'ten
`window.pywebview.api.<metot>(...)` ile çağrılır ve Promise döner.
"""
from __future__ import annotations

import base64
import io
import os
import random
import sys
import threading
from pathlib import Path
from typing import Optional

from PIL import Image

from spoty import config
from spoty.core import cloud, downloader, metadata, settings, updater
from spoty.core.player import Player

# Çalma listesi karoları için renk paleti (theme.py ile aynı, ctk'siz)
_TILE_COLORS = ("#3a6ea5", "#b07a1e", "#7a4a86", "#c1574b", "#2f6f5e",
                "#8a3b5a", "#6b7f2a", "#4a8f6b", "#5b4bcf", "#3f7d8c")


def _tile(name: str) -> dict:
    name = name or "?"
    color = _TILE_COLORS[sum(name.encode("utf-8", "ignore")) % len(_TILE_COLORS)]
    return {"color": color, "letter": name[:1].upper()}


def _square(im: Image.Image) -> Image.Image:
    w, h = im.size
    if w == h:
        return im
    m = min(w, h)
    l, t = (w - m) // 2, (h - m) // 2
    return im.crop((l, t, l + m, t + m))


_cover_cache: dict = {}


def _cover_uri(filepath: str, size: int) -> Optional[str]:
    """Gömülü kapağı kare kırpıp `size` boyutunda JPEG data-URI olarak döner."""
    key = (filepath, size)
    if key in _cover_cache:
        return _cover_cache[key]
    uri = None
    try:
        pil = metadata.get_cover_image(filepath)
        if pil is not None:
            im = _square(pil).convert("RGB").resize((size, size), Image.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=82)
            uri = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:  # noqa: BLE001
        uri = None
    _cover_cache[key] = uri
    return uri


class Api:
    def __init__(self) -> None:
        self._settings = settings.load()
        vol = float(self._settings.get("volume", 0.7))
        self.player = Player(volume=vol)
        self._preview = Player(volume=vol)   # önizleme için ayrı çalıcı (ana çalmayı bozmaz)
        self._main_was_playing = False
        self._queue: list = []
        self._qi: int = -1
        self._source: str = ""
        self._shuffle: bool = False
        self._repeat: bool = False
        self._now_path: Optional[str] = None
        self._dl: dict = {}
        self._dl_reset()
        self._upd: dict = {"active": False, "phase": "", "pct": 0.0}
        self.window = None  # webmain.main() pencere olusturunca atar

    # ---- yardımcılar ----
    def _track_dict(self, t, plays: Optional[dict] = None) -> dict:
        return {
            "id": t.id, "title": t.title, "artist": t.artist or "",
            "duration": t.duration, "duration_str": t.duration_str,
            "cover": _cover_uri(t.filepath, 80),
            "playing": bool(self._now_path) and Path(t.filepath) == Path(self._now_path),
            "plays": (plays or {}).get(t.id, {}),
        }

    def _now_dict(self) -> Optional[dict]:
        if not (0 <= self._qi < len(self._queue)):
            return None
        t = self._queue[self._qi]
        return {
            "id": t.id, "title": t.title, "artist": t.artist or "",
            "cover": _cover_uri(t.filepath, 320), "source": self._source,
            "is_playing": self.player.is_playing,
        }

    # ---- başlangıç durumu ----
    def get_initial(self) -> dict:
        return {
            "library": self.get_library(),
            "playlists": self.get_playlists(),
            "volume": round(self.player.volume, 3),
            "now": self._now_dict(),
            "user_name": config.get_user_name(),
        }

    def get_user_name(self) -> str:
        return config.get_user_name()

    def set_user_name(self, name: str) -> str:
        name = (name or "").strip()
        config.set_user_name(name)
        return name

    def get_library(self) -> list:
        try:
            plays = cloud.get_play_counts()
            return [self._track_dict(t, plays) for t in cloud.get_all_tracks()]
        except cloud.CloudError:
            return []  # internet yok/erisim sorunu -- bos kutuphane goster, cokme

    def get_playlists(self) -> list:
        try:
            out = []
            for pl in cloud.get_playlists():
                out.append({"id": pl.id, "name": pl.name, "count": pl.track_count, **_tile(pl.name)})
            return out
        except cloud.CloudError:
            return []

    def get_playlist_tracks(self, pid: int) -> list:
        try:
            plays = cloud.get_play_counts()
            return [self._track_dict(t, plays) for t in cloud.get_playlist_tracks(int(pid))]
        except cloud.CloudError:
            return []

    # ---- çalma ----
    def play(self, track_id: int, queue_ids: list, source: str) -> dict:
        """queue_ids sırasına göre kuyruğu kurar, track_id'yi çalar."""
        tracks = [cloud.get_track(int(i)) for i in (queue_ids or [])]
        tracks = [t for t in tracks if t]
        idx = next((i for i, t in enumerate(tracks) if t.id == int(track_id)), -1)
        if idx < 0:
            return {}
        self._queue, self._qi, self._source = tracks, idx, source or ""
        return self._play_current()

    def _play_current(self) -> dict:
        if not (0 <= self._qi < len(self._queue)):
            return {}
        t = self._queue[self._qi]
        if not cloud.ensure_local(t):  # bu bilgisayarda yoksa buluttan indir
            return {}
        try:
            self.player.load(t.filepath)
            self.player.play()
        except Exception:  # noqa: BLE001
            return {}
        self._now_path = t.filepath
        try:
            cloud.record_play(t.id, config.get_user_name())
        except cloud.CloudError:
            pass  # sayac yazilamasa da calma devam etsin
        return self._now_dict() or {}

    def toggle(self) -> bool:
        self.player.toggle()
        return self.player.is_playing

    def next(self) -> Optional[dict]:
        if not self._queue:
            return None
        if self._shuffle and len(self._queue) > 1:
            nxt = self._qi
            while nxt == self._qi:
                nxt = random.randrange(len(self._queue))
            self._qi = nxt
        elif self._qi + 1 < len(self._queue):
            self._qi += 1
        elif self._repeat:
            self._qi = 0
        else:
            self.player.stop()
            self._now_path = None
            return None
        return self._play_current()

    def prev(self) -> Optional[dict]:
        if self.player.position > 3:
            self.player.seek(0)
            return self._now_dict()
        if self._qi > 0:
            self._qi -= 1
            return self._play_current()
        return self._now_dict()

    def seek(self, seconds: float) -> bool:
        self.player.seek(float(seconds))
        return True

    def set_volume(self, value: float) -> bool:
        self.player.set_volume(float(value))
        return True

    def set_shuffle(self, on: bool) -> bool:
        self._shuffle = bool(on)
        return self._shuffle

    def set_repeat(self, on: bool) -> bool:
        self._repeat = bool(on)
        return self._repeat

    # ---- arama / indirme (yalnız bu kısım internet ister) ----
    def _source_of(self, url: str) -> str:
        u = (url or "").lower()
        if "tiktok" in u:
            return "TikTok"
        if "youtu" in u:
            return "YouTube"
        return "Web"

    def search(self, query: str) -> dict:
        try:
            results = downloader.search(query)
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}
        return {"results": [
            {"title": r.title, "uploader": r.uploader, "duration_str": r.duration_str,
             "url": r.url, "source": self._source_of(r.url)}
            for r in results
        ]}

    def download(self, url: str) -> dict:
        """Bir linki (veya arama sonucu url'ini) indirir, buluta yukleyip kütüphaneye ekler."""
        try:
            track = downloader.download_from_url(url)
            cloud.publish_track(track.filepath, track.title, track.artist, track.duration, track.source_url)
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}
        return {"ok": True, "title": getattr(track, "title", "")}

    # ---- video indirme ilerlemesi ----
    # yt-dlp hook'ları indirmeyi yürüten ayrı thread'den çağrılır; burada yalnızca
    # küçük bir sözlük güncellenir, JS `download_progress()` ile ~500ms'de bir yoklar.
    def _dl_reset(self) -> None:
        self._dl = {"active": False, "url": "", "phase": "", "pct": 0.0,
                    "speed": "", "eta": "", "part": 0}

    def _dl_hook(self, d: dict) -> None:
        """İndirme ilerlemesi. `bv*+ba` iki ayrı akış indirir → hook iki tur döner."""
        st = d.get("status")
        if st == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes") or 0
            self._dl["phase"] = "indiriliyor"
            self._dl["pct"] = round(done * 100.0 / total, 1) if total else 0.0
            self._dl["speed"] = (d.get("_speed_str") or "").strip()
            self._dl["eta"] = (d.get("_eta_str") or "").strip()
        elif st == "finished":
            self._dl["part"] = int(self._dl.get("part", 0)) + 1
            self._dl["pct"] = 100.0
            self._dl["phase"] = "işleniyor"

    def _pp_hook(self, d: dict) -> None:
        """ffmpeg aşaması (büyük dosyada indirmeden uzun sürebilir)."""
        if d.get("status") != "started":
            return
        self._dl["phase"] = {
            "Merger": "görüntü ve ses birleştiriliyor",
            "FFmpegVideoRemuxer": "mp4'e dönüştürülüyor",
            "FFmpegMetadata": "etiketler yazılıyor",
            "EmbedThumbnail": "kapak gömülüyor",
        }.get(d.get("postprocessor") or "", "işleniyor")

    def download_progress(self) -> dict:
        """JS'in yokladığı anlık indirme durumu (kopya döner)."""
        return dict(self._dl)

    def download_video(self, url: str) -> dict:
        """Bir linki mp4 olarak `video/` klasörüne indirir (kalite kaybı yok).

        Müzik kütüphanesine EKLENMEZ — çalıcı yalnızca ses çalar.
        """
        self._dl_reset()
        self._dl["active"] = True
        self._dl["url"] = url
        self._dl["phase"] = "başlıyor"
        try:
            video = downloader.download_video_from_url(
                url, progress_hook=self._dl_hook, postprocessor_hook=self._pp_hook
            )
        except Exception as e:  # noqa: BLE001
            self._dl["active"] = False
            return {"error": str(e)}
        finally:
            self._dl["active"] = False
        return {
            "ok": True,
            "title": video.title,
            "resolution": video.resolution_str,
            "ext": video.ext,
            # mp4'e remux edilemediyse arayüz kullanıcıyı uyarabilsin
            "not_mp4": video.ext.lower() != config.VIDEO_CONTAINER,
            "folder": str(config.VIDEO_DIR),
        }

    def open_video_folder(self) -> bool:
        """İnen videoların klasörünü Windows Gezgini'nde açar."""
        try:
            os.startfile(str(config.VIDEO_DIR))  # noqa: S606  (Windows'a özgü)
        except Exception:  # noqa: BLE001
            return False
        return True

    def preview(self, url: str) -> dict:
        """İndirmeden önce şarkının ilk ~6 saniyesini çalar (ayrı çalıcıyla)."""
        try:
            path = downloader.download_preview(url, seconds=6)
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}
        if not path:
            return {"error": "Önizleme alınamadı"}
        # ana çalma üst üste binmesin diye duraklat (bitince sürdürülür)
        self._main_was_playing = self.player.is_playing
        if self.player.is_playing:
            self.player.pause()
        try:
            self._preview.set_volume(self.player.volume)
            self._preview.load(path)
            self._preview.play()
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}
        return {"ok": True, "dur": round(self._preview.duration or 6, 1)}

    def stop_preview(self) -> bool:
        try:
            self._preview.stop()
        except Exception:  # noqa: BLE001
            pass
        if self._main_was_playing:
            self.player.resume()
            self._main_was_playing = False
        return True

    # ---- çalma listesi / şarkı düzenleme ----
    def create_playlist(self, name: str) -> int:
        name = (name or "").strip()
        return cloud.create_playlist(name) if name else 0

    def delete_playlist(self, pid: int) -> bool:
        cloud.delete_playlist(int(pid))
        return True

    def add_to_playlist(self, pid: int, tid: int) -> bool:
        cloud.add_track_to_playlist(int(pid), int(tid))
        return True

    def remove_from_playlist(self, pid: int, tid: int) -> bool:
        cloud.remove_track_from_playlist(int(pid), int(tid))
        return True

    def playlists_for_track(self, tid: int) -> list:
        return list(cloud.playlists_for_track(int(tid)))

    def rename_track(self, tid: int, title: str, artist: str) -> dict:
        cloud.rename_track(int(tid), title, artist)
        for t in self._queue:  # kuyruktaki gösterimi de tazele
            if t.id == int(tid):
                t.title = (title or "").strip()
                if artist is not None:
                    t.artist = (artist or "").strip()
        return {"now": self._now_dict()}

    def delete_track(self, tid: int) -> dict:
        t = cloud.get_track(int(tid))
        cleared = False
        if t and self._now_path and Path(t.filepath) == Path(self._now_path):
            try:
                self.player.stop()
            except Exception:  # noqa: BLE001
                pass
            self._now_path = None
            self._qi = -1
            cleared = True
        cloud.delete_track(int(tid), delete_file=True)
        return {"cleared": cleared}

    def reorder_playlist(self, pid: int, ordered_ids: list) -> bool:
        cloud.reorder_playlist(int(pid), [int(i) for i in ordered_ids])
        return True

    def progress(self) -> dict:
        """JS ~300ms'de bir çağırır: konum/süre + doğal bitişte sonrakine geçer."""
        # önizleme klibi doğal bittiyse durdur + ana çalmayı sürdür
        if self._preview.is_loaded and self._preview.has_ended():
            self._preview.stop()
            if self._main_was_playing:
                self.player.resume()
                self._main_was_playing = False
        advanced = None
        if self.player.is_loaded and self.player.has_ended():
            advanced = self.next()
        return {
            "pos": self.player.position, "dur": self.player.duration,
            "playing": self.player.is_playing, "advanced": advanced,
        }

    # ---- paylasilan kutuphane (bulut) ----
    def restart_app(self) -> bool:
        """Uygulamayi kapatip aynisini tekrar baslatir (klasor degisikligi sonrasi)."""
        if not getattr(sys, "frozen", False):
            return False
        try:
            os.startfile(sys.executable)  # noqa: S606  (Windows'a ozgu)
        except Exception:  # noqa: BLE001
            return False
        os._exit(0)

    # ---- guncelleme ----
    def check_update(self) -> dict:
        """Yeni surum var mi diye GitHub Releases'e bakar (yalnizca paketli exe'de)."""
        if not getattr(sys, "frozen", False):
            return {}
        info = updater.check_latest()
        return info if info.get("available") else {}

    def start_update(self, url: str) -> bool:
        """Guncellemeyi indirip kurar; bitince uygulama kendini yeniden baslatir."""
        if self._upd["active"]:
            return False
        self._upd = {"active": True, "phase": "başlıyor", "pct": 0.0}

        def on_progress(phase: str, pct: float) -> None:
            self._upd = {"active": True, "phase": phase, "pct": pct}

        def run() -> None:
            try:
                updater.start_update(url, on_progress=on_progress)
            except Exception as e:  # noqa: BLE001
                self._upd = {"active": False, "phase": "hata", "pct": 0.0, "error": str(e)}

        threading.Thread(target=run, daemon=True).start()
        return True

    def update_progress(self) -> dict:
        return dict(self._upd)

    # ---- kapanış ----
    def save_state(self) -> bool:
        try:
            self._settings["volume"] = round(self.player.volume, 3)
            if 0 <= self._qi < len(self._queue):
                self._settings["last_track_id"] = self._queue[self._qi].id
            settings.save(self._settings)
            self.player.stop()
        except Exception:  # noqa: BLE001
            pass
        return True
