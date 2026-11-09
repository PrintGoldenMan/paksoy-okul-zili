"""Ders saatlerinden günlük zil listesini ve o anki durumu hesaplar."""

import datetime as dt
import logging
from dataclasses import dataclass, field

from . import rotation
from .config import BELL_NAMES, DEFAULT_ASSEMBLY_MINUTES, ring_seconds
from .turkish import capitalize_first, ordinal_word

log = logging.getLogger(__name__)

DAY_MINUTES = 24 * 60


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
    kind: str            # ogrenci / ogretmen / cikis / ek / toplanma
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
    shift: int = 1       # ikili öğretimde 1 = sabahçı, 2 = öğlenci
    index: int = 0       # ek zillerde listedeki sırası (aynı dakikadaki iki ek zil ayrı tutulsun)
    dup: int = 1         # ek zillerde aynı ad ve saatteki kaçıncı zil (kimlikleri karışmasın)

    @property
    def bell_id(self) -> str:
        """Saatten bağımsız kalıcı kimlik (ör. "ogretmen-1"; öğlencide "s2-ogretmen-1")."""
        if self.kind == "ek":
            # Aynı ad ve saatteki ikinci, üçüncü ek zil "-2", "-3" ile ayrılır; ilkinin kimliği değişmez.
            return f"ek-{self.label}-{self.time_str}" + (f"-{self.dup}" if self.dup > 1 else "")
        return f"{'s2-' if self.shift == 2 else ''}{self.kind}-{self.lesson}"

    @property
    def time_str(self) -> str:
        return fmt_hm(self.minute)

    @property
    def key(self) -> str:
        if self.kind == "ek":
            return f"{self.minute}-ek-{self.index}-{self.label}"
        return f"{self.minute}-{self.kind}-{self.shift}-{self.lesson}-{self.label}"


def auto_lessons(timing: dict) -> list:
    t = parse_hm(timing["first_lesson"])
    lessons = []
    for i in range(1, int(timing["lesson_count"]) + 1):
        start, end = t, t + int(timing["lesson_minutes"])
        if end >= DAY_MINUTES:
            break   # gece yarısını geçen dersler yok sayılır (zil saati ertesi güne kaymasın)
        lessons.append((start, end))
        gap = int(timing["lunch_minutes"]) if i == int(timing["lunch_after"]) else int(timing["break_minutes"])
        t = end + gap
    return lessons


def config_for_date(cfg: dict, date: dt.date) -> dict:
    """O tarihe bir zil programı atanmışsa, programın ayarlarıyla birleştirilmiş ayarları döndürür.
    «Bugün kısaltılmış ders» seçildiyse o günün ders saatleri kısaltılır."""
    iso = date.isoformat()
    for item in cfg.get("profile_dates", []):
        profile = cfg.get("profiles", {}).get(item.get("profile"))
        if item.get("date") == iso and profile:
            cfg = dict(cfg, **profile)
            break
    short = cfg.get("short_day") or {}
    if short.get("date") == iso:
        cfg = shortened_config(cfg, date.weekday(), short)
    return cfg


def shorten(lessons: list, lesson_minutes: int, break_minutes: int, lunch_minutes) -> dict:
    """Ders saatlerini kısaltır: ilk ders aynı saatte başlar, ders sayısı aynı kalır.
    Öğle arası (30 dk ve üzeri en uzun ara) yerinde kalır; süresi lunch_minutes olur (None = aynı)."""
    gaps = [lessons[i + 1][0] - lessons[i][1] for i in range(len(lessons) - 1)]
    lunch_after, lunch_len = 0, 0
    if gaps and max(gaps) >= 30:
        lunch_after = gaps.index(max(gaps)) + 1
        lunch_len = max(gaps) if lunch_minutes is None else int(lunch_minutes)
    return {"first_lesson": fmt_hm(lessons[0][0]), "lesson_count": len(lessons),
            "lesson_minutes": int(lesson_minutes), "break_minutes": int(break_minutes),
            "lunch_after": lunch_after, "lunch_minutes": lunch_len}


def shortened_config(cfg: dict, weekday: int, short: dict) -> dict:
    out = dict(cfg)
    lesson_minutes = int(short.get("lesson_minutes", 30))
    break_minutes = int(short.get("break_minutes", cfg["timing"].get("break_minutes", 10)))
    lunch = short.get("lunch_minutes")
    lessons = lessons_for_weekday(cfg, weekday)
    if lessons:
        out["timing"] = dict(cfg["timing"], **shorten(lessons, lesson_minutes, break_minutes, lunch))
        out["schedule_mode"], out["day_overrides"] = "auto", {}
    second = cfg.get("second_shift") or {}
    if second.get("enabled"):
        lessons2 = second_shift_lessons(cfg)
        if lessons2:
            out["second_shift"] = dict(second, schedule_mode="auto",
                                       timing=dict(second.get("timing", {}),
                                                   **shorten(lessons2, lesson_minutes, break_minutes, lunch)))
    return out


