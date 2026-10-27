"""Ses kütüphanesi: internetten (yt-dlp) ya da bilgisayardan eklenen zil sesleri.

Sesler veri klasöründeki «kutuphane» klasöründe Opus (.opus) olarak, bilgileri ise
kutuphane.json dosyasında tutulur. Zil ayarlarında bir ses "lib:<kimlik>" olarak geçer.
"""

import json
import logging
import os
import re
import shutil
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
        self._items = []
        self._items = self._load()

    @staticmethod
    def _read(path: Path) -> list:
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
        return [i for i in data.get("items", []) if isinstance(i, dict) and i.get("id") and i.get("file")]

    def _load(self) -> list:
        if not self._index.exists() and not self._index.with_suffix(".bak").exists():
            items = []
        else:
            items = None
            for path in (self._index, self._index.with_suffix(".bak")):
                try:
                    items = self._read(path)
                    if path != self._index:
                        log.warning("Kütüphane listesi yedekten okundu")
                    break
                except (OSError, ValueError, AttributeError) as exc:
                    log.error("Kütüphane listesi okunamadı (%s): %s", path.name, exc)
            if items is None:
                # Liste bozuk ve yedek de yok: sesler klasördeki dosyalardan yeniden tanınır, böylece
                # zillerin seçtiği sesler (kimlik dosya adında saklı) kaybolmaz.
                try:
                    self._index.replace(self._index.with_suffix(".bozuk.json"))
                except OSError:
                    pass
                items = self._rebuild_from_files()
        self._items = items
        self._sweep_orphans()
        return items

    def _rebuild_from_files(self) -> list:
        items = []
        for f in sorted(library_dir().glob("*.opus")):
            if f.name.endswith(".part.opus"):
                continue
            m = re.match(r"^(.*)-([0-9a-f]{6})$", f.stem)
            # Dosya adında kimliğin yalnızca ilk 6 hanesi var; zil ayarlarındaki kimlikle eşleştirmek için
            # o 6 haneyle başlayan tam kimlik kullanılamayacağından kısa kimlik kullanılır.
            item_id = m.group(2) if m else uuid.uuid4().hex[:12]
            title = (m.group(1) if m else f.stem).replace("-", " ").strip() or "Adsız ses"
            items.append({"id": item_id, "file": f.name, "title": short_title(title), "full_title": title,
                          "duration": None, "source": "Kurtarıldı", "added": time.strftime("%Y-%m-%d %H:%M")})
        log.warning("Kütüphane listesi dosyalardan yeniden oluşturuldu (%d ses)", len(items))
        return items

    def _sweep_orphans(self):
        """Listede olmayan ses dosyalarını ve yarım kalmış dönüştürmeleri temizler
        (ör. çalarken silinen ve Windows'un o an silmeye izin vermediği dosyalar)."""
        known = {i["file"] for i in self._items}
        now = time.time()
        for f in library_dir().iterdir():
            if f.suffix != ".opus" or f.name in known:
                continue
            try:
                if now - f.stat().st_mtime > 600:   # yeni başlamış bir indirmenin dosyasına dokunma
                    f.unlink()
                    log.info("Artık ses dosyası silindi: %s", f.name)
            except OSError:
                pass

    def _save(self):
        tmp = self._index.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"version": 1, "items": self._items}, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        if self._index.exists():
            try:
                shutil.copyfile(self._index, self._index.with_suffix(".bak"))
            except OSError:
                pass
        tmp.replace(self._index)

    # -- okuma ---------------------------------------------------------------

    def items(self) -> list:
        with self._lock:
            return [dict(i) for i in self._items if (library_dir() / i["file"]).exists()]

    def get(self, item_id: str):
        with self._lock:
            item = next((i for i in self._items if i["id"] == item_id), None)
            if item is None:
                # Liste dosyalardan yeniden oluşturulduysa kimlikler 6 hanelidir (dosya adındaki kısım).
                item = next((i for i in self._items if len(i["id"]) == 6 and item_id.startswith(i["id"])), None)
            return dict(item) if item else None

    def path(self, item_id: str):
        item = self.get(item_id)
        if not item:
            return None
        p = library_dir() / item["file"]
        return p if p.exists() else None

    def total_bytes(self) -> int:
        total = 0
        for i in self.items():
            try:
                total += (library_dir() / i["file"]).stat().st_size
            except OSError:
                pass
        return total

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

    def set_part(self, item_id: str, start, end):
        """Zilde bu sesin hangi bölümünün çalınacağı (saniye; end None ise sonuna kadar)."""
        with self._lock:
            for i in self._items:
                if i["id"] == item_id:
                    i["part_start"] = round(float(start or 0.0), 2)
                    i["part_end"] = round(float(end), 2) if end is not None else None
            self._save()

    def remove(self, item_id: str):
        with self._lock:
            item = next((i for i in self._items if i["id"] == item_id), None)
            if not item:
                return
            self._items.remove(item)
            self._save()
        path = library_dir() / item["file"]
        log.info("Kütüphaneden silindi: %s", item["title"])

        def delete_file():
            # Ses o an çalıyorsa Windows dosyayı kilitler; birkaç kez denenir, olmazsa açılışta temizlenir.
            for _ in range(20):
                try:
                    path.unlink(missing_ok=True)
                    return
                except OSError:
                    time.sleep(0.5)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            threading.Thread(target=delete_file, daemon=True).start()


_library = None
_library_lock = threading.Lock()


def get_library() -> Library:
    global _library
    with _library_lock:
        if _library is None:
            _library = Library()
        return _library
