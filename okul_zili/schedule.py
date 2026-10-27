"""Ders saatlerinden günlük zil listesini ve o anki durumu hesaplar."""

import datetime as dt
from dataclasses import dataclass, field

from .config import BELL_NAMES, ring_seconds
from .turkish import capitalize_first, ordinal_word


def parse_hm(text: str) -> int:
    """'08:30' -> gece yarısından itibaren dakika. Hatalı biçimde ValueError verir."""
    h, m = str(text).strip().replace(".", ":").split(":")
    h, m = int(h), int(m)
    if not (0 <= h < 24 and 0 <= m < 60):
        raise ValueError(text)
    return h * 60 + m


def fmt_hm(minutes: int) -> str:
    minutes %= 24 * 60
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


@dataclass
class BellEvent:
    minute: int          # gece yarısından itibaren dakika
    kind: str            # ogrenci / ogretmen / cikis / ek
    lesson: int = 0      # ilgili ders numarası (ek zillerde 0)
    variant: str = ""    # cikis için: "", "lunch", "last"
    label: str = ""
    note: str = ""
    sound: str = ""
    text: str = ""       # anons metni (yer tutucular doldurulmuş)
    tts: bool = False
    duration: float = 3.5  # zilin çalma süresi (saniye)
    volume: int = 100
    extra: dict = field(default_factory=dict)
    off: str = ""        # boş değilse zil çalmaz: "Kapalı" veya "Bugün kapalı"

    @property
    def bell_id(self) -> str:
        """Saatten bağımsız kalıcı kimlik (ör. "ogretmen-1")."""
        if self.kind == "ek":
            return f"ek-{self.label}-{self.time_str}"
        return f"{self.kind}-{self.lesson}"

    @property
    def time_str(self) -> str:
        return fmt_hm(self.minute)

    @property
    def key(self) -> str:
        return f"{self.minute}-{self.kind}-{self.lesson}-{self.label}"


def auto_lessons(timing: dict) -> list:
    t = parse_hm(timing["first_lesson"])
    lessons = []
    for i in range(1, int(timing["lesson_count"]) + 1):
        start, end = t, t + int(timing["lesson_minutes"])
        lessons.append((start, end))
        gap = int(timing["lunch_minutes"]) if i == int(timing["lunch_after"]) else int(timing["break_minutes"])
        t = end + gap
    return lessons


def config_for_date(cfg: dict, date: dt.date) -> dict:
    """O tarihe bir zil programı atanmışsa, programın ayarlarıyla birleştirilmiş ayarları döndürür."""
    iso = date.isoformat()
    for item in cfg.get("profile_dates", []):
        profile = cfg.get("profiles", {}).get(item.get("profile"))
        if item.get("date") == iso and profile:
            return dict(cfg, **profile)
    return cfg


def profile_name_for_date(cfg: dict, date: dt.date):
    iso = date.isoformat()
    for item in cfg.get("profile_dates", []):
        if item.get("date") == iso and item.get("profile") in cfg.get("profiles", {}):
            return item["profile"]
    return None


def lessons_for_weekday(cfg: dict, weekday: int) -> list:
    """Verilen gün için [(başlangıç, bitiş), ...] listesi (dakika)."""
    override = cfg.get("day_overrides", {}).get(str(weekday))
    if override:
        rows = override
    elif cfg.get("schedule_mode") == "manual":
        rows = cfg.get("manual_lessons", [])
    else:
        return auto_lessons(cfg["timing"])
    out = []
    for start, end in rows:
        try:
            out.append((parse_hm(start), parse_hm(end)))
        except ValueError:
            continue
    out.sort()
    return out


def holiday_name(cfg: dict, date: dt.date):
    """Tarih tatilse tatilin adını (boş olabilir), değilse None döndürür."""
    iso = date.isoformat()
    for h in cfg.get("holidays", []):
        start = h.get("start") or ""
        if start and start <= iso <= (h.get("end") or start):
            return h.get("name") or "Tatil"
    return None


def is_school_day(cfg: dict, date: dt.date) -> bool:
    return date.weekday() in cfg.get("active_days", [0, 1, 2, 3, 4]) and holiday_name(cfg, date) is None


def _fill(template: str, lesson: int, minute: int) -> str:
    try:
        return template.format(ders=lesson, ders_sira=ordinal_word(lesson), saat=fmt_hm(minute)).strip()
    except (KeyError, IndexError, ValueError):
        return template.strip()


def _bell(cfg, minute, kind, lesson, variant, note):
    b = cfg["bells"][kind]
    template = b.get("text", "")
    if variant == "lunch":
        template = b.get("text_lunch") or template
    elif variant == "last":
        template = b.get("text_last") or template
    text = _fill(template, lesson, minute)
    text = capitalize_first(text)
    return BellEvent(
        minute=minute, kind=kind, lesson=lesson, variant=variant,
        label=BELL_NAMES[kind], note=note, sound=b.get("sound", ""),
        text=text, tts=bool(b.get("tts")) and cfg["tts"].get("enabled", False),
        duration=ring_seconds(b.get("duration")), volume=int(b.get("volume", 100)),
    )


