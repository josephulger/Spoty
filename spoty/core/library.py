"""
Spoty - Kutuphane (SQLite veri katmani).

Indirilen sarkilari ve calma listelerini kalici olarak saklar (data/spoty.db).
Ag veya ses gerektirmez; tamamen yereldir.

Tablolar:
  tracks          : indirilen her sarki (dosya yolu benzersiz -> ciftlenmez)
  playlists       : calma listeleri (ad benzersiz)
  playlist_tracks : hangi sarki hangi listede (sira bilgisiyle)

Terminalden test:
    python -m spoty.core.library
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterator, Optional

from spoty import config

if TYPE_CHECKING:
    # Sadece tip ipucu icin; calisma aninda yt_dlp'yi import etmemek icin
    # (kutuphane modulu hafif kalsin).
    from spoty.core.downloader import DownloadedTrack


# ---------------------------------------------------------------------------
# Veri tasiyici siniflar
# ---------------------------------------------------------------------------
@dataclass
class Track:
    id: int
    title: str
    artist: str
    duration: int
    filepath: str
    source_url: str
    added_at: str

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


# ---------------------------------------------------------------------------
# Baglanti yonetimi
# ---------------------------------------------------------------------------
@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    """Veritabani baglantisi acar; cikista commit + close yapar."""
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row          # sutunlara isimle erisim
    conn.execute("PRAGMA foreign_keys = ON")  # CASCADE silme icin sart
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """Tablolari (yoksa) olusturur. Modul ilk import edildiginde cagrilir."""
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tracks (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                title      TEXT NOT NULL,
                artist     TEXT DEFAULT '',
                duration   INTEGER DEFAULT 0,
                filepath   TEXT NOT NULL UNIQUE,
                source_url TEXT DEFAULT '',
                added_at   TEXT DEFAULT (datetime('now','localtime'))
            );

            CREATE TABLE IF NOT EXISTS playlists (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT NOT NULL UNIQUE,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            );

            CREATE TABLE IF NOT EXISTS playlist_tracks (
                playlist_id INTEGER NOT NULL,
                track_id    INTEGER NOT NULL,
                position    INTEGER DEFAULT 0,
                PRIMARY KEY (playlist_id, track_id),
                FOREIGN KEY (playlist_id) REFERENCES playlists(id) ON DELETE CASCADE,
                FOREIGN KEY (track_id)    REFERENCES tracks(id)    ON DELETE CASCADE
            );

            -- Paylasilan kutuphanede kim hangi sarkiyi kac kere caldi.
            -- user_name bu bilgisayardaki kisinin adi (config.get_user_name()).
            CREATE TABLE IF NOT EXISTS play_counts (
                track_id  INTEGER NOT NULL,
                user_name TEXT NOT NULL,
                count     INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (track_id, user_name),
                FOREIGN KEY (track_id) REFERENCES tracks(id) ON DELETE CASCADE
            );
            """
        )


def _row_to_track(row: sqlite3.Row) -> Track:
    return Track(
        id=row["id"],
        title=row["title"],
        artist=row["artist"] or "",
        duration=row["duration"] or 0,
        filepath=row["filepath"],
        source_url=row["source_url"] or "",
        added_at=row["added_at"],
    )


# ---------------------------------------------------------------------------
# Sarki islemleri
# ---------------------------------------------------------------------------
def add_track(track: "DownloadedTrack") -> int:
    """Indirilen bir sarkiyi kaydeder; ayni dosya zaten varsa onun id'sini verir.

    `track` su alanlara sahip olmali: title, artist, duration, filepath, source_url
    (downloader.DownloadedTrack bunlari saglar).
    """
    with _connect() as conn:
        row = conn.execute(
            "SELECT id FROM tracks WHERE filepath = ?", (track.filepath,)
        ).fetchone()
        if row:
            return row["id"]  # zaten kayitli -> ciftleme

        cur = conn.execute(
            """INSERT INTO tracks (title, artist, duration, filepath, source_url)
               VALUES (?, ?, ?, ?, ?)""",
            (track.title, track.artist, track.duration, track.filepath, track.source_url),
        )
        return int(cur.lastrowid)


