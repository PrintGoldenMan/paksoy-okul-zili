"""Ayarların varsayılan değerleri, yüklenmesi ve kaydedilmesi."""

import copy
import datetime as dt
import json
import logging
import math
import os
import re

from . import paths

log = logging.getLogger(__name__)

LEVELS = ["kolay", "basit", "gelismis", "uzman", "profesyonel"]
LEVEL_NAMES = {"kolay": "Çok Kolay", "basit": "Basit", "gelismis": "Gelişmiş", "uzman": "Uzman",
               "profesyonel": "Profesyonel"}
LEVEL_DESCRIPTIONS = {
    "kolay": "Tek sayfa: ses düzeyi, zil çalma süresi, sabah zillerini açma/kapatma ve otomatik başlatma. "
             "Ders saatleri okulun programına göre hazır gelir.",
    "basit": "Yalnızca gerekli ayarlar: ders başlangıcı, ders ve teneffüs süreleri, "
             "zil sesleri. Hızlı ve kolay kullanım için önerilir.",
    "gelismis": "Basit düzeye ek olarak: ders saatlerini tek tek düzenleme, okul günleri, "
                "tatiller, kendi ses dosyalarınız ve Türkçe sesli anonslar.",
    "uzman": "Her şey ayarlanabilir: güne özel ders saatleri, ek ziller (İstiklal Marşı, "
             "tören vb.), anons sesi ve hızı, yedekleme ve kayıtlar.",
    "profesyonel": "Uzman düzeye ek olarak: her zili tek tek açıp kapatma, birden çok zil programı "
                   "(ör. kısaltılmış ders, sınav haftası) ve bunları belirli tarihlere atama, teknik ayarlar.",
}

# Zilin kaç saniye çalacağı. Ses daha kısaysa başa sarılarak tekrarlanır, daha uzunsa
# süre dolunca yumuşakça kısılarak durdurulur.
DEFAULT_RING_SECONDS = 3.5
# Programla gelen zil sesi (Für Elise'in açılış cümlesi): zil bu kadar çalar ve cümle bitince susar.
DEFAULT_BELL_SOUND = "gomulu:zil"
DEFAULT_BELL_SECONDS = 9.5
MIN_RING_SECONDS = 1.5
MAX_RING_SECONDS = 30.0


def ring_seconds(value) -> float:
    try:
        v = float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return DEFAULT_RING_SECONDS
    if not math.isfinite(v):
        return DEFAULT_RING_SECONDS
    return max(MIN_RING_SECONDS, min(MAX_RING_SECONDS, v))


BELL_TYPES = ["ogrenci", "ogretmen", "cikis"]
BELL_NAMES = {"ogrenci": "Öğrenci Zili", "ogretmen": "Öğretmen Zili",
              "cikis": "Çıkış Zili", "ek": "Ek Zil", "toplanma": "Toplanma Zili"}
# Sabah toplanma zili: açıksa ilk dersten «assembly_minutes» dakika önce çalar ve o günün ilk öğrenci zili
# (ör. 08:28) çalmaz; öğretmen zili (08:30) olduğu gibi kalır. Yalnızca sabahçılar / tek grup için.
DEFAULT_ASSEMBLY_MINUTES = 10

def _rotation_default():
    """Değişen zil sesi (rotation.py): kapalıyken zil «sound» ayarındaki sesi çalar."""
    return {"enabled": False, "period": "week", "pool": [], "current": "", "key": ""}


