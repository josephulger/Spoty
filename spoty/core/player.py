"""
Spoty - Calma cekirdegi (just_playback uzerine ince bir sarmalayici).

Arayuzden bagimsizdir. Tek bir sarkiyi calar ve kontrol eder:
  oynat / duraklat / devam / dur / sar / ses seviyesi
ve durum bilgisi verir:
  konum, sure, ilerleme, caliyor mu, duraklatildi mi, bitti mi.

Alttaki 'just_playback.Playback' su API'yi sunar (kurulu kaynaktan dogrulandi):
  load_file(path), play(), pause(), resume(), stop(), seek(sn), set_volume(0..1)
  ozellikler: playing, paused, active, curr_pos, duration, volume

Terminalden tek basina test:
    python -m spoty.core.player                # music/ icindeki ilk mp3'u calar
    python -m spoty.core.player "yol\\sarki.mp3"
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from just_playback import Playback

from spoty import config


class Player:
    """Tek sarkilik muzik calar. Arayuz bu sinifin metotlarini cagiracak."""

    def __init__(self, volume: float = 0.7) -> None:
        # Alttaki calici ilk yuklemede olusturulur (boylece bu modulu sadece
        # import etmek ses aygiti gerektirmez -> arayuz guvenle import edebilir).
        self._pb: Optional[Playback] = None
        self._volume: float = min(max(volume, 0.0), 1.0)
        self._current_path: Optional[str] = None
        self._started: bool = False   # play() cagrildi mi (dogal bitis tespiti icin)
        self._stopped: bool = False   # kullanici durdurdu mu

    # -- ic yardimci -------------------------------------------------------
    def _ensure(self) -> Playback:
        """Alttaki Playback nesnesini gerektiginde olusturur."""
        if self._pb is None:
            self._pb = Playback()          # ses aygiti yoksa burada hata firlatir
            self._pb.set_volume(self._volume)
        return self._pb

    # -- yukleme -----------------------------------------------------------
    def load(self, path: str | Path) -> None:
        """Calinacak ses dosyasini yukler (caliyorsa onceki durur)."""
        pb = self._ensure()
        pb.load_file(str(path))
        self._current_path = str(path)
        self._started = False
        self._stopped = False

    # -- temel kontroller --------------------------------------------------
    def play(self) -> None:
        """Yuklu sarkiyi bastan calar."""
        if self._pb is None or self._current_path is None:
            return
        self._pb.play()
        self._started = True
        self._stopped = False

    def pause(self) -> None:
        if self._pb is not None:
            self._pb.pause()

    def resume(self) -> None:
        if self._pb is not None:
            self._pb.resume()

    def stop(self) -> None:
        if self._pb is not None:
            self._pb.stop()
            self._stopped = True

    def toggle(self) -> None:
        """Arayuzdeki tek oynat/duraklat butonu icin akilli gecis."""
        if self._pb is None or self._current_path is None:
            return
        if self.is_playing:
            self.pause()
        elif self.is_paused:
            self.resume()
        else:
            # durmus / hic baslamamis / bitmis -> bastan cal
            self.play()

    # -- sarma (seek) ------------------------------------------------------
    def seek(self, seconds: float) -> None:
        """Belirtilen saniyeye atlar (0..sure araliginda kirpilir)."""
        if self._pb is not None:
            self._pb.seek(max(0.0, seconds))

    def seek_relative(self, delta: float) -> None:
        """Bulunulan konuma gore ileri/geri sarar (orn. +10, -10)."""
        if self._pb is not None:
            self._pb.seek(max(0.0, self.position + delta))

    # -- ses ---------------------------------------------------------------
    def set_volume(self, volume: float) -> None:
        """Ses seviyesi 0.0 - 1.0 arasi."""
        self._volume = min(max(volume, 0.0), 1.0)
        if self._pb is not None:
            self._pb.set_volume(self._volume)

    @property
    def volume(self) -> float:
        return self._pb.volume if self._pb is not None else self._volume

    # -- durum bilgisi -----------------------------------------------------
    @property
    def position(self) -> float:
        """Bulunulan konum (saniye). Yokken 0."""
        if self._pb is None:
            return 0.0
        return max(0.0, self._pb.curr_pos)

    @property
    def duration(self) -> float:
        """Sarkinin toplam suresi (saniye)."""
        return self._pb.duration if self._pb is not None else 0.0

    @property
    def progress(self) -> float:
        """Ilerleme orani 0.0 - 1.0 (arayuzdeki cubuk icin)."""
        d = self.duration
        return (self.position / d) if d > 0 else 0.0

    @property
    def is_playing(self) -> bool:
        return self._pb is not None and self._pb.playing

    @property
    def is_paused(self) -> bool:
        return self._pb is not None and self._pb.paused

    @property
    def is_loaded(self) -> bool:
        return self._current_path is not None

    @property
    def current_path(self) -> Optional[str]:
        return self._current_path

    def has_ended(self) -> bool:
        """Sarki dogal olarak bitti mi? (otomatik 'sonraki sarki' icin)

        True olmasi icin: calmaya baslamis olmali, kullanici durdurmamis olmali
        ve calici artik aktif olmamali (duraklatma aktif sayilir, bitti sayilmaz).
        """
        if self._pb is None or not self._started or self._stopped:
            return False
        return not self._pb.active


# ===========================================================================
# Terminal testi -- arayuz olmadan calici durum makinesini dogrular
# ===========================================================================
def _fmt(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"


def _first_music_file() -> Optional[str]:
    files = sorted(config.MUSIC_DIR.glob("*.mp3"))
    return str(files[0]) if files else None


def _cli() -> None:
    import time

    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

    path = sys.argv[1] if len(sys.argv) > 1 else _first_music_file()
    if not path:
        print("Calinacak mp3 bulunamadi. Once bir sarki indir (downloader).")
        return
    if not Path(path).exists():
        print(f"Dosya yok: {path}")
        return

    print(f"Dosya : {Path(path).name}")
    p = Player()
    try:
        p.load(path)
    except Exception as e:
        print(f"Yukleme/ses aygiti hatasi: {e}")
        return

    print(f"Sure  : {_fmt(p.duration)}")
    p.set_volume(0.6)

    print("\n[1] Calmaya basliyor (ses cikmali)...")
    p.play()
    time.sleep(2.0)
    pos1 = p.position
    print(f"    2 sn sonra konum: {pos1:.2f} sn | caliyor: {p.is_playing}")

    print("[2] Duraklatiliyor, 1 sn bekleniyor...")
    p.pause()
    time.sleep(1.0)
    pos2 = p.position
    print(f"    konum: {pos2:.2f} sn (degismemeli) | duraklatildi: {p.is_paused}")

    print("[3] Devam ediyor, 1.5 sn caliyor...")
    p.resume()
    time.sleep(1.5)
    pos3 = p.position
    print(f"    konum: {pos3:.2f} sn (artmali) | caliyor: {p.is_playing}")

    print("[4] 120. saniyeye sariliyor...")
    p.seek(120)
    time.sleep(0.5)
    print(f"    konum: {p.position:.2f} sn (~120 olmali)")

    print("[5] Ses %30'a dusuruluyor...")
    p.set_volume(0.3)
    print(f"    ses: {p.volume:.2f}")

    print("[6] Durduruluyor...")
    p.stop()
    print(f"    caliyor: {p.is_playing} | durdu (bitti sayilmaz): {p.has_ended()}")

    # Basit dogrulamalar
    print("\n--- Sonuc ---")
    ok_pause = abs(pos2 - pos1) < 0.4
    ok_resume = pos3 > pos2 + 0.4
    print(f"  Duraklatma calisti : {'EVET' if ok_pause else 'HAYIR'}")
    print(f"  Devam etme calisti : {'EVET' if ok_resume else 'HAYIR'}")
    print(f"  Genel              : {'TEST BASARILI' if (ok_pause and ok_resume) else 'KONTROL ET'}")


if __name__ == "__main__":
    _cli()