def record_play(track_id: int, user_name: str) -> None:
    """Bir sarki calindiginda cagrilir; o kisinin o sarki icin sayacini 1 artirir."""
    user_name = (user_name or "").strip()
    if not user_name:
        return
    with _connect() as conn:
        conn.execute(
            """INSERT INTO play_counts (track_id, user_name, count) VALUES (?, ?, 1)
               ON CONFLICT(track_id, user_name) DO UPDATE SET count = count + 1""",
            (track_id, user_name),
        )


def get_play_counts() -> dict[int, dict[str, int]]:
    """Tum sarkilar icin {track_id: {kisi_adi: sayi}} -- tek sorguda, N+1 yok."""
    with _connect() as conn:
        rows = conn.execute("SELECT track_id, user_name, count FROM play_counts").fetchall()
    out: dict[int, dict[str, int]] = {}
    for r in rows:
        out.setdefault(r["track_id"], {})[r["user_name"]] = r["count"]
    return out


def get_all_tracks() -> list[Track]:
    """Kutuphanedeki tum sarkilar (en yeni eklenen ustte)."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM tracks ORDER BY added_at DESC, id DESC"
        ).fetchall()
        return [_row_to_track(r) for r in rows]


def get_track(track_id: int) -> Optional[Track]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM tracks WHERE id = ?", (track_id,)).fetchone()
        return _row_to_track(row) if row else None


def rename_track(track_id: int, title: str, artist: Optional[str] = None) -> None:
    """Sarkinin gorunen adini (ve istege bagli sanatcisini) gunceller.

    Yalnizca veritabanindaki etiketi degistirir; dosya adi ve mp3 icindeki gomulu
    ID3 etiketi degismez (gorunum yeterli; ozellikle uzun TikTok basliklari icin).
    """
    title = (title or "").strip()
    if not title:
        return
    with _connect() as conn:
        if artist is None:
            conn.execute("UPDATE tracks SET title = ? WHERE id = ?", (title, track_id))
        else:
            conn.execute(
                "UPDATE tracks SET title = ?, artist = ? WHERE id = ?",
                (title, artist.strip(), track_id),
            )


def delete_track(track_id: int, delete_file: bool = False) -> None:
    """Sarkiyi kutuphaneden siler. delete_file=True ise diskten de siler.

    playlist_tracks kayitlari CASCADE ile otomatik temizlenir.
    """
    track = get_track(track_id)
    with _connect() as conn:
        conn.execute("DELETE FROM tracks WHERE id = ?", (track_id,))
    if delete_file and track:
        try:
            from pathlib import Path
            Path(track.filepath).unlink(missing_ok=True)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Calma listesi islemleri
# ---------------------------------------------------------------------------
def create_playlist(name: str) -> int:
    """Yeni calma listesi olusturur; ayni isim varsa onun id'sini verir."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT id FROM playlists WHERE name = ?", (name,)
        ).fetchone()
        if row:
            return row["id"]
        cur = conn.execute("INSERT INTO playlists (name) VALUES (?)", (name,))
        return int(cur.lastrowid)


def get_playlists() -> list[Playlist]:
    """Tum calma listeleri (icindeki sarki sayisiyla birlikte)."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT p.id, p.name, p.created_at,
                   COUNT(pt.track_id) AS track_count
            FROM playlists p
            LEFT JOIN playlist_tracks pt ON pt.playlist_id = p.id
            GROUP BY p.id
            ORDER BY p.created_at, p.id
            """
        ).fetchall()
        return [
            Playlist(
                id=r["id"],
                name=r["name"],
                created_at=r["created_at"],
                track_count=r["track_count"],
            )
            for r in rows
        ]


def delete_playlist(playlist_id: int) -> None:
    """Listeyi siler (icindeki baglantilar CASCADE ile temizlenir; sarkilar kalir)."""
    with _connect() as conn:
        conn.execute("DELETE FROM playlists WHERE id = ?", (playlist_id,))


