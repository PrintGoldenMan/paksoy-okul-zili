"""Zil ve anons seslerini sırayla çalan oynatıcı."""

import logging
import os
import queue
import threading
import time

from . import sounds, tts

log = logging.getLogger(__name__)

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

try:
    import pygame
    pygame.mixer.pre_init(44100, -16, 2, 1024)
    pygame.mixer.init()
    _HAVE_PYGAME = True
except Exception as exc:  # noqa: BLE001 - ses kartı yoksa vb.
    log.error("Ses sistemi başlatılamadı: %s", exc)
    _HAVE_PYGAME = False


class Player:
    """Çalma isteklerini bir kuyrukta toplar; aynı anda tek ses çalar."""

    def __init__(self, get_config, on_state=None):
        self._get_config = get_config
        self._on_state = on_state or (lambda playing, text: None)
        self._queue = queue.Queue()
        self._stop = threading.Event()
        self.playing = False
        threading.Thread(target=self._worker, name="zil-oynatici", daemon=True).start()

    @property
    def available(self) -> bool:
        return _HAVE_PYGAME

    def ring(self, event, announce=True) -> None:
        """Bir zil olayını (schedule.BellEvent) kuyruğa ekler."""
        self._queue.put(("event", event, announce))

    def preview_sound(self, sound_id: str, duration=None) -> None:
        """Sesi dinletir; süre verilirse zil gerçekte ne kadar çalacaksa o kadar çalar."""
        self.stop()
        self._queue.put(("sound", sound_id, duration))

    def say(self, text: str, tts_cfg=None) -> None:
        """Metni okur. tts_cfg verilirse kayıtlı anons ayarları yerine o kullanılır (deneme için)."""
        self._queue.put(("say", text, tts_cfg))

    def stop(self) -> None:
        """Çalan sesi durdurur ve bekleyen tüm istekleri iptal eder."""
        try:
            while True:
                self._queue.get_nowait()
        except queue.Empty:
            pass
        self._stop.set()
        if _HAVE_PYGAME:
            try:
                pygame.mixer.music.stop()
            except Exception:  # noqa: BLE001
                pass

    # -- iç işleyiş --------------------------------------------------------

    def _worker(self):
        while True:
            kind, a, b = self._queue.get()
            self._stop.clear()
            cfg = self._get_config()
            try:
                if kind == "event":
                    self._play_event(cfg, a, b)
                elif kind == "sound":
                    self._set_state(True, sounds.display_name(a))
                    self._play_file(sounds.resolve(a), cfg["master_volume"], duration=b)
                elif kind == "say":
                    self._set_state(True, "Anons")
                    self._announce(cfg if b is None else dict(cfg, tts=b), a)
            except Exception as exc:  # noqa: BLE001 - oynatıcı asla durmamalı
                log.exception("Çalma hatası: %s", exc)
            finally:
                self._set_state(False, "")

    def _set_state(self, playing, text):
        self.playing = playing
        try:
            self._on_state(playing, text)
        except Exception:  # noqa: BLE001
            pass

    def _play_event(self, cfg, event, announce):
        self._set_state(True, event.label)
        volume = cfg["master_volume"] * event.volume / 100
        path = sounds.resolve(event.sound)
        self._play_file(path, volume, duration=event.duration)
        if self._stop.is_set():
            return
        if announce and event.tts and event.text and not self._stop.is_set():
            if path:
                time.sleep(cfg["tts"].get("pause_ms", 400) / 1000)
            self._announce(cfg, event.text)

    def _announce(self, cfg, text):
        path = tts.synthesize(text, cfg["tts"])
        if path is None:
            log.warning("Anons çalınamadı: %s", text)
            return
        volume = cfg["master_volume"] * cfg["tts"].get("volume", 100) / 100
        self._play_file(path, volume)

    def _play_file(self, path, volume, duration=None):
        """Dosyayı çalar. duration (saniye) verilirse ses o süre boyunca çalar:
        kısa sesler başa sarılarak tekrarlanır, uzun sesler sonunda yumuşakça kısılır."""
        if path is None or self._stop.is_set():
            return
        if not _HAVE_PYGAME:
            _fallback_play(path)
            return
        pygame.mixer.music.load(str(path))
        pygame.mixer.music.set_volume(max(0.0, min(1.0, volume / 100)))
        if duration:
            pygame.mixer.music.play(loops=-1)
            end = time.monotonic() + duration
            fade_s = min(0.5, duration * 0.2)
        else:
            pygame.mixer.music.play()
            end = None
        while pygame.mixer.music.get_busy():
            if self._stop.wait(0.02):
                pygame.mixer.music.stop()
                break
            if end is not None:
                left = end - time.monotonic()
                if left <= 0:
                    pygame.mixer.music.stop()   # süre doldu: kesin olarak dur
                    break
                if left <= fade_s:
                    # Sonda sesi elle kısarak yumuşak bitiş (fadeout süresi her sistemde kesin değil)
                    pygame.mixer.music.set_volume(max(0.0, min(1.0, volume / 100)) * left / fade_s)
        try:
            pygame.mixer.music.unload()
        except Exception:  # noqa: BLE001
            pass


def _fallback_play(path):
    """pygame yoksa Windows'un yerleşik WAV oynatıcısı denenir."""
    try:
        import winsound
        if str(path).lower().endswith(".wav"):
            winsound.PlaySound(str(path), winsound.SND_FILENAME)
    except ImportError:
        log.error("Ses çalınamadı (ses sistemi yok): %s", path)