DEFAULTS = {
    "version": 1,
    "level": None,  # İlk açılışta kullanıcıya sorulur.
    "theme": "system",
    "school_name": "",           # ilk açılıştaki kurulum sihirbazında sorulur
    "setup_done": False,         # kurulum sihirbazı tamamlandı mı (eski kurulumlarda True kabul edilir)
    "school_type": "lise",
    "auto_ring": True,
    "master_volume": 85,
    "confirm_exit": True,
    "timing": {
        "first_lesson": "08:30",
        "lesson_count": 8,
        "lesson_minutes": 40,
        "break_minutes": 10,
        "lunch_after": 5,
        "lunch_minutes": 40,
        "student_offset": 2,
        "morning_student_bell": True,   # ilk dersten önceki öğrenci zili (08:28)
        "morning_teacher_bell": True,   # ilk dersin öğretmen zili (08:30)
        "assembly_bell": False,         # toplanma zili (ilk dersten 10 dk önce, ör. 08:20); 08:28 zili çalmaz
        "assembly_minutes": DEFAULT_ASSEMBLY_MINUTES,
        # Uzman / Profesyonel düzeyde: zilin adı, sabit saat ("" = ilk dersten dakika önce), günler
        # (0 = Pazartesi), sabah öğrenci zili de çalsın mı, öğlenciler için de çalsın mı
        "assembly_name": "Toplanma Zili",
        "assembly_time": "",
        "assembly_days": [0, 1, 2, 3, 4, 5, 6],
        "assembly_keep_student": False,
        "assembly_second_shift": False,
    },
    # "auto": süreler kullanılarak hesaplanır, "manual": ders saatleri tek tek girilir.
    "schedule_mode": "auto",
    "manual_lessons": [
        ["08:30", "09:10"], ["09:20", "10:00"], ["10:10", "10:50"], ["11:00", "11:40"],
        ["11:50", "12:30"], ["13:10", "13:50"], ["14:00", "14:40"], ["14:50", "15:30"],
    ],
    "active_days": [0, 1, 2, 3, 4],
    # Uzman düzeyi: güne özel ders saatleri, ör. {"4": [["08:30", "09:10"], ...]}
    "day_overrides": {},
    "bells": {
        "ogrenci": {
            "sound": DEFAULT_BELL_SOUND, "duration": DEFAULT_BELL_SECONDS, "volume": 100, "tts": True,
            "rotation": _rotation_default(),
            "text": "Sevgili öğrenciler, {ders_sira} ders başlamak üzere. "
                    "Lütfen sınıflarınıza geçiniz.",
        },
        "ogretmen": {
            "sound": DEFAULT_BELL_SOUND, "duration": DEFAULT_BELL_SECONDS, "volume": 100, "tts": True,
            "rotation": _rotation_default(),
            "text": "Sayın öğretmenlerimiz, {ders_sira} ders başlamıştır.",
        },
        "cikis": {
            "sound": DEFAULT_BELL_SOUND, "duration": DEFAULT_BELL_SECONDS, "volume": 100, "tts": True,
            "rotation": _rotation_default(),
            "text": "{ders_sira} ders sona ermiştir. İyi teneffüsler.",
            "text_lunch": "Öğle arası başlamıştır. Afiyet olsun.",
            "text_last": "Bugünkü dersler sona ermiştir. İyi günler dileriz.",
        },
        "toplanma": {
            "sound": DEFAULT_BELL_SOUND, "duration": DEFAULT_BELL_SECONDS, "volume": 100, "tts": True,
            "rotation": _rotation_default(),
            "text": "Sevgili öğrenciler, toplanma zili çaldı. Lütfen toplanma alanına geçiniz.",
        },
    },
    "tts": {
        "enabled": False,
        "engine": "edge",          # "edge" (internet, doğal ses) veya "offline" (Windows sesleri)
        "voice": "tr-TR-EmelNeural",
        "rate": 0,                 # yüzde, -50..+50
        "volume": 100,
        "pause_ms": 400,           # zil ile anons arasındaki bekleme
    },
    # [{"start": "2026-10-29", "end": "2026-10-29", "name": "Cumhuriyet Bayramı"}]
    "holidays": [],
    # [{"enabled": true, "time": "08:25", "days": [0], "label": "İstiklal Marşı",
    #   "sound": "lib:<kimlik>", "text": "", "duration": 3.5}]
    "extra_bells": [],
    # Profesyonel düzey: kalıcı olarak kapatılan ziller, ör. {"all": ["cikis-8"], "4": ["ogrenci-6"]}
    # Kimlikler "tür-dersno" biçimindedir; böylece ders saatleri değişse de geçerli kalır.
    "disabled_bells": {},
    # Ana ekrandan yalnızca bugün için kapatılan ziller: {"date": "2026-10-27", "ids": ["ogretmen-1"]}
    "skip_today": {"date": None, "ids": []},
    # Profesyonel düzey: adlandırılmış zil programları ve belirli tarihlere atanmaları
    "profiles": {},
    "profile_dates": [],   # [{"date": "2026-11-10", "profile": "Kısaltılmış Ders"}]
    "grace_seconds": 45,
    "tray_on_close": True,       # pencere kapatılınca sistem tepsisine küçült (program çalışmaya devam eder)
    "watchdog": True,            # program beklenmedik şekilde kapanırsa 5 dk içinde yeniden başlat (Windows)
    "keep_awake": True,          # okul saatlerinde bilgisayarın uykuya geçmesini engelle
    "check_updates": True,       # yeni sürüm çıkınca haber ver
    "check_clock": True,         # internet varsa bilgisayar saatini denetle
    "start_in_tray": True,       # bilgisayar açılınca pencere açılmadan tepside başla (autostart.BACKGROUND_FLAG)
    "use_network_time": False,   # ziller bilgisayar saati yerine internet saatine göre çalsın (clock.py)
    "check_volume": True,        # Windows sesi kapalı/çok kısıksa uyar
    "prepare_announcements": True,
    "skip_date": None,  # "Bugün zilleri kapat" seçildiğinde o günün tarihi
    # İkili öğretim: ilk vardiya yukarıdaki ders saatlerini kullanır; ikinci vardiyanın kendi saatleri vardır.
    "first_shift_name": "Sabahçı",
    "second_shift": {
        "enabled": False,
        "name": "Öğlenci",
        "schedule_mode": "auto",
        "timing": {"first_lesson": "13:00", "lesson_count": 6, "lesson_minutes": 40, "break_minutes": 10,
                   "lunch_after": 0, "lunch_minutes": 0},
        "manual_lessons": [],
    },
    # «Bugün kısaltılmış ders»: yalnızca o tarihte dersler kısaltılır
    "short_day": {"date": None, "lesson_minutes": 30, "break_minutes": 10, "lunch_minutes": None},
    "meb_applied": {},           # {"2026-2027": "<takvim parmak izi>"} – takvimin hangi sürümü uygulandı
    "meb_auto": True,            # MEB takvimi internetten güncellenince tatiller kendiliğinden eklensin
    # Tören düğmeleri (ana ekran): İstiklal Marşı / Saygı Duruşu + İstiklal Marşı (ceremony.py)
    "ceremony": {
        "show": True,            # ana ekranda düğmeler görünsün
        "confirm": True,         # başlatmadan önce sor (yanlışlıkla basılmasın)
        "volume": 100,           # genel ses düzeyine göre yüzde
        "items": {"istiklal": {"sound": "", "url": ""}, "saygi": {"sound": "", "url": ""}},
    },
    "autostart": False,
}


