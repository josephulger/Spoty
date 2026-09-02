"""
Spoty - paylasilan bulut kutuphanesi (Supabase REST + Storage).

Ekstra bagimlilik eklememek icin urllib ile duz HTTP istekleri atar
(PostgREST tablo API'si + Storage API). Iki kisi de ayni Supabase projesine
baglandigi icin hicbir klasor senkronu/kurulumu gerekmez.

Sarkinin ses dosyasi bulutta ('spoty-music' kovasinda) durur; her bilgisayar
ilk calindiginda kendi music/ klasorune indirip yerel bir onbellek tutar
(ayni sarkiyi tekrar indirmemek icin).
"""
from __future__ import annotations

import json
import mimetypes
import re
import shutil
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from spoty import config

_REST = f"{config.SUPABASE_URL}/rest/v1"
_STORAGE = f"{config.SUPABASE_URL}/storage/v1/object"
_HEADERS = {
    "apikey": config.SUPABASE_ANON_KEY,
    "Authorization": f"Bearer {config.SUPABASE_ANON_KEY}",
}


class CloudError(RuntimeError):
    pass


def _request(method: str, url: str, data: Optional[bytes] = None, headers: Optional[dict] = None) -> bytes:
    req = urllib.request.Request(url, data=data, method=method, headers={**_HEADERS, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")
        raise CloudError(f"{method} {url} -> {e.code}: {body}") from e
    except urllib.error.URLError as e:
        raise CloudError(f"İnternete ulaşılamadı: {e.reason}") from e


def _rest_json(method: str, path: str, body: Optional[dict | list] = None, prefer: str = "") -> list | dict:
    headers = {"Content-Type": "application/json"}
    if prefer:
        headers["Prefer"] = prefer
    data = json.dumps(body).encode("utf-8") if body is not None else None
    out = _request(method, f"{_REST}/{path}", data=data, headers=headers)
    return json.loads(out) if out else ([] if method == "GET" else {})


# ---------------------------------------------------------------------------
# Veri tasiyicilar (spoty.core.library.Track/Playlist ile ayni sekilde
# kullanilabilsin diye ayni alan adlarini tasir)
# ---------------------------------------------------------------------------
@dataclass
class Track:
    id: int
    title: str
    artist: str
    duration: int
    storage_path: str
    source_url: str
    added_at: str
    added_by: str = ""

    @property
    def filepath(self) -> str:
        """Yerel onbellek yolu (bu bilgisayarda henuz inmemis olabilir)."""
        return str(config.MUSIC_DIR / Path(self.storage_path).name)

    @property
    def duration_str(self) -> str:
        m, s = divmod(int(self.duration or 0), 60)
        return f"{m}:{s:02d}"


@dataclass
class Playlist:
    id: int
    name: str
    created_at: str
    track_count: int = 0


def _row_to_track(row: dict) -> Track:
    return Track(
        id=row["id"], title=row["title"], artist=row.get("artist") or "",
        duration=row.get("duration") or 0, storage_path=row["storage_path"],
        source_url=row.get("source_url") or "", added_at=row.get("added_at") or "",
        added_by=row.get("added_by") or "",
    )


# ---------------------------------------------------------------------------
# Sarkilar
# ---------------------------------------------------------------------------
def _safe_storage_name(title: str) -> str:
    """Depo anahtarlari icin guvenli, benzersiz bir dosya adi uretir.

    Supabase Storage bosluk/kose parantez gibi karakterlere izin vermiyor;
    baslik yerine ascii-guvenli bir slug + rastgele ek kullanilir.
    """
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", title or "sarki").strip("-").lower()[:60] or "sarki"
    return f"{slug}-{uuid.uuid4().hex[:8]}.mp3"


def publish_track(local_path: str, title: str, artist: str, duration: int, source_url: str) -> Track:
    """Yerelde inmis bir sarkiyi buluta yukler (dosya + metadata) ve Track doner."""
    p = Path(local_path)
    storage_path = _safe_storage_name(title)
    # Yerel onbellek adiyla (storage_path'in dosya adiyla) eslessin diye
    # indirilen dosyayi kanonik ada kopyalar -- boylece indiren kisi sarkiyi
    # ikinci kez indirmek zorunda kalmaz. Eski (yt-dlp'nin verdigi) ad silinir.
    canonical = config.MUSIC_DIR / storage_path
    if p != canonical:
        shutil.copy2(str(p), str(canonical))
        p.unlink(missing_ok=True)
        p = canonical
    upload_file(str(p), storage_path)
    rows = _rest_json(
        "POST", "tracks",
        body={
            "title": title, "artist": artist, "duration": int(duration),
            "storage_path": storage_path, "source_url": source_url,
            "added_by": config.get_user_name(),
        },
        prefer="return=representation",
    )
    return _row_to_track(rows[0])


def get_all_tracks() -> list[Track]:
    rows = _rest_json("GET", "tracks?select=*&order=added_at.desc")
    return [_row_to_track(r) for r in rows]


def get_track(track_id: int) -> Optional[Track]:
    rows = _rest_json("GET", f"tracks?select=*&id=eq.{int(track_id)}")
    return _row_to_track(rows[0]) if rows else None


def rename_track(track_id: int, title: str, artist: Optional[str] = None) -> None:
    body: dict = {"title": (title or "").strip()}
    if artist is not None:
        body["artist"] = artist.strip()
    _rest_json("PATCH", f"tracks?id=eq.{int(track_id)}", body=body)


def delete_track(track_id: int, delete_file: bool = False) -> None:
    t = get_track(track_id)
    _rest_json("DELETE", f"tracks?id=eq.{int(track_id)}")
    if delete_file and t:
        try:
            delete_file_storage(t.storage_path)
        except CloudError:
            pass  # bulutta silinemese de yerel kutuphaneden kalkmis olsun
        Path(t.filepath).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Calma listeleri
# ---------------------------------------------------------------------------
def get_playlists() -> list[Playlist]:
    rows = _rest_json("GET", "playlists?select=*,playlist_tracks(count)&order=created_at.asc")
    out = []
    for r in rows:
        count = 0
        pt = r.get("playlist_tracks") or []
        if pt and isinstance(pt, list):
            count = pt[0].get("count", 0)
        out.append(Playlist(id=r["id"], name=r["name"], created_at=r.get("created_at") or "", track_count=count))
    return out


def create_playlist(name: str) -> int:
    rows = _rest_json("POST", "playlists", body={"name": name}, prefer="return=representation")
    return int(rows[0]["id"])


def delete_playlist(pid: int) -> None:
    _rest_json("DELETE", f"playlists?id=eq.{int(pid)}")


def get_playlist_tracks(pid: int) -> list[Track]:
    rows = _rest_json(
        "GET",
        f"playlist_tracks?playlist_id=eq.{int(pid)}&select=position,tracks(*)&order=position.asc",
    )
    return [_row_to_track(r["tracks"]) for r in rows if r.get("tracks")]


def add_track_to_playlist(pid: int, tid: int) -> None:
    rows = _rest_json("GET", f"playlist_tracks?playlist_id=eq.{int(pid)}&select=position&order=position.desc&limit=1")
    next_pos = (rows[0]["position"] + 1) if rows else 0
    _rest_json(
        "POST", "playlist_tracks",
        body={"playlist_id": int(pid), "track_id": int(tid), "position": next_pos},
        prefer="resolution=merge-duplicates",
    )


def remove_track_from_playlist(pid: int, tid: int) -> None:
    _rest_json("DELETE", f"playlist_tracks?playlist_id=eq.{int(pid)}&track_id=eq.{int(tid)}")


def playlists_for_track(tid: int) -> list[int]:
    rows = _rest_json("GET", f"playlist_tracks?track_id=eq.{int(tid)}&select=playlist_id")
    return [r["playlist_id"] for r in rows]


def reorder_playlist(pid: int, ordered_ids: list[int]) -> None:
    for pos, tid in enumerate(ordered_ids):
        _rest_json("PATCH", f"playlist_tracks?playlist_id=eq.{int(pid)}&track_id=eq.{int(tid)}", body={"position": pos})


# ---------------------------------------------------------------------------
# Calma sayaclari
# ---------------------------------------------------------------------------
def record_play(track_id: int, user_name: str) -> None:
    user_name = (user_name or "").strip()
    if not user_name:
        return
    rows = _rest_json("GET", f"play_counts?track_id=eq.{int(track_id)}&user_name=eq.{quote(user_name)}&select=count")
    if rows:
        _rest_json(
            "PATCH", f"play_counts?track_id=eq.{int(track_id)}&user_name=eq.{quote(user_name)}",
            body={"count": int(rows[0]["count"]) + 1},
        )
    else:
        _rest_json("POST", "play_counts", body={"track_id": int(track_id), "user_name": user_name, "count": 1})


def get_play_counts() -> dict[int, dict[str, int]]:
    rows = _rest_json("GET", "play_counts?select=track_id,user_name,count")
    out: dict[int, dict[str, int]] = {}
    for r in rows:
        out.setdefault(r["track_id"], {})[r["user_name"]] = r["count"]
    return out


# ---------------------------------------------------------------------------
# Depolama (ses dosyalari)
# ---------------------------------------------------------------------------
def upload_file(local_path: str, storage_path: str) -> None:
    data = Path(local_path).read_bytes()
    ctype = mimetypes.guess_type(local_path)[0] or "application/octet-stream"
    url = f"{_STORAGE}/{config.SUPABASE_BUCKET}/{quote(storage_path)}"
    _request("POST", url, data=data, headers={"Content-Type": ctype, "x-upsert": "true"})


def download_file(storage_path: str, local_path: str) -> None:
    url = f"{_STORAGE}/{config.SUPABASE_BUCKET}/{quote(storage_path)}"
    data = _request("GET", url)
    Path(local_path).parent.mkdir(parents=True, exist_ok=True)
    Path(local_path).write_bytes(data)


def delete_file_storage(storage_path: str) -> None:
    url = f"{_STORAGE}/{config.SUPABASE_BUCKET}/{quote(storage_path)}"
    _request("DELETE", url)


def ensure_local(track: Track) -> bool:
    """Sarki bu bilgisayarda yoksa buluttan indirir. Basariliysa True doner."""
    local = Path(track.filepath)
    if local.exists():
        return True
    try:
        download_file(track.storage_path, str(local))
        return True
    except CloudError:
        return False
