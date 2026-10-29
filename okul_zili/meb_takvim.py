"""MEB çalışma takvimi: eğitim yılının tatilleri (tek tıkla «Tatiller» listesine eklenir).

Kaynak: Millî Eğitim Bakanlığı, «2026-2027 Eğitim Öğretim Yılı Takvimi Açıklandı»
(https://www.meb.gov.tr/2026-2027-egitim-ogretim-yili-takvimi-aciklandi/haber/41057/tr) ve
Diyanet takvimine göre dinî bayramlar. Yeni eğitim yılının takvimi açıklandığında buraya eklenir
ve programın güncellemesiyle okullara ulaşır.

"from": yarım günlük tatillerde zillerin susacağı saat (ör. 28 Ekim öğleden sonra).
"""

import datetime as dt
import json
import logging
import threading
import time
import urllib.request

from . import GITHUB_REPO, paths

log = logging.getLogger(__name__)

# Takvim internetten (GitHub deposundaki takvim/meb_takvim.json) haftada bir yenilenir; böylece yeni eğitim
# yılının takvimi programın yeni sürümü beklenmeden gelir. İnternet yoksa aşağıdaki yerleşik takvim kullanılır.
REMOTE_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}/HEAD/takvim/meb_takvim.json"
REFRESH_SECONDS = 7 * 24 * 3600

CALENDARS = {
    "2026-2027": {
        "first_day": "2026-09-14",
        "last_day": "2027-06-25",
        "holidays": [
            {"name": "Cumhuriyet Bayramı arifesi (öğleden sonra)", "start": "2026-10-28", "end": "2026-10-28",
             "from": "13:00"},
            {"name": "Cumhuriyet Bayramı", "start": "2026-10-29", "end": "2026-10-29"},
            {"name": "Birinci dönem ara tatili", "start": "2026-11-16", "end": "2026-11-20"},
            {"name": "Yılbaşı", "start": "2027-01-01", "end": "2027-01-01"},
            {"name": "Yarıyıl tatili", "start": "2027-01-25", "end": "2027-02-05"},
            {"name": "İkinci dönem ara tatili ve Ramazan Bayramı", "start": "2027-03-08", "end": "2027-03-12"},
            {"name": "Ulusal Egemenlik ve Çocuk Bayramı", "start": "2027-04-23", "end": "2027-04-23"},
            {"name": "Kurban Bayramı ve 19 Mayıs", "start": "2027-05-17", "end": "2027-05-19"},
            # Bir sonraki yılın açılış tarihi henüz belli değil; yeni takvim eklenince güncellenir.
            {"name": "Yaz tatili", "start": "2027-06-26", "end": "2027-08-31"},
        ],
    },
}


BUILTIN = CALENDARS


def _cache_file():
    return paths.data_dir() / "meb_takvim.json"


def _valid(data) -> bool:
    if not isinstance(data, dict) or not isinstance(data.get("calendars"), dict):
        return False
    for cal in data["calendars"].values():
        if not isinstance(cal, dict) or not isinstance(cal.get("holidays"), list):
            return False
        for h in cal["holidays"]:
            if not (isinstance(h, dict) and isinstance(h.get("start"), str) and isinstance(h.get("name"), str)):
                return False
    return True


def _load_cache() -> dict:
    try:
        with open(_cache_file(), encoding="utf-8") as f:
            data = json.load(f)
        return data["calendars"] if _valid(data) else {}
    except (OSError, ValueError, KeyError):
        return {}


def calendars() -> dict:
    """Yerleşik takvimler + internetten indirilmiş olanlar (indirilen, aynı yıl için önceliklidir)."""
    return {**BUILTIN, **_load_cache()}


