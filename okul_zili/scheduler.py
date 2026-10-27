"""Saati izleyip zamanı gelen zilleri çalan arka plan görevi."""

import datetime as dt
import logging
import threading

from . import schedule, tts

log = logging.getLogger(__name__)

# Program zil saatinden biraz sonra açılırsa/uyanırsa bu süre içinde zil yine çalar.
GRACE_SECONDS = 45


class BellScheduler:
    def __init__(self, get_config, player, on_ring=None):
        self._get_config = get_config
        self._player = player
        self._on_ring = on_ring or (lambda event: None)
        self._fired = set()
        self._date = None
        self._events = []
        self._dirty = True
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._loop, name="zil-zamanlayici", daemon=True)

    def start(self):
        self._thread.start()

    def reload(self):
        """Ayarlar değiştiğinde çağrılır."""
        with self._lock:
            self._dirty = True

    def today_events(self):
        self._refresh(dt.datetime.now())
        return list(self._events)

    def next_event(self, now=None):
        now = now or dt.datetime.now()
        self._refresh(now)
        m = now.hour * 60 + now.minute
        for e in self._events:
            if e.minute > m or (e.minute == m and e.key not in self._fired and now.second < GRACE_SECONDS):
                return e
        return None

    def was_fired(self, event) -> bool:
        return event.key in self._fired

    def _refresh(self, now):
        with self._lock:
            if not self._dirty and self._date == now.date():
                return
            if self._date != now.date():
                self._fired.clear()
            cfg = self._get_config()
            self._date = now.date()
            self._events = schedule.events_for_date(cfg, self._date)
            self._dirty = False
            # Program açıldığında zamanı çoktan geçmiş zilleri "çalındı" say.
            sec = now.hour * 3600 + now.minute * 60 + now.second
            for e in self._events:
                if sec - e.minute * 60 > GRACE_SECONDS:
                    self._fired.add(e.key)
            if cfg["tts"].get("enabled"):
                tts.prepare_async([e.text for e in self._events if e.tts], cfg["tts"])

    def _loop(self):
        stop = threading.Event()
        while not stop.wait(0.5):
            try:
                self._tick(dt.datetime.now())
            except Exception:  # noqa: BLE001 - zamanlayıcı asla durmamalı
                log.exception("Zamanlayıcı hatası")

    def _tick(self, now):
        self._refresh(now)
        cfg = self._get_config()
        sec = now.hour * 3600 + now.minute * 60 + now.second
        for e in self._events:
            if e.key in self._fired:
                continue
            delta = sec - e.minute * 60
            if 0 <= delta <= GRACE_SECONDS:
                self._fired.add(e.key)
                if not cfg.get("auto_ring", True):
                    log.info("Otomatik zil kapalı, çalınmadı: %s %s", e.time_str, e.label)
                elif cfg.get("skip_date") == now.date().isoformat():
                    log.info("Bugün ziller kapalı, çalınmadı: %s %s", e.time_str, e.label)
                else:
                    log.info("Zil çalıyor: %s %s", e.time_str, e.label)
                    self._player.ring(e)
                self._on_ring(e)
            elif delta > GRACE_SECONDS:
                self._fired.add(e.key)