def second_shift_lessons(cfg: dict) -> list:
    """İkili öğretimde öğlencilerin ders saatleri (kapalıysa boş liste)."""
    second = cfg.get("second_shift") or {}
    if not second.get("enabled"):
        return []
    if second.get("schedule_mode") == "manual":
        out = []
        for row in second.get("manual_lessons", []):
            try:
                out.append((parse_hm(row[0]), parse_hm(row[1])))
            except (ValueError, TypeError, IndexError):
                continue
        return sorted(out)
    try:
        return auto_lessons(dict(cfg["timing"], **second.get("timing", {})))
    except (KeyError, ValueError, TypeError):
        return []


def shifts_for_weekday(cfg: dict, weekday: int) -> list:
    """[(vardiya no, ad, dersler, zamanlama)] – tekli öğretimde tek öğe, adı boş."""
    first = lessons_for_weekday(cfg, weekday)
    second = cfg.get("second_shift") or {}
    if not second.get("enabled"):
        return [(1, "", first, cfg["timing"])]
    timing2 = dict(cfg["timing"], **second.get("timing", {}))
    return [(1, cfg.get("first_shift_name") or "Sabahçı", first, cfg["timing"]),
            (2, second.get("name") or "Öğlenci", second_shift_lessons(cfg), timing2)]


def profile_name_for_date(cfg: dict, date: dt.date):
    iso = date.isoformat()
    for item in cfg.get("profile_dates", []):
        if item.get("date") == iso and item.get("profile") in cfg.get("profiles", {}):
            return item["profile"]
    return None


def lessons_for_weekday(cfg: dict, weekday: int) -> list:
    """Verilen gün için [(başlangıç, bitiş), ...] listesi (dakika)."""
    override = cfg.get("day_overrides", {}).get(str(weekday))
    if override and isinstance(override, list):
        rows = override
    elif cfg.get("schedule_mode") == "manual":
        rows = cfg.get("manual_lessons", [])
    else:
        return auto_lessons(cfg["timing"])
    out = []
    for row in rows if isinstance(rows, list) else []:
        try:
            start, end = row
            out.append((parse_hm(start), parse_hm(end)))
        except (ValueError, TypeError):
            continue
    out.sort()
    return out


def holiday_name(cfg: dict, date: dt.date):
    """Tarih tatilse tatilin adını (boş olabilir), değilse None döndürür."""
    iso = date.isoformat()
    for h in cfg.get("holidays", []):
        start = h.get("start") or ""
        if start and start <= iso <= (h.get("end") or start) and not h.get("from"):
            return h.get("name") or "Tatil"
    return None


def half_day(cfg: dict, date: dt.date):
    """Yarım günlük tatil (ör. 28 Ekim öğleden sonra): (ad, dakika) ya da None."""
    iso = date.isoformat()
    for h in cfg.get("holidays", []):
        start = h.get("start") or ""
        if start and start <= iso <= (h.get("end") or start) and h.get("from"):
            try:
                return h.get("name") or "Yarım gün tatil", parse_hm(h["from"])
            except (ValueError, TypeError):
                continue
    return None


def is_school_day(cfg: dict, date: dt.date) -> bool:
    return date.weekday() in cfg.get("active_days", [0, 1, 2, 3, 4]) and holiday_name(cfg, date) is None


def _fill(template: str, lesson: int, minute: int) -> str:
    try:
        return template.format(ders=lesson, ders_sira=ordinal_word(lesson), saat=fmt_hm(minute)).strip()
    except (KeyError, IndexError, ValueError):
        return template.strip()


def _bell(cfg, minute, kind, lesson, variant, note, shift=1):
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
        label=BELL_NAMES[kind], note=note, sound=rotation.effective_sound(b),
        text=text, tts=bool(b.get("tts")) and cfg["tts"].get("enabled", False),
        duration=ring_seconds(b.get("duration")), volume=int(b.get("volume", 100)), shift=shift,
    )


def assembly_minutes(cfg) -> int:
    """Toplanma zili ilk dersten kaç dakika önce çalar? Kapalıysa 0."""
    t = cfg["timing"]
    if not t.get("assembly_bell"):
        return 0
    try:
        return max(1, min(120, int(t.get("assembly_minutes", DEFAULT_ASSEMBLY_MINUTES))))
    except (TypeError, ValueError, OverflowError):
        return DEFAULT_ASSEMBLY_MINUTES