# Bir zil programını oluşturan ayarlar (Profesyonel düzeydeki "Zil Programları" bunları saklar).
PROFILE_KEYS = ["timing", "schedule_mode", "manual_lessons", "day_overrides", "disabled_bells", "second_shift"]


def profile_snapshot(cfg: dict) -> dict:
    return {k: copy.deepcopy(cfg[k]) for k in PROFILE_KEYS}


_MISSING = object()


def merge_changes(base, mine, current):
    """Üç yönlü birleştirme: ayarlar penceresi açılırken alınan kopya (base), pencerede düzenlenen
    (mine) ve o arada programın kendisinin değiştirdiği güncel ayarlar (current; ör. MEB takvimi,
    değişen ses, kütüphane). Pencerede değiştirilmeyen ayarın güncel hali korunur; ikisi de
    değiştiyse pencere kazanır. Sözlükler anahtar anahtar birleştirilir."""
    if isinstance(base, dict) and isinstance(mine, dict) and isinstance(current, dict):
        out = {}
        for key in list(mine) + [k for k in current if k not in mine]:
            value = merge_changes(base.get(key, _MISSING), mine.get(key, _MISSING), current.get(key, _MISSING))
            if value is not _MISSING:
                out[key] = value
        return out
    if mine == base:
        return copy.deepcopy(current) if current is not _MISSING else _MISSING
    return copy.deepcopy(mine) if mine is not _MISSING else _MISSING


