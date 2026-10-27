"""Değişen zil sesi: seçilen kütüphane seslerinden her gün / hafta / ay rastgele biri çalar.

Her zilin ayarında "rotation" bölümü bulunur:
  {"enabled": False, "period": "week", "pool": ["lib:…", …], "current": "lib:…", "key": "2026-W44"}
Yeni döneme girildiğinde, havuzdan bir önceki sesten FARKLI bir ses rastgele seçilir ve ayarlara
kaydedilir; böylece program yeniden başlasa da dönem boyunca aynı ses çalar.
"""

import datetime as dt
import random

from . import library, sounds

PERIODS = {"day": "Her gün", "week": "Her hafta", "month": "Her ay"}
PERIOD_THIS = {"day": "Bugünün", "week": "Bu haftanın", "month": "Bu ayın"}
DEFAULT = {"enabled": False, "period": "week", "pool": [], "current": "", "key": ""}


def period_key(period: str, date: dt.date) -> str:
    if period == "day":
        return date.isoformat()
    if period == "month":
        return f"{date.year}-{date.month:02d}"
    year, week, _ = date.isocalendar()   # haftalar pazartesi başlar
    return f"{year}-W{week:02d}"


def valid_pool(rot: dict) -> list:
    """Havuzdaki seslerden kütüphanede hâlâ bulunanlar (sırası korunur, tekrarsız)."""
    out = []
    for sid in rot.get("pool") or []:
        if sid not in out and sid.startswith(library.PREFIX) and sounds.resolve(sid) is not None:
            out.append(sid)
    return out


def pick(pool: list, exclude: str = "", rng=random) -> str:
    """Havuzdan rastgele bir ses; mümkünse exclude (şu anki ses) dışında."""
    if not pool:
        return ""
    choices = [s for s in pool if s != exclude] or pool
    return rng.choice(choices)


def is_active(bell: dict) -> bool:
    rot = bell.get("rotation") or {}
    return bool(rot.get("enabled")) and bool(valid_pool(rot))


def update(bell: dict, date: dt.date, force: bool = False, rng=random) -> bool:
    """Gerekirse bu dönemin sesini seçer. Bir şey değiştiyse True döndürür.

    force=True: dönem değişmese de yeni bir ses seçilir («Şimdi değiştir»)."""
    rot = bell.get("rotation")
    if not isinstance(rot, dict) or not rot.get("enabled"):
        return False
    pool = valid_pool(rot)
    if not pool:
        return False
    key = period_key(rot.get("period", "week"), date)
    current = rot.get("current", "")
    if not force and rot.get("key") == key and current in pool:
        return False
    rot["current"] = pick(pool, exclude=current, rng=rng)
    rot["key"] = key
    return True


def update_all(cfg: dict, date: dt.date = None, rng=random) -> bool:
    date = date or dt.date.today()
    changed = False
    for bell in cfg.get("bells", {}).values():
        changed |= update(bell, date, rng=rng)
    return changed


def effective_sound(bell: dict) -> str:
    """Zilin şu an çalacağı ses kimliği (değişen ses açıksa bu dönemin sesi)."""
    rot = bell.get("rotation") or {}
    if rot.get("enabled"):
        pool = valid_pool(rot)
        if rot.get("current") in pool:
            return rot["current"]
        if pool:
            return pool[0]   # henüz seçim yapılmadıysa (bir sonraki denetimde rastgele seçilir)
    return bell.get("sound", "")


def remove_from_pools(cfg: dict, sound_id: str) -> None:
    """Kütüphaneden silinen sesi tüm havuzlardan çıkarır."""
    for bell in cfg.get("bells", {}).values():
        rot = bell.get("rotation")
        if isinstance(rot, dict):
            rot["pool"] = [s for s in rot.get("pool") or [] if s != sound_id]
            if rot.get("current") == sound_id:
                rot["current"] = ""