def assembly_minute(cfg, first_start, shift=1, weekday=None):
    """Bu vardiyanın bu gün toplanma zilinin dakikası; çalmayacaksa None.
    Sabit saat yalnızca sabahçılar / tek grup içindir ve ilk dersten önce olmalıdır (değilse dakika ayarı)."""
    before = assembly_minutes(cfg)
    t = cfg["timing"]
    if not before or (shift == 2 and not t.get("assembly_second_shift")):
        return None
    days = t.get("assembly_days")
    if weekday is not None and isinstance(days, list) and weekday not in days:
        return None
    fixed = t.get("assembly_time") if shift == 1 else ""
    if fixed:
        try:
            minute = parse_hm(fixed)
            if minute < first_start:
                return minute
        except (TypeError, ValueError):
            pass
    # İlk ders gece yarısından hemen sonraysa (ör. 00:05) toplanma zili önceki güne düşer: çalmaz.
    return first_start - before if first_start - before >= 0 else None


def assembly_name(cfg) -> str:
    name = cfg["timing"].get("assembly_name")
    return name.strip() if isinstance(name, str) and name.strip() else BELL_NAMES["toplanma"]


def events_for_lessons(cfg: dict, lessons: list, shift=1, shift_name="", timing=None, weekday=None) -> list:
    timing = timing or cfg["timing"]
    offset = int(cfg["timing"].get("student_offset", 2))
    # Toplanma zili: ilk dersten önce çalar; ayarda istenmedikçe o sabahki öğrenci zili çalmaz.
    assembly = assembly_minute(cfg, lessons[0][0], shift, weekday) if lessons else None
    keep_student = bool(cfg["timing"].get("assembly_keep_student"))
    prefix = f"{shift_name} · " if shift_name else ""
    # Süreler ile hesaplanan programda öğle arası ayardan bilinir; elle girilen saatlerde
    # 30 dakika ve üzeri boşluk öğle arası sayılır.
    auto = lessons == auto_lessons(timing)
    lunch_after = int(timing.get("lunch_after", 0)) if int(timing.get("lunch_minutes", 0)) > 0 else 0

    def is_lunch(lesson_no, gap):
        return lesson_no == lunch_after if auto else gap >= 30

    events = []
    for i, (start, end) in enumerate(lessons, start=1):
        prev_end = lessons[i - 2][1] if i > 1 else None
        if prev_end is None and assembly is not None:
            e = _bell(cfg, assembly, "toplanma", i, "", prefix + "Öğrenciler toplanır", shift)
            e.label = assembly_name(cfg)
            events.append(e)
        if offset > 0 and (prev_end is not None or assembly is None or keep_student):
            student = start - offset
            if prev_end is None:
                e = _bell(cfg, student, "ogrenci", i, "", prefix + "Öğrenciler sınıfa girer", shift)
                # Sabah Zilleri ayarı yalnızca sabahçıların / tek grubun ilk dersi içindir.
                if shift == 1 and not cfg["timing"].get("morning_student_bell", True):
                    e.off = "Kapalı"   # Sabah Zilleri ayarından kapatıldı; listede görünür ama çalmaz
                events.append(e)
            elif student > prev_end:
                note = "Öğle arası bitmek üzere" if is_lunch(i - 1, start - prev_end) else "Teneffüs bitmek üzere"
                events.append(_bell(cfg, student, "ogrenci", i, "", prefix + note, shift))
        e = _bell(cfg, start, "ogretmen", i, "", f"{prefix}{i}. ders başlar", shift)
        if i == 1 and shift == 1 and not cfg["timing"].get("morning_teacher_bell", True):
            e.off = "Kapalı"
        events.append(e)
        if i == len(lessons):
            variant, note = "last", (f"{shift_name} dersleri biter" if shift_name else "Okul dağılır")
        else:
            gap = lessons[i][0] - end
            if is_lunch(i, gap):
                variant, note = "lunch", f"{i}. ders biter · Öğle arası ({gap} dk)"
            else:
                variant, note = "", f"{i}. ders biter · Teneffüs ({gap} dk)"
        events.append(_bell(cfg, end, "cikis", i, variant, note if variant == "last" else prefix + note, shift))
    return events


def events_for_weekday(cfg: dict, weekday: int) -> list:
    """Bir haftanın gününün bütün zilleri (tarihe bağlı tatil/kapatma uygulanmadan), sıralı."""
    events = []
    for shift, name, lessons, timing in shifts_for_weekday(cfg, weekday):
        events += events_for_lessons(cfg, lessons, shift=shift, shift_name=name, timing=timing, weekday=weekday)
    events += extra_events(cfg, weekday)
    # Elle düzenlenmiş aşırı ayarlar (ör. 00:01'deki dersin 2 dk önceki zili) günün dışına taşmasın.
    events = [e for e in events if 0 <= e.minute < DAY_MINUTES]
    events.sort(key=lambda e: (e.minute, {"cikis": 0, "ek": 1, "toplanma": 2, "ogrenci": 2, "ogretmen": 3}[e.kind]))
    return events


