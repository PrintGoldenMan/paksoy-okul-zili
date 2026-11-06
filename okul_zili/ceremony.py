"""Tören sesleri: «İstiklal Marşı» ve «Saygı Duruşu + İstiklal Marşı».

Ana ekrandaki düğmeyle başlatılır. Tören sürerken zamanı gelen ziller çalmaz; bekletilir ve tören
bitince (birkaç saniye ara verilerek) yalnızca en son bekleyen zil çalar (scheduler.py).
"""

import re

from . import library, sounds

ITEMS = {
    "istiklal": {"name": "İstiklal Marşı", "url": "https://youtu.be/s3GnMgOQs5k"},
    "saygi": {"name": "Saygı Duruşu + İstiklal Marşı", "url": "https://youtu.be/PMhKP8QyxFQ"},
}
KEYS = tuple(ITEMS)


def name(key: str) -> str:
    return ITEMS[key]["name"]


def item_cfg(cfg, key) -> dict:
    return (cfg.get("ceremony") or {}).get("items", {}).get(key) or {}


def sound_of(cfg, key) -> str:
    return item_cfg(cfg, key).get("sound") or ""


def url_of(cfg, key) -> str:
    return (item_cfg(cfg, key).get("url") or "").strip() or ITEMS[key]["url"]


def is_ready(cfg, key) -> bool:
    sid = sound_of(cfg, key)
    return bool(sid) and not sounds.is_silent(sid) and sounds.resolve(sid) is not None


def video_id(url: str):
    """YouTube bağlantısındaki video kimliği (youtu.be/…, watch?v=…, shorts/…)."""
    m = re.search(r"(?:youtu\.be/|[?&]v=|/shorts/|/embed/)([A-Za-z0-9_-]{11})", url or "")
    return m.group(1) if m else None


def find_in_library(url: str):
    """Aynı video daha önce tören sesi olarak (ses düzeyi değiştirilmeden) indirildiyse o kayıt."""
    vid = video_id(url)
    if not vid:
        return None
    for item in library.get_library().items():
        if item.get("normalized") is False and vid in (item.get("source") or ""):
            return item
    return None


def length_seconds(cfg, key):
    return sounds.length_seconds(sound_of(cfg, key))


def download(url: str, title: str, progress=None, cancel=None) -> dict:
    """Tören sesini indirip kütüphaneye ekler. Ses düzeyi eşitlenmez ve baştaki sessizlik kırpılmaz:
    saygı duruşunun sessiz dakikası olduğu gibi kalmalı."""
    from . import downloader
    return downloader.download(url, title, progress, cancel, normalize=False)
