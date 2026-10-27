"""Ses kütüphanesi: internetten (yt-dlp) ya da bilgisayardan eklenen zil sesleri.

Sesler veri klasöründeki «kutuphane» klasöründe Opus (.opus) olarak, bilgileri ise
kutuphane.json dosyasında tutulur. Zil ayarlarında bir ses "lib:<kimlik>" olarak geçer.
"""

import json
import logging
import re
import threading
import time
import unicodedata
import uuid
from pathlib import Path

from . import paths

log = logging.getLogger(__name__)

PREFIX = "lib:"
MAX_NAME_CHARS = 40       # dosya adının en fazla uzunluğu (kimlik eki hariç)
MAX_TITLE_CHARS = 70      # programda gösterilen adın en fazla uzunluğu

_TR_MAP = str.maketrans({"ç": "c", "Ç": "c", "ğ": "g", "Ğ": "g", "ı": "i", "I": "i", "İ": "i",
                         "ö": "o", "Ö": "o", "ş": "s", "Ş": "s", "ü": "u", "Ü": "u"})


def short_file_stem(title: str, item_id: str) -> str:
    """Uzun başlıkları kısa ve her sistemde güvenli bir dosya adına çevirir.

    «İstiklal Marşı (TBMM Resmî Kayıt) | 4K Remastered Official Video» ->
    «istiklal-marsi-tbmm-resmi-kayit-4k-3fa9c2»
    """
    # Harf/rakam dışındaki her şey (tire, «–», «|» vb.) ayraç sayılır; sözcükler birbirine yapışmasın.
    text = re.sub(r"[^\w]+", " ", (title or "").translate(_TR_MAP))
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()
    words = re.findall(r"[a-z0-9]+", text)
    stem = ""
    for w in words:
        candidate = f"{stem}-{w}" if stem else w
        if len(candidate) > MAX_NAME_CHARS:
            break
        stem = candidate
    if not stem and words:
        stem = words[0][:MAX_NAME_CHARS]
    return f"{stem or 'ses'}-{item_id[:6]}"


def short_title(title: str) -> str:
    title = re.sub(r"\s+", " ", (title or "").strip()) or "Adsız ses"
    return title if len(title) <= MAX_TITLE_CHARS else title[:MAX_TITLE_CHARS - 1].rstrip() + "…"


def library_dir() -> Path:
    return paths.sub_dir("kutuphane")


class Library:
    def __init__(self):
        self._lock = threading.RLock()
        self._index = library_dir() / "kutuphane.json"
        self._items = self._load()

    def _load(self) -> list:
        try:
            with open(self._index, encoding="utf-8-sig") as f:
                data = json.load(f)
            items = [i for i in data.get("items", []) if isinstance(i, dict) and i.get("id") and i.get("file")]
            return items
        except FileNotFoundError:
            return []
        except (OSError, ValueError, AttributeError) as exc:
            log.error("Kütüphane listesi okunamadı: %s", exc)
            return []

    def _save(self):
        tmp = self._index.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"version": 1, "items": self._items}, f, ensure_ascii=False, indent=2)
        tmp.replace(self._index)

    # -- okuma ---------------------------------------------------------------

    def items(self) -> list:
        with self._lock:
            return [dict(i) for i in self._items if (library_dir() / i["file"]).exists()]

    def get(self, item_id: str):
        with self._lock:
            return next((dict(i) for i in self._items if i["id"] == item_id), None)

    def path(self, item_id: str):
        item = self.get(item_id)
        if not item:
            return None
        p = library_dir() / item["file"]
        return p if p.exists() else None

    def total_bytes(self) -> int:
        return sum((library_dir() / i["file"]).stat().st_size for i in self.items())

    # -- yazma ---------------------------------------------------------------

    def new_target(self, title: str, ext: str = ".opus"):
        """Yeni bir ses için (kimlik, kısa dosya yolu) üretir."""
        item_id = uuid.uuid4().hex[:12]
        return item_id, library_dir() / (short_file_stem(title, item_id) + ext)

    def add(self, item_id: str, file_path: Path, title: str, duration=None, source: str = "") -> dict:
        item = {"id": item_id, "file": file_path.name, "title": short_title(title),
                "full_title": (title or "").strip(), "duration": round(float(duration), 1) if duration else None,
                "source": source, "added": time.strftime("%Y-%m-%d %H:%M")}
        with self._lock:
            self._items.append(item)
            self._save()
        log.info("Kütüphaneye eklendi: %s (%s)", item["title"], item["file"])
        return dict(item)

    def rename(self, item_id: str, title: str):
        with self._lock:
            for i in self._items:
                if i["id"] == item_id:
                    i["title"] = short_title(title)
            self._save()

    def remove(self, item_id: str):
        with self._lock:
            item = next((i for i in self._items if i["id"] == item_id), None)
            if not item:
                return
            self._items.remove(item)
            self._save()
        try:
            (library_dir() / item["file"]).unlink()
        except OSError:
            pass
        log.info("Kütüphaneden silindi: %s", item["title"])


_library = None
_library_lock = threading.Lock()


def get_library() -> Library:
    global _library
    with _library_lock:
        if _library is None:
            _library = Library()
        return _library