def _merge(defaults, loaded):
    """Kayıtlı ayarları varsayılanların üstüne yazar; yeni sürümde eklenen anahtarlar korunur.
    Türü varsayılandan farklı olan değerler (ör. elle düzenlenip bozulmuş) yok sayılır."""
    if not isinstance(loaded, dict):
        return copy.deepcopy(defaults)
    out = copy.deepcopy(defaults)
    for key, value in loaded.items():
        if key not in out:
            out[key] = copy.deepcopy(value)
        elif isinstance(out[key], dict):
            if isinstance(value, dict):
                out[key] = _merge(out[key], value)
        elif not _same_type(out[key], value):
            log.warning("Ayar «%s» geçersiz, varsayılan kullanılıyor", key)
        else:
            out[key] = copy.deepcopy(value)
    return out


def _same_type(default, value) -> bool:
    if default is None:
        return True          # varsayılanı boş olan ayarlar (ör. skip_date) her değeri alabilir
    if value is None:
        return False         # elle yazılmış «null», sayı/yazı beklenen yerde kabul edilmez
    if isinstance(default, bool) or isinstance(value, bool):
        return isinstance(default, bool) == isinstance(value, bool)
    if isinstance(default, (int, float)):
        # JSON «Infinity»/«NaN» de sayı olarak okunur; int() ile hata verdiği için kabul edilmez.
        return isinstance(value, (int, float)) and math.isfinite(value)
    return isinstance(value, type(default))


def _valid_rows(rows) -> list:
    """Ders saati satırlarından yalnızca ["SS:DD", "SS:DD"] biçiminde ve bitişi başlangıçtan sonra olanlar."""
    out = []
    for row in rows if isinstance(rows, list) else []:
        if not (isinstance(row, (list, tuple)) and len(row) == 2 and all(isinstance(x, str) for x in row)):
            continue
        try:
            h1, m1 = (int(x) for x in row[0].replace(".", ":").split(":"))
            h2, m2 = (int(x) for x in row[1].replace(".", ":").split(":"))
        except ValueError:
            continue
        if 0 <= h1 < 24 and 0 <= h2 < 24 and 0 <= m1 < 60 and 0 <= m2 < 60 and h2 * 60 + m2 > h1 * 60 + m1:
            out.append([row[0], row[1]])
    return out


def _iso_date(value):
    """"2026-10-29" biçimindeki tarihi döndürür; geçersizse None."""
    if not isinstance(value, str):
        return None
    try:
        return dt.date.fromisoformat(value.strip()).isoformat()
    except ValueError:
        return None


def _valid_holidays(items) -> list:
    """Tatillerden başlangıcı, bitişi ve (yarım günse) saati geçerli olanlar; bozuk kayıt atılır."""
    out = []
    for h in items:
        start = _iso_date(h.get("start"))
        end = _iso_date(h.get("end")) if h.get("end") else start
        fixed = dict(h, start=start, end=end)
        if h.get("from"):
            try:
                hh, mm = (int(x) for x in str(h["from"]).strip().replace(".", ":").split(":"))
                if not (0 <= hh < 24 and 0 <= mm < 60):
                    raise ValueError(h["from"])
                fixed["from"] = f"{hh:02d}:{mm:02d}"
            except (TypeError, ValueError):
                start = None
        else:
            fixed.pop("from", None)
        if start is None or end is None or end < start:
            log.warning("Tatil kaydı geçersiz, yok sayıldı: %s", h)
            continue
        if "name" in h and not isinstance(h["name"], str):
            fixed["name"] = "Tatil"
        out.append(fixed)
    return out


