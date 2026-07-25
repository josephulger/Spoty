"""
Spoty - kucuk ayar saklama (data/settings.json).

Uygulama kapanip acilinca hatirlanmasi gereken kucuk seyler:
ses seviyesi ve son calinan sarki.
"""
from __future__ import annotations

import json
from typing import Any

from spoty import config

_SETTINGS_PATH = config.DATA_DIR / "settings.json"

DEFAULTS: dict[str, Any] = {
    "volume": 0.7,
    "last_track_id": None,
}


def load() -> dict[str, Any]:
    """Ayarlari okur; dosya yoksa/bozuksa varsayilanlari verir."""
    try:
        with open(_SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {**DEFAULTS, **data}
    except Exception:
        return dict(DEFAULTS)


def save(settings: dict[str, Any]) -> None:
    """Ayarlari diske yazar (hata olursa sessizce gecer)."""
    try:
        with open(_SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
    except Exception:
        pass
