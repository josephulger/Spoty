"""
Spoty - mp3 icine gomulu albüm kapagini okuma.

downloader, kapagi mp3 icine APIC (ID3) olarak gomuyor. Burada onu okuyup
PIL.Image olarak donduruyoruz; arayuz bunu CTkImage'e cevirip gosterir.
PIL dondurmek thread-guvenlidir (CTkImage olusturmak UI thread'inde yapilir).
"""
from __future__ import annotations

from io import BytesIO
from typing import Optional

from PIL import Image


def get_cover_image(filepath: str) -> Optional[Image.Image]:
    """mp3'teki gomulu kapagi PIL.Image olarak dondurur; yoksa None."""
    try:
        from mutagen.mp3 import MP3

        audio = MP3(filepath)
        tags = audio.tags
        if not tags:
            return None
        for key in tags.keys():
            if key.startswith("APIC"):  # gomulu resim cercevesi
                apic = tags.get(key)
                data = getattr(apic, "data", None)
                if data:
                    return Image.open(BytesIO(data)).convert("RGB")
    except Exception:
        return None
    return None