def events_for_lessons(cfg: dict, lessons: list) -> list:
    timing = cfg["timing"]
    offset = int(timing.get("student_offset", 2))
    # Süreler ile hesaplanan programda öğle arası ayardan bilinir; elle girilen saatlerde
    # 30 dakika ve üzeri boşluk öğle arası sayılır.
    auto = lessons == auto_lessons(timing)
    lunch_after = int(timing.get("lunch_after", 0)) if int(timing.get("lunch_minutes", 0)) > 0 else 0

    def is_lunch(lesson_no, gap):
        return lesson_no == lunch_after if auto else gap >= 30

    events = []
    for i, (start, end) in enumerate(lessons, start=1):
        prev_end = lessons[i - 2][1] if i > 1 else None
        if offset > 0:
            student = start - offset
            if prev_end is None:
                e = _bell(cfg, student, "ogrenci", i, "", "Öğrenciler sınıfa girer")
                if not timing.get("morning_student_bell", True):
                    e.off = "Kapalı"   # Sabah Zilleri ayarından kapatıldı; listede görünür ama çalmaz
                events.append(e)
            elif student > prev_end:
                note = "Öğle arası bitmek üzere" if is_lunch(i - 1, start - prev_end) else "Teneffüs bitmek üzere"
                events.append(_bell(cfg, student, "ogrenci", i, "", note))
        e = _bell(cfg, start, "ogretmen", i, "", f"{i}. ders başlar")
        if i == 1 and not timing.get("morning_teacher_bell", True):
            e.off = "Kapalı"
        events.append(e)
        if i == len(lessons):
            variant, note = "last", "Okul dağılır"
        else:
            gap = lessons[i][0] - end
            if is_lunch(i, gap):
                variant, note = "lunch", f"{i}. ders biter · Öğle arası ({gap} dk)"
            else:
                variant, note = "", f"{i}. ders biter · Teneffüs ({gap} dk)"
        events.append(_bell(cfg, end, "cikis", i, variant, note))
    return events


def extra_events(cfg: dict, weekday: int) -> list:
    out = []
    for e in cfg.get("extra_bells", []):
        if not e.get("enabled", True) or weekday not in e.get("days", []):
            continue
        try:
            minute = parse_hm(e["time"])
        except (KeyError, ValueError):
            continue
        text = _fill(e.get("text", ""), 0, minute)
        out.append(BellEvent(
            minute=minute, kind="ek", label=e.get("label") or "Ek Zil", note="Ek zil",
            sound=e.get("sound", "builtin:gong"), text=text,
            tts=bool(text) and cfg["tts"].get("enabled", False),
            duration=ring_seconds(e.get("duration")), volume=int(e.get("volume", 100)), extra=e,
        ))
    return out


def is_disabled(cfg: dict, weekday: int, bell_id: str) -> bool:
    d = cfg.get("disabled_bells", {})
    return bell_id in d.get("all", []) or bell_id in d.get(str(weekday), [])


def events_for_date(cfg: dict, date: dt.date) -> list:
    if not is_school_day(cfg, date):
        return []
    cfg = config_for_date(cfg, date)
    events = events_for_lessons(cfg, lessons_for_weekday(cfg, date.weekday()))
    events += extra_events(cfg, date.weekday())
    skip = cfg.get("skip_today") or {}
    skipped = skip.get("ids", []) if skip.get("date") == date.isoformat() else []
    for e in events:
        if e.off:
            continue
        if is_disabled(cfg, date.weekday(), e.bell_id):
            e.off = "Kapalı"
        elif e.bell_id in skipped:
            e.off = "Bugün kapalı"
    events.sort(key=lambda e: (e.minute, {"cikis": 0, "ek": 1, "ogrenci": 2, "ogretmen": 3}[e.kind]))
    return events


def next_school_day(cfg: dict, date: dt.date, limit_days=120):
    """date'ten sonraki ilk zil çalacak gün ve o günün ilk zili: (tarih, BellEvent) veya None."""
    for i in range(1, limit_days + 1):
        d = date + dt.timedelta(days=i)
        events = [e for e in events_for_date(cfg, d) if not e.off]
        if events:
            return d, events[0]
    return None


def current_status(cfg: dict, now: dt.datetime):
    """(başlık, ayrıntı, ilerleme 0..1 veya None) döndürür."""
    date = now.date()
    if not is_school_day(cfg, date):
        name = holiday_name(cfg, date)
        return ("Bugün tatil" if name else "Bugün ders yok", name or "Ziller çalmayacak", None)
    cfg = config_for_date(cfg, date)
    lessons = lessons_for_weekday(cfg, date.weekday())
    if not lessons:
        return ("Bugün ders yok", "Ders saati tanımlı değil", None)
    m = now.hour * 60 + now.minute + now.second / 60
    if m < lessons[0][0]:
        return ("Dersler başlamadı", f"İlk ders {fmt_hm(lessons[0][0])}'da başlıyor", None)
    for i, (start, end) in enumerate(lessons, start=1):
        if start <= m < end:
            left = end - m
            return (f"{i}. ders devam ediyor", f"Bitişe {int(left)} dk {int((left % 1) * 60)} sn",
                    (m - start) / (end - start))
        if i < len(lessons) and end <= m < lessons[i][0]:
            nxt = lessons[i][0]
            kind = "Öğle arası" if nxt - end >= 30 else "Teneffüs"
            left = nxt - m
            return (kind, f"{i + 1}. derse {int(left)} dk {int((left % 1) * 60)} sn",
                    (m - end) / (nxt - end))
    return ("Dersler sona erdi", "İyi günler!", None)