def extra_events(cfg: dict, weekday: int) -> list:
    out = []
    # (ad, dakika) -> listede kaçıncı kez görüldü; gün ve açık/kapalı durumundan bağımsız sayılır ki
    # aynı zilin kimliği her gün aynı kalsın.
    seen = {}
    for i, e in enumerate(cfg.get("extra_bells", [])):
        try:
            try:
                minute = parse_hm(e["time"])
            except (KeyError, ValueError):
                continue
            label = e.get("label") or "Ek Zil"
            seen[(label, minute)] = seen.get((label, minute), 0) + 1
            if not e.get("enabled", True) or weekday not in e.get("days", []):
                continue
            text = _fill(e.get("text") or "", 0, minute)
            out.append(BellEvent(
                minute=minute, kind="ek", label=label, note="Ek zil", dup=seen[(label, minute)],
                sound=e.get("sound") or "", text=text,
                tts=bool(text) and cfg["tts"].get("enabled", False),
                # «Sonuna kadar çal» seçiliyse süre sınırı yok (None): ses ya da seçilen bölümü bir kez tam çalar.
                duration=None if e.get("full") else ring_seconds(e.get("duration")),
                volume=int(e.get("volume", 100)), extra=e, index=i,
            ))
        except Exception:  # noqa: BLE001 - bozuk bir ek zil yüzünden günün bütün zilleri bozulmasın
            log.exception("Ek zil yok sayıldı (ayarı bozuk): %s", e)
    return out


def is_disabled(cfg: dict, weekday: int, bell_id: str) -> bool:
    d = cfg.get("disabled_bells", {})
    return bell_id in d.get("all", []) or bell_id in d.get(str(weekday), [])


def events_for_date(cfg: dict, date: dt.date) -> list:
    if not is_school_day(cfg, date):
        return []
    cfg = config_for_date(cfg, date)
    events = events_for_weekday(cfg, date.weekday())
    skip = cfg.get("skip_today") or {}
    skipped = skip.get("ids", []) if skip.get("date") == date.isoformat() else []
    half = half_day(cfg, date)
    for e in events:
        if e.off:
            continue
        # Yarım gün tatil: tam o dakikada biten dersin çıkış zili yine çalar.
        if half and (e.minute > half[1] or (e.minute == half[1] and e.kind != "cikis")):
            e.off = "Tatil (yarım gün)"
        elif is_disabled(cfg, date.weekday(), e.bell_id):
            e.off = "Kapalı"
        elif e.bell_id in skipped:
            e.off = "Bugün kapalı"
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
    # [(başlangıç, bitiş, vardiya adı, vardiyadaki ders no)] – ikili öğretimde iki vardiya art arda
    lessons = []
    for _, name, rows, _ in shifts_for_weekday(cfg, date.weekday()):
        lessons += [(a, b, name, i) for i, (a, b) in enumerate(rows, start=1)]
    lessons.sort()
    if not lessons:
        return ("Bugün ders yok", "Ders saati tanımlı değil", None)

    def label(name, i):
        return f"{name} · {i}. ders" if name else f"{i}. ders"

    def left_text(minutes):
        return f"{int(minutes)} dk {int((minutes % 1) * 60)} sn"

    m = now.hour * 60 + now.minute + now.second / 60
    first = lessons[0]
    if m < first[0]:
        who = f"{first[2]} dersleri" if first[2] else "İlk ders"
        return ("Dersler başlamadı", f"{who} {fmt_hm(first[0])}'da başlıyor", None)
    for k, (start, end, name, i) in enumerate(lessons):
        if start <= m < end:
            return (f"{label(name, i)} devam ediyor", f"Bitişe {left_text(end - m)}", (m - start) / (end - start))
        if k + 1 < len(lessons) and end <= m < lessons[k + 1][0]:
            nxt_start, _, nxt_name, nxt_i = lessons[k + 1]
            if nxt_name != name:   # sabahçılar bitti, öğlenciler başlayacak
                return (f"{name} dersleri bitti", f"{nxt_name} dersleri {fmt_hm(nxt_start)}'da başlıyor",
                        (m - end) / (nxt_start - end))
            kind = "Öğle arası" if nxt_start - end >= 30 else "Teneffüs"
            title = f"{name} · {kind}" if name else kind
            return (title, f"{label(nxt_name, nxt_i)}e {left_text(nxt_start - m)}", (m - end) / (nxt_start - end))
    return ("Dersler sona erdi", "İyi günler!", None)
