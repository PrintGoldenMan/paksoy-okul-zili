"""Ayarların varsayılan değerleri, yüklenmesi ve kaydedilmesi."""

import copy
import json
import logging

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
            "sound": "builtin:melodi", "duration": DEFAULT_RING_SECONDS, "volume": 100, "tts": True,
            "text": "Sevgili öğrenciler, {ders_sira} ders başlamak üzere. "
                    "Lütfen sınıflarınıza geçiniz.",
        },
        "ogretmen": {
            "sound": "builtin:klasik", "duration": DEFAULT_RING_SECONDS, "volume": 100, "tts": True,
            "text": "Sayın öğretmenlerimiz, {ders_sira} ders başlamıştır.",
        },
        "cikis": {
            "sound": "builtin:kampana", "duration": DEFAULT_RING_SECONDS, "volume": 100, "tts": True,
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
    #   "sound": "builtin:gong", "text": "", "duration": 3.5}]
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
    "prepare_announcements": True,
    "skip_date": None,  # "Bugün zilleri kapat" seçildiğinde o günün tarihi
    "autostart": False,
}


# Bir zil programını oluşturan ayarlar (Profesyonel düzeydeki "Zil Programları" bunları saklar).
PROFILE_KEYS = ["timing", "schedule_mode", "manual_lessons", "day_overrides", "disabled_bells"]


def profile_snapshot(cfg: dict) -> dict:
    return {k: copy.deepcopy(cfg[k]) for k in PROFILE_KEYS}


def _merge(defaults, loaded):
    """Kayıtlı ayarları varsayılanların üstüne yazar; yeni sürümde eklenen anahtarlar korunur."""
    if not isinstance(defaults, dict) or not isinstance(loaded, dict):
        return copy.deepcopy(loaded)
    out = copy.deepcopy(defaults)
    for key, value in loaded.items():
        if key in out and isinstance(out[key], dict) and isinstance(value, dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def default_config() -> dict:
    return copy.deepcopy(DEFAULTS)


def load() -> dict:
    path = paths.config_file()
    if not path.exists():
        return default_config()
    try:
        with open(path, encoding="utf-8") as f:
            return _merge(DEFAULTS, json.load(f))
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
    tmp.replace(path)


def import_from(file_path) -> dict:
    with open(file_path, encoding="utf-8") as f:
        return _merge(DEFAULTS, json.load(f))


def export_to(cfg: dict, file_path) -> None:
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
