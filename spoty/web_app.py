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
from pathlib import Path
from typing import Optional

from PIL import Image

from spoty import config
from spoty.core import downloader, library, metadata, settings
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

    # ---- yardımcılar ----
    def _track_dict(self, t) -> dict:
        return {
            "id": t.id, "title": t.title, "artist": t.artist or "",
            "duration": t.duration, "duration_str": t.duration_str,
            "cover": _cover_uri(t.filepath, 80),
            "playing": bool(self._now_path) and Path(t.filepath) == Path(self._now_path),
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
        }

    def get_library(self) -> list:
        return [self._track_dict(t) for t in library.get_all_tracks()]

    def get_playlists(self) -> list:
        out = []
        for pl in library.get_playlists():
            out.append({"id": pl.id, "name": pl.name, "count": pl.track_count, **_tile(pl.name)})
        return out

    def get_playlist_tracks(self, pid: int) -> list:
        return [self._track_dict(t) for t in library.get_playlist_tracks(int(pid))]

    # ---- çalma ----
    def play(self, track_id: int, queue_ids: list, source: str) -> dict:
        """queue_ids sırasına göre kuyruğu kurar, track_id'yi çalar."""
        tracks = [library.get_track(int(i)) for i in (queue_ids or [])]
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
        try:
            self.player.load(t.filepath)
            self.player.play()
        except Exception:  # noqa: BLE001
            return {}
        self._now_path = t.filepath
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
        """Bir linki (veya arama sonucu url'ini) indirir, kütüphaneye ekler."""
        try:
            track = downloader.download_from_url(url)
            library.add_track(track)
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}
        return {"ok": True, "title": getattr(track, "title", "")}

    def download_video(self, url: str) -> dict:
        """Bir linki mp4 olarak `video/` klasörüne indirir (kalite kaybı yok).

        Müzik kütüphanesine EKLENMEZ — çalıcı yalnızca ses çalar.
        """
        try:
            video = downloader.download_video_from_url(url)
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}
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
        return library.create_playlist(name) if name else 0

    def delete_playlist(self, pid: int) -> bool:
        library.delete_playlist(int(pid))
        return True

    def add_to_playlist(self, pid: int, tid: int) -> bool:
        library.add_track_to_playlist(int(pid), int(tid))
        return True

    def remove_from_playlist(self, pid: int, tid: int) -> bool:
        library.remove_track_from_playlist(int(pid), int(tid))
        return True

    def playlists_for_track(self, tid: int) -> list:
        return list(library.playlists_for_track(int(tid)))

    def rename_track(self, tid: int, title: str, artist: str) -> dict:
        library.rename_track(int(tid), title, artist)
        for t in self._queue:  # kuyruktaki gösterimi de tazele
            if t.id == int(tid):
                t.title = (title or "").strip()
                if artist is not None:
                    t.artist = (artist or "").strip()
        return {"now": self._now_dict()}

    def delete_track(self, tid: int) -> dict:
        t = library.get_track(int(tid))
        cleared = False
        if t and self._now_path and Path(t.filepath) == Path(self._now_path):
            try:
                self.player.stop()
            except Exception:  # noqa: BLE001
                pass
            self._now_path = None
            self._qi = -1
            cleared = True
        library.delete_track(int(tid), delete_file=True)
        return {"cleared": cleared}

    def reorder_playlist(self, pid: int, ordered_ids: list) -> bool:
        library.reorder_playlist(int(pid), [int(i) for i in ordered_ids])
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