def _number(value, default, low, high):
    """Elle yazılmış sayıyı sınırlar içine alır; sayı değilse (ör. «yüksek», null, Infinity) varsayılan."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return default
    return max(low, min(high, value))


def _valid_extra_bells(items) -> list:
    """Ek zillerin alanlarını denetler: türü yanlış alan varsayılana döner, saati bozuk zil atılır."""
    out = []
    for e in items:
        if not isinstance(e.get("time"), str) or not isinstance(e.get("days", []), list):
            log.warning("Ek zil geçersiz, yok sayıldı: %s", e)
            continue
        fixed = dict(e, days=[d for d in e.get("days", []) if isinstance(d, int) and not isinstance(d, bool)
                              and 0 <= d <= 6])
        for key in ("label", "sound", "text"):
            if not isinstance(fixed.get(key, ""), str):
                fixed[key] = ""
        for key in ("enabled", "full"):
            if key in fixed and not isinstance(fixed[key], bool):
                fixed[key] = bool(fixed[key]) if isinstance(fixed[key], (int, float)) else key == "enabled"
        fixed["volume"] = int(_number(fixed.get("volume", 100), 100, 0, 100))
        fixed["duration"] = ring_seconds(fixed.get("duration"))
        out.append(fixed)
    return out


def _sanitize(cfg: dict) -> dict:
    """Elle düzenlenmiş ayar dosyasındaki bozuk liste öğelerini atar; ziller bir hata yüzünden durmasın."""
    def dicts(value):
        return [x for x in value if isinstance(x, dict)] if isinstance(value, list) else []

    cfg["manual_lessons"] = _valid_rows(cfg.get("manual_lessons"))
    if not cfg["manual_lessons"]:
        cfg["manual_lessons"] = copy.deepcopy(DEFAULTS["manual_lessons"])
    overrides = cfg.get("day_overrides") if isinstance(cfg.get("day_overrides"), dict) else {}
    cfg["day_overrides"] = {str(k): rows for k, v in overrides.items()
                            if str(k) in {str(i) for i in range(7)} and (rows := _valid_rows(v))}
    cfg["active_days"] = sorted({d for d in cfg.get("active_days", []) if isinstance(d, int) and 0 <= d <= 6})
    cfg["holidays"] = _valid_holidays(dicts(cfg.get("holidays")))
    cfg["extra_bells"] = _valid_extra_bells(dicts(cfg.get("extra_bells")))
    cfg["profile_dates"] = [d for d in dicts(cfg.get("profile_dates"))
                            if isinstance(d.get("date"), str) and isinstance(d.get("profile"), str)]
    profiles = cfg.get("profiles") if isinstance(cfg.get("profiles"), dict) else {}
    cfg["profiles"] = {}
    for name, p in profiles.items():
        if isinstance(p, dict):
            # Eksik ya da bozuk program ayarları güncel ayarlarla tamamlanır.
            fixed = _merge({k: cfg[k] for k in PROFILE_KEYS}, p)
            fixed["manual_lessons"] = _valid_rows(fixed.get("manual_lessons")) or cfg["manual_lessons"]
            cfg["profiles"][str(name)] = fixed
    second = cfg.get("second_shift")
    if not isinstance(second, dict):
        cfg["second_shift"] = copy.deepcopy(DEFAULTS["second_shift"])
    else:
        second["manual_lessons"] = _valid_rows(second.get("manual_lessons"))
        if not isinstance(second.get("timing"), dict):
            second["timing"] = copy.deepcopy(DEFAULTS["second_shift"]["timing"])
    if not isinstance(cfg.get("short_day"), dict):
        cfg["short_day"] = copy.deepcopy(DEFAULTS["short_day"])
    t = cfg.get("timing")
    if isinstance(t, dict):
        days = t.get("assembly_days")
        t["assembly_days"] = sorted({d for d in days if isinstance(d, int) and 0 <= d <= 6}) \
            if isinstance(days, list) else list(range(7))
        at = t.get("assembly_time")
        if not isinstance(at, str) or (at and not re.fullmatch(r"([01]?\d|2[0-3]):[0-5]\d", at.strip())):
            t["assembly_time"] = ""
        if not isinstance(t.get("assembly_name"), str):
            t["assembly_name"] = DEFAULTS["timing"]["assembly_name"]
    lunch = cfg["short_day"].get("lunch_minutes")
    if lunch is not None:
        cfg["short_day"]["lunch_minutes"] = _number(lunch, None, 0, 180)
    cer = cfg.get("ceremony")
    if not isinstance(cer, dict) or not isinstance(cer.get("items"), dict):
        cfg["ceremony"] = cer = dict(cer if isinstance(cer, dict) else {},
                                     items=copy.deepcopy(DEFAULTS["ceremony"]["items"]))
    for key, default in DEFAULTS["ceremony"]["items"].items():
        item = cer["items"].get(key)
        if not isinstance(item, dict):
            item = cer["items"][key] = copy.deepcopy(default)
        for field in ("sound", "url"):
            if not isinstance(item.get(field), str):
                item[field] = ""
    try:
        cer["volume"] = max(10, min(100, int(cer.get("volume", 100))))
    except (TypeError, ValueError, OverflowError):
        cer["volume"] = 100
    disabled = cfg.get("disabled_bells") if isinstance(cfg.get("disabled_bells"), dict) else {}
    cfg["disabled_bells"] = {str(k): [x for x in v if isinstance(x, str)]
                             for k, v in disabled.items() if isinstance(v, list)}
    skip = cfg.get("skip_today")
    if not isinstance(skip, dict) or not isinstance(skip.get("ids", []), list):
        cfg["skip_today"] = {"date": None, "ids": []}
    for bell in cfg.get("bells", {}).values():
        rot = bell.get("rotation")
        if not isinstance(rot, dict):
            bell["rotation"] = _rotation_default()
            continue
        rot["pool"] = [s for s in rot.get("pool") or [] if isinstance(s, str)] if isinstance(rot.get("pool"), list) else []
        for key in ("current", "key", "period"):
            if not isinstance(rot.get(key), str):
                rot[key] = _rotation_default()[key]
    return cfg


def _migrate(cfg: dict) -> dict:
    """Eski sürümlerdeki program içi hazır seslerin («builtin:…») yerini «seçilmedi» alır. Sesi hiç
    seçilmemiş (uyarı sesi çalan) zillere programla gelen zil sesi verilir; çalma süresi hiç
    değiştirilmemişse (3,5 sn) zil sesinin kendi süresine çıkarılır ki müzik cümlesi yarıda kesilmesin."""
    for bell in list(cfg.get("bells", {}).values()) + list(cfg.get("extra_bells", [])):
        if isinstance(bell, dict) and str(bell.get("sound", "")).startswith("builtin:"):
            bell["sound"] = ""
    for bell in (cfg.get("bells") or {}).values():
        if isinstance(bell, dict) and bell.get("sound") == "":
            bell["sound"] = DEFAULT_BELL_SOUND
            if bell.get("duration") in (None, DEFAULT_RING_SECONDS):
                bell["duration"] = DEFAULT_BELL_SECONDS
    return cfg


def default_config() -> dict:
    return copy.deepcopy(DEFAULTS)


def load() -> dict:
    path = paths.config_file()
    if not path.exists():
        return default_config()
    try:
        # utf-8-sig: Not Defteri ile kaydedilmiş (BOM'lu) dosyalar da okunur.
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("ayar dosyası bir nesne değil")
        # Sihirbazdan önceki sürümlerle kurulmuş okullar: kurulum yapılmış sayılır, sihirbaz açılmaz.
        data.setdefault("setup_done", True)
        return _sanitize(_migrate(_merge(DEFAULTS, data)))
    except Exception as exc:  # noqa: BLE001 - bozuk ayar dosyası programı açılışta çökertmesin
        log.error("Ayarlar okunamadı, varsayılanlar kullanılıyor: %s", exc)
        backup = path.with_suffix(".bozuk.json")
        try:
            path.replace(backup)
        except OSError:
            pass
        return default_config()


def save(cfg: dict) -> None:
    path = paths.config_file()
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)


def import_from(file_path) -> dict:
    with open(file_path, encoding="utf-8-sig") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("Bu dosya bir Okul Zili ayar dosyası değil.")
    return _sanitize(_migrate(_merge(DEFAULTS, data)))


def export_to(cfg: dict, file_path) -> None:
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