def add_track_to_playlist(playlist_id: int, track_id: int) -> None:
    """Bir sarkiyi listenin sonuna ekler (zaten varsa bir sey yapmaz)."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT COALESCE(MAX(position), -1) + 1 AS next_pos FROM playlist_tracks WHERE playlist_id = ?",
            (playlist_id,),
        ).fetchone()
        next_pos = row["next_pos"]
        conn.execute(
            """INSERT OR IGNORE INTO playlist_tracks (playlist_id, track_id, position)
               VALUES (?, ?, ?)""",
            (playlist_id, track_id, next_pos),
        )


def remove_track_from_playlist(playlist_id: int, track_id: int) -> None:
    with _connect() as conn:
        conn.execute(
            "DELETE FROM playlist_tracks WHERE playlist_id = ? AND track_id = ?",
            (playlist_id, track_id),
        )


def reorder_playlist(playlist_id: int, ordered_track_ids: list[int]) -> None:
    """Listedeki sarkilarin sirasini verilen track_id sirasina gore yeniden numaralar.

    `ordered_track_ids` listedeki TUM sarkilari (yeni sirayla) icermeli; her birine
    0..n-1 araliginda yeni `position` atanir. Sürükle-bırak sonrasi cagrilir.
    """
    with _connect() as conn:
        for pos, tid in enumerate(ordered_track_ids):
            conn.execute(
                "UPDATE playlist_tracks SET position = ? WHERE playlist_id = ? AND track_id = ?",
                (pos, playlist_id, tid),
            )


def playlists_for_track(track_id: int) -> set[int]:
    """Bir şarkının halihazırda bulunduğu çalma listesi id'lerini döndürür."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT playlist_id FROM playlist_tracks WHERE track_id = ?", (track_id,)
        ).fetchall()
        return {r["playlist_id"] for r in rows}


def get_playlist_tracks(playlist_id: int) -> list[Track]:
    """Bir listedeki sarkilari sirayla dondurur."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT t.*
            FROM playlist_tracks pt
            JOIN tracks t ON t.id = pt.track_id
            WHERE pt.playlist_id = ?
            ORDER BY pt.position, pt.track_id
            """,
            (playlist_id,),
        ).fetchall()
        return [_row_to_track(r) for r in rows]


# Modul import edilir edilmez tablolarin hazir olmasini garanti et
init_db()


# ===========================================================================
# Terminal testi
# ===========================================================================
def _cli() -> None:
    import sys
    from types import SimpleNamespace

    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

    print(f"Veritabani: {config.DB_PATH}")
    init_db()

    # music/ icindeki ilk mp3'u, gomulu etiketlerini okuyarak kutuphaneye ekle
    mp3s = sorted(config.MUSIC_DIR.glob("*.mp3"))
    if not mp3s:
        print("music/ klasorunde mp3 yok. Once bir sarki indir.")
        return
    path = str(mp3s[0])

    title, artist, duration = path, "", 0
    try:
        from mutagen.mp3 import MP3
        audio = MP3(path)
        tags = audio.tags
        if tags:
            if tags.get("TIT2"):
                title = str(tags.get("TIT2"))
            if tags.get("TPE1"):
                artist = str(tags.get("TPE1"))
        duration = int(audio.info.length)
    except Exception as e:
        print(f"(etiket okunamadi, varsayilan kullanilacak: {e})")

    fake_track = SimpleNamespace(
        title=title, artist=artist, duration=duration,
        filepath=path, source_url="test",
    )

    print("\n[1] Sarki ekleniyor...")
    tid1 = add_track(fake_track)
    print(f"    eklendi -> id={tid1}  ({title} / {artist})")

    print("[2] Ayni sarki tekrar ekleniyor (ciftlenmemeli)...")
    tid2 = add_track(fake_track)
    print(f"    donen id={tid2}  ->  {'AYNI (dogru)' if tid1 == tid2 else 'FARKLI (HATA!)'}")

    print("[3] Calma listesi olusturuluyor: 'Favoriler'")
    pid = create_playlist("Favoriler")
    print(f"    liste id={pid}")

    print("[4] Sarki listeye ekleniyor...")
    add_track_to_playlist(pid, tid1)

    print("\n[5] Tum sarkilar:")
    for t in get_all_tracks():
        print(f"    #{t.id}  {t.title}  [{t.artist}]  {t.duration_str}")

    print("\n[6] Calma listeleri:")
    for pl in get_playlists():
        print(f"    #{pl.id}  {pl.name}  ({pl.track_count} sarki)")

    print(f"\n[7] 'Favoriler' icindekiler:")
    for t in get_playlist_tracks(pid):
        print(f"    {t.title}  [{t.artist}]  {t.duration_str}")

    print("\nTEST BASARILI")


if __name__ == "__main__":
    _cli()
