"""Zil sesi kimliklerini dosyalara çevirir.

Ses kimlikleri:
  "lib:<kimlik>"  – kütüphanedeki bir ses (library.py)
  "none"          – zil sesi yok, yalnızca anons okunur
  ""              – henüz ses seçilmedi: zil sessiz kalmasın diye Windows uyarı sesi çalar
  "file:<yol>"    – eski sürümlerden kalan doğrudan dosya yolu
  "gomulu:<ad>"   – programla gelen (koda bayt olarak gömülü) ses: İstiklal Marşı vb. (gomulu_sesler.py)
"""

import base64
import hashlib
import logging
import threading
from pathlib import Path

from . import library, paths

log = logging.getLogger(__name__)

NO_SOUND = "none"
NO_SOUND_NAME = "(Zil sesi yok, yalnızca anons)"
UNSET_NAME = "(Ses seçilmedi – uyarı sesi çalar)"
BUILTIN_PREFIX = "gomulu:"
_builtin_lock = threading.Lock()


def builtin_sounds() -> dict:
    """Programla gelen sesler: {ad: bilgi}. Gömülü ses modülü yoksa (ör. kaynak koddan çalışırken) boş."""
    try:
        from . import gomulu_sesler
    except ImportError:
        return {}
    return gomulu_sesler.SESLER


def _builtin_info(sound_id: str):
    if sound_id and sound_id.startswith(BUILTIN_PREFIX):
        return builtin_sounds().get(sound_id[len(BUILTIN_PREFIX):])
    return None


def builtin_path(key: str):
    """Gömülü sesi ilk kullanımda veri klasörüne çıkarır (Opus) ve yolunu döndürür."""
    info = builtin_sounds().get(key)
    if not info:
        return None
    target = paths.sub_dir("gomulu") / f"{key}-{info['sha256'][:10]}.opus"
    with _builtin_lock:
        try:
            if target.exists() and target.stat().st_size == info["boyut"]:
                return target
            data = base64.b64decode("".join(info["veri"]))
            if hashlib.sha256(data).hexdigest() != info["sha256"]:
                log.error("Gömülü ses bozuk: %s", key)
                return None
            part = target.with_suffix(".part")
            part.write_bytes(data)
            part.replace(target)
            for old in target.parent.glob(f"{key}-*.opus"):   # önceki sürümlerin çıkardığı kopyalar
                if old != target:
                    old.unlink(missing_ok=True)
            log.info("Gömülü ses çıkarıldı: %s", target.name)
            return target
        except OSError as exc:
            log.error("Gömülü ses çıkarılamadı (%s): %s", key, exc)
            return None


def is_silent(sound_id: str) -> bool:
    return sound_id == NO_SOUND


def resolve(sound_id: str):
    """Çalınacak dosyanın yolu; dosya yoksa ya da ses seçilmediyse None."""
    if not sound_id or sound_id == NO_SOUND:
        return None
    if sound_id.startswith(library.PREFIX):
        return library.get_library().path(sound_id[len(library.PREFIX):])
    if sound_id.startswith(BUILTIN_PREFIX):
        return builtin_path(sound_id[len(BUILTIN_PREFIX):])
    if sound_id.startswith("file:"):
        p = Path(sound_id.split(":", 1)[1])
        return p if p.exists() else None
    return None


def is_missing(sound_id: str) -> bool:
    """Ses seçilmemiş ya da seçilen dosya artık yok (uyarı sesi çalacak)."""
    return not is_silent(sound_id) and resolve(sound_id) is None


def length_seconds(sound_id: str):
    info = _builtin_info(sound_id)
    if info:
        return info.get("sure")
    if sound_id and sound_id.startswith(library.PREFIX):
        item = library.get_library().get(sound_id[len(library.PREFIX):])
        return item.get("duration") if item else None
    return None


def part(sound_id: str):
    """Kütüphanede bu ses için seçilmiş «zilde çalınacak bölüm»: (başlangıç, bitiş ya da None)."""
    if sound_id and sound_id.startswith(library.PREFIX):
        item = library.get_library().get(sound_id[len(library.PREFIX):])
        if item:
            try:
                start = float(item.get("part_start") or 0.0)
                end = item.get("part_end")
                end = float(end) if end not in (None, "") else None
                if end is not None and end <= start:
                    end = None
                return max(0.0, start), end
            except (TypeError, ValueError):
                pass
    return 0.0, None


def display_name(sound_id: str) -> str:
    if sound_id == NO_SOUND:
        return NO_SOUND_NAME
    if sound_id and sound_id.startswith(BUILTIN_PREFIX):
        info = _builtin_info(sound_id)
        return f"{info['ad']} (programla gelen)" if info else "(Programla gelen ses bulunamadı)"
    if sound_id and sound_id.startswith(library.PREFIX):
        item = library.get_library().get(sound_id[len(library.PREFIX):])
        return item["title"] if item else "(Silinmiş ses – uyarı sesi çalar)"
    if sound_id and sound_id.startswith("file:"):
        return "Dosya: " + Path(sound_id.split(":", 1)[1]).name
    return UNSET_NAME
