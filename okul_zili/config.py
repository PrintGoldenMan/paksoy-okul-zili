"""Ayarların varsayılan değerleri, yüklenmesi ve kaydedilmesi."""

import copy
import json
import logging
import os

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
MIN_RING_SECONDS = 1.5
MAX_RING_SECONDS = 30.0


def ring_seconds(value) -> float:
    try:
        v = float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return DEFAULT_RING_SECONDS
    return max(MIN_RING_SECONDS, min(MAX_RING_SECONDS, v))


BELL_TYPES = ["ogrenci", "ogretmen", "cikis"]
BELL_NAMES = {"ogrenci": "Öğrenci Zili", "ogretmen": "Öğretmen Zili",
              "cikis": "Çıkış Zili", "ek": "Ek Zil"}

def _rotation_default():
    """Değişen zil sesi (rotation.py): kapalıyken zil «sound» ayarındaki sesi çalar."""
    return {"enabled": False, "period": "week", "pool": [], "current": "", "key": ""}


DEFAULTS = {
    "version": 1,
    "level": None,  # İlk açılışta kullanıcıya sorulur.
    "theme": "system",
    "school_name": "Abdulkadir Paksoy Anadolu Lisesi",
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
            "sound": "", "duration": DEFAULT_RING_SECONDS, "volume": 100, "tts": True,
            "rotation": _rotation_default(),
            "text": "Sevgili öğrenciler, {ders_sira} ders başlamak üzere. "
                    "Lütfen sınıflarınıza geçiniz.",
        },
        "ogretmen": {
            "sound": "", "duration": DEFAULT_RING_SECONDS, "volume": 100, "tts": True,
            "rotation": _rotation_default(),
            "text": "Sayın öğretmenlerimiz, {ders_sira} ders başlamıştır.",
        },
        "cikis": {
            "sound": "", "duration": DEFAULT_RING_SECONDS, "volume": 100, "tts": True,
            "rotation": _rotation_default(),
            "text": "{ders_sira} ders sona ermiştir. İyi teneffüsler.",
            "text_lunch": "Öğle arası başlamıştır. Afiyet olsun.",
            "text_last": "Bugünkü dersler sona ermiştir. İyi günler dileriz.",
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
    "check_volume": True,        # Windows sesi kapalı/çok kısıksa uyar
    "prepare_announcements": True,
    "skip_date": None,  # "Bugün zilleri kapat" seçildiğinde o günün tarihi
    "autostart": False,
}


# Bir zil programını oluşturan ayarlar (Profesyonel düzeydeki "Zil Programları" bunları saklar).
PROFILE_KEYS = ["timing", "schedule_mode", "manual_lessons", "day_overrides", "disabled_bells"]


def profile_snapshot(cfg: dict) -> dict:
    return {k: copy.deepcopy(cfg[k]) for k in PROFILE_KEYS}


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
        return isinstance(value, (int, float))
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
    cfg["holidays"] = [h for h in dicts(cfg.get("holidays")) if isinstance(h.get("start"), str)]
    cfg["extra_bells"] = [e for e in dicts(cfg.get("extra_bells"))
                          if isinstance(e.get("time"), str) and isinstance(e.get("days", []), list)]
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
    """Eski sürümlerdeki program içi hazır seslerin («builtin:…») yerini «seçilmedi» alır."""
    for bell in list(cfg.get("bells", {}).values()) + list(cfg.get("extra_bells", [])):
        if isinstance(bell, dict) and str(bell.get("sound", "")).startswith("builtin:"):
            bell["sound"] = ""
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
        return _sanitize(_migrate(_merge(DEFAULTS, data)))
    except (OSError, ValueError) as exc:
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
