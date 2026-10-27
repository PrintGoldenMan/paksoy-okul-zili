"""Zil sesi kimliklerini dosyalara çevirir.

Ses kimlikleri:
  "lib:<kimlik>"  – kütüphanedeki bir ses (library.py)
  "none"          – zil sesi yok, yalnızca anons okunur
  ""              – henüz ses seçilmedi: zil sessiz kalmasın diye Windows uyarı sesi çalar
  "file:<yol>"    – eski sürümlerden kalan doğrudan dosya yolu
"""

from pathlib import Path

from . import library

NO_SOUND = "none"
NO_SOUND_NAME = "(Zil sesi yok, yalnızca anons)"
UNSET_NAME = "(Ses seçilmedi – uyarı sesi çalar)"


def is_silent(sound_id: str) -> bool:
    return sound_id == NO_SOUND


def resolve(sound_id: str):
    """Çalınacak dosyanın yolu; dosya yoksa ya da ses seçilmediyse None."""
    if not sound_id or sound_id == NO_SOUND:
        return None
    if sound_id.startswith(library.PREFIX):
        return library.get_library().path(sound_id[len(library.PREFIX):])
    if sound_id.startswith("file:"):
        p = Path(sound_id.split(":", 1)[1])
        return p if p.exists() else None
    return None


def is_missing(sound_id: str) -> bool:
    """Ses seçilmemiş ya da seçilen dosya artık yok (uyarı sesi çalacak)."""
    return not is_silent(sound_id) and resolve(sound_id) is None


def length_seconds(sound_id: str):
    if sound_id and sound_id.startswith(library.PREFIX):
        item = library.get_library().get(sound_id[len(library.PREFIX):])
        return item.get("duration") if item else None
    return None


def display_name(sound_id: str) -> str:
    if sound_id == NO_SOUND:
        return NO_SOUND_NAME
    if sound_id and sound_id.startswith(library.PREFIX):
        item = library.get_library().get(sound_id[len(library.PREFIX):])
        return item["title"] if item else "(Silinmiş ses – uyarı sesi çalar)"
    if sound_id and sound_id.startswith("file:"):
        return "Dosya: " + Path(sound_id.split(":", 1)[1]).name
    return UNSET_NAME