def refresh(force=False) -> bool:
    """Takvimi internetten yeniler; yeni bir şey geldiyse True. İnternet yoksa sessizce False."""
    cache = _cache_file()
    try:
        if not force and cache.exists() and time.time() - cache.stat().st_mtime < REFRESH_SECONDS:
            return False
        req = urllib.request.Request(REMOTE_URL, headers={"User-Agent": "OkulZili"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.load(resp)
        if not _valid(data):
            log.warning("İnternetteki MEB takvimi geçersiz; yerleşik takvim kullanılıyor")
            return False
        old = _load_cache()
        tmp = cache.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(cache)
        changed = old != data["calendars"]
        if changed:
            log.info("MEB takvimi güncellendi: %s", ", ".join(sorted(data["calendars"])))
        return changed
    except Exception as exc:  # noqa: BLE001 - internet yok vb.
        log.debug("MEB takvimi indirilemedi: %s", exc)
        return False


def _fingerprint(cal) -> str:
    import hashlib
    return hashlib.sha1(json.dumps(cal.get("holidays", []), sort_keys=True).encode("utf-8")).hexdigest()[:16]


def apply_calendar(cfg: dict, year: str, force: bool = False) -> int:
    """O eğitim yılının MEB tatillerini ayarlara ekler/günceller. Değişen kayıt sayısını döndürür.

    Takvimden gelen kayıtlar "meb": "2026-2027" ile işaretlenir; yalnızca bunlar güncellenir,
    okulun kendi eklediği tatillere dokunulmaz. Takvimin bu sürümü zaten uygulandıysa (force=False)
    hiçbir şey yapılmaz; böylece okulun sonradan sildiği/değiştirdiği takvim kayıtları geri gelmez —
    yalnızca MEB takvimi değişirse yeniden uygulanır."""
    cal = calendars().get(year)
    if not cal:
        return 0
    applied = cfg.setdefault("meb_applied", {})
    fingerprint = _fingerprint(cal)
    if not force and applied.get(year) == fingerprint:
        return 0
    applied[year] = fingerprint
    wanted = []
    for h in cal["holidays"]:
        entry = {"name": h["name"], "start": h["start"], "end": h.get("end") or h["start"], "meb": year}
        if h.get("from"):
            entry["from"] = h["from"]
        wanted.append(entry)
    current = [h for h in cfg.get("holidays", []) if h.get("meb") == year]
    if sorted(map(json.dumps, current)) == sorted(map(json.dumps, wanted)):
        return 0
    # Okulun elle girdiği aynı tarih ve adlı kayıtlar yinelenmesin.
    own = {(h.get("name"), h.get("start")) for h in cfg.get("holidays", []) if h.get("meb") != year}
    kept = [h for h in cfg.get("holidays", []) if h.get("meb") != year]
    added = [w for w in wanted if (w["name"], w["start"]) not in own]
    cfg["holidays"] = kept + added
    return len(added)


def uses_meb(cfg: dict) -> bool:
    return any(h.get("meb") for h in cfg.get("holidays", []))


def auto_apply(cfg: dict, date: dt.date) -> int:
    """MEB takvimini kullanan okullarda bu ve (açıklandıysa) gelecek eğitim yılının tatillerini günceller."""
    if not cfg.get("meb_auto", True) or not uses_meb(cfg):
        return 0
    this = school_year(date)
    start = int(this.split("-")[0])
    return apply_calendar(cfg, this) + apply_calendar(cfg, f"{start + 1}-{start + 2}")


class CalendarUpdater:
    """Açılıştan bir süre sonra ve günde bir internetteki takvime bakar."""

    def __init__(self, first_delay=90):
        self.changed = False
        self._first_delay = first_delay
        threading.Thread(target=self._run, name="meb-takvimi", daemon=True).start()

    def _run(self):
        time.sleep(self._first_delay)
        while True:
            if refresh():
                self.changed = True
            time.sleep(24 * 3600)


def school_year(date: dt.date) -> str:
    """Tarihin içinde bulunduğu eğitim yılı, ör. 2026-10-27 → «2026-2027» (yaz ayları bir sonrakine sayılır)."""
    start = date.year if date.month >= 7 else date.year - 1
    return f"{start}-{start + 1}"


def calendar_for(date: dt.date):
    return calendars().get(school_year(date))
