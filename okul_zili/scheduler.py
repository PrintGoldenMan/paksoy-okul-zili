"""Saati izleyip zamanı gelen zilleri çalan arka plan görevi."""

import copy
import datetime as dt
import logging
import threading

from . import clock, schedule, tts

log = logging.getLogger(__name__)

# Program zil saatinden biraz sonra açılırsa/uyanırsa bu süre içinde zil yine çalar
# (Profesyonel düzeyde "grace_seconds" ile değiştirilebilir).
GRACE_SECONDS = 45
# Tören (İstiklal Marşı) sırasında gelen ziller bekletilir; tören bitince bu kadar ara verilip
# yalnızca en son bekleyen zil çalar. Zilin saatinin üzerinden HELD_MAX_SECONDS geçtiyse artık çalmaz.
HELD_GAP_SECONDS = 3
HELD_MAX_SECONDS = 5 * 60


# Zil çizelgesi hesaplanamazsa sırayla varsayılana döndürülen ayar bölümleri: yalnızca bozuk bölüm
# sıfırlanır; tatiller, okul günleri ve diğer ayarlar korunur.
FALLBACK_SECTIONS = (("holidays",), ("extra_bells",), ("profiles", "profile_dates"), ("short_day",),
                     ("day_overrides",), ("second_shift",), ("disabled_bells", "skip_today"),
                     ("timing", "schedule_mode", "manual_lessons"), ("bells",), ("tts",))


def safe_events(cfg, date):
    """schedule.events_for_date; ayarlardan biri bozuksa o bölüm varsayılana döndürülerek yeniden denenir."""
    try:
        return schedule.events_for_date(cfg, date)
    except Exception:  # noqa: BLE001 - bozuk bir ayar yüzünden bütün gün zil susmasın
        log.exception("Zil çizelgesi hesaplanamadı; bozuk ayar bölümü aranıyor")
    from . import config
    defaults = config.default_config()
    reset = {}
    for single in (True, False):
        # Önce tek tek bölümler, olmazsa birikerek (birden çok bölüm bozuk olabilir) sıfırlanır.
        for keys in FALLBACK_SECTIONS:
            trial_reset = {} if single else reset
            trial_reset.update({k: copy.deepcopy(defaults[k]) for k in keys})
            try:
                events = schedule.events_for_date(dict(cfg, **trial_reset), date)
            except Exception:  # noqa: BLE001
                continue
            log.warning("Zil çizelgesi için şu ayarlar yok sayıldı (varsayılan kullanıldı): %s",
                        ", ".join(trial_reset))
            return events
    log.error("Zil çizelgesi hesaplanamadı; varsayılan ders saatleri kullanılıyor")
    return schedule.events_for_date(defaults, date)


def _grace(cfg) -> int:
    try:
        return max(5, min(600, int(cfg.get("grace_seconds", GRACE_SECONDS))))
    except (TypeError, ValueError):
        return GRACE_SECONDS


class BellScheduler:
    def __init__(self, get_config, player, on_ring=None):
        self._get_config = get_config
        self._player = player
        self._on_ring = on_ring or (lambda event: None)
        self._fired = set()        # bugün çalınan ya da zamanı geçmiş sayılan ziller
        self._handled = set()      # gerçekten işlenen ziller (çaldı, bekletildi, kapalı diye atlandı): (tarih, anahtar)
        self._clock_version = None
        self._date = None
        self._events = []
        self._dirty = True
        self._held = []            # tören sırasında zamanı gelen ziller
        self._release_at = None    # tören bitti: bekleyen zil bu anda çalar
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._loop, name="zil-zamanlayici", daemon=True)

    def start(self):
        self._thread.start()

    def reload(self):
        """Ayarlar değiştiğinde çağrılır."""
        with self._lock:
            self._dirty = True

    def today_events(self):
        self._refresh(clock.now())
        return list(self._events)

    def next_event(self, now=None):
        now = now or clock.now()
        self._refresh(now)
        m = now.hour * 60 + now.minute
        for e in self._events:
            if e.off:
                continue
            if e.minute > m or (e.minute == m and e.key not in self._fired):
                return e
        return None

    def was_fired(self, event) -> bool:
        return event.key in self._fired

    def _refresh(self, now):
        with self._lock:
            version = clock.version()
            if not self._dirty and self._date == now.date() and version == self._clock_version:
                return
            if self._date != now.date():
                self._held.clear()
                # Saat kaynağı tarihi geri alabilir: dünün/yarının işlenen zilleri unutulmasın.
                self._handled = {h for h in self._handled if abs((h[0] - now.date()).days) <= 1}
            cfg = self._get_config()
            self._date = now.date()
            self._dirty = False
            self._clock_version = version
            self._events = safe_events(cfg, self._date)
            # Zamanı çoktan geçmiş zilleri "çalındı" say. Saat sıçradıysa (ör. internet saati geldi) bu
            # yeni saate göre yeniden hesaplanır; gerçekten çalınan ziller yine de bir daha çalmaz.
            sec = now.hour * 3600 + now.minute * 60 + now.second
            self._fired = {key for date, key in self._handled if date == self._date}
            for e in self._events:
                if sec - e.minute * 60 > _grace(cfg):
                    self._fired.add(e.key)
            if cfg["tts"].get("enabled") and cfg.get("prepare_announcements", True):
                tts.prepare_async([e.text for e in self._events if e.tts and not e.off], cfg["tts"])

    def _claim(self, event, handled):
        """Zil işaretlenir; başka iş parçacığı _fired'ı yeniden hesaplarken kaybolmasın diye kilitli."""
        with self._lock:
            if event.key in self._fired:
                return False
            self._fired.add(event.key)
            if handled:
                self._handled.add((self._date, event.key))
            return True

    def _loop(self):
        stop = threading.Event()
        while not stop.wait(0.5):
            try:
                self._tick(clock.now())
            except Exception:  # noqa: BLE001 - zamanlayıcı asla durmamalı
                log.exception("Zamanlayıcı hatası")

    @property
    def held(self):
        return list(self._held)

    def _release_held(self, now, cfg):
        """Tören bitti: bekletilen zillerden yalnızca en sonuncusu çalar (öncekiler artık geçersiz)."""
        held, self._held, self._release_at = self._held, [], None
        event = held[-1]
        for e in held[:-1]:
            log.info("Tören sırasında gelen zil atlandı (yerine daha sonraki çalıyor): %s %s", e.time_str, e.label)
        late = now.hour * 3600 + now.minute * 60 + now.second - event.minute * 60
        if late > HELD_MAX_SECONDS or late < 0:
            log.info("Tören uzun sürdü; bekleyen zil artık çalınmadı: %s %s", event.time_str, event.label)
        elif not cfg.get("auto_ring", True) or cfg.get("skip_date") == now.date().isoformat():
            log.info("Ziller kapalı; töreni bekleyen zil çalınmadı: %s %s", event.time_str, event.label)
        elif self._player.ring_scheduled(event):
            log.info("Tören bitti, bekleyen zil çalıyor: %s %s", event.time_str, event.label)
        else:
            self._held = [event]   # bu arada yeni bir tören başladı: yine beklesin

    def _tick(self, now):
        self._refresh(now)
        cfg = self._get_config()
        sec = now.hour * 3600 + now.minute * 60 + now.second
        grace = _grace(cfg)
        take = getattr(self._player, "take_preempted", None)
        preempted = take() if take is not None else []
        if preempted:
            # Tören, kuyrukta çalmayı bekleyen zili kesti: zil diğer bekletilenler gibi tören bitince çalar.
            for e in preempted:
                log.info("Tören başladı; sıradaki zil tören bitince çalacak: %s %s", e.time_str, e.label)
            self._held = sorted(self._held + preempted, key=lambda e: e.minute)
            self._release_at = None
        if self._held:
            if getattr(self._player, "ceremony_active", False):
                self._release_at = None
            elif self._release_at is None:
                self._release_at = now + dt.timedelta(seconds=HELD_GAP_SECONDS)
            elif now >= self._release_at:
                self._release_held(now, cfg)
        for e in self._events:
            if e.key in self._fired:
                continue
            delta = sec - e.minute * 60
            if 0 <= delta <= grace:
                if not self._claim(e, handled=True):
                    continue
                if e.off:
                    log.info("Zil kapalı (%s), çalınmadı: %s %s", e.off, e.time_str, e.label)
                elif not cfg.get("auto_ring", True):
                    log.info("Otomatik zil kapalı, çalınmadı: %s %s", e.time_str, e.label)
                elif cfg.get("skip_date") == now.date().isoformat():
                    log.info("Bugün ziller kapalı, çalınmadı: %s %s", e.time_str, e.label)
                elif self._player.ring_scheduled(e):
                    log.info("Zil çalıyor: %s %s", e.time_str, e.label)
                else:
                    log.info("Tören sürüyor; zil tören bitince çalacak: %s %s", e.time_str, e.label)
                    self._held.append(e)
                    self._release_at = None
                self._on_ring(e)
            elif delta > grace:
                self._claim(e, handled=False)
