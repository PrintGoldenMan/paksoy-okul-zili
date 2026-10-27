"""Zil ve anons seslerini sırayla çalan oynatıcı."""

import logging
import os
import queue
import sys
import threading
import time

from . import sounds, tts

log = logging.getLogger(__name__)

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

try:
    import pygame
    _HAVE_PYGAME = True
except ImportError as exc:
    log.error("pygame yüklü değil: %s", exc)
    _HAVE_PYGAME = False

_mixer_lock = threading.Lock()
MAX_FULL_SECONDS = 15 * 60   # «sonuna kadar» çalan ek ziller için güvenlik sınırı


def _ensure_mixer() -> bool:
    """Ses sistemini gerekirse (yeniden) başlatır. Windows açılırken ses aygıtı henüz hazır
    değilse ya da aygıt sonradan değişirse (USB/HDMI hoparlör, uyku) bir sonraki zilde tekrar denenir."""
    if not _HAVE_PYGAME:
        return False
    with _mixer_lock:
        if pygame.mixer.get_init():
            return True
        try:
            pygame.mixer.pre_init(44100, -16, 2, 1024)
            pygame.mixer.init()
            log.info("Ses sistemi başlatıldı")
            return True
        except Exception as exc:  # noqa: BLE001 - ses kartı yoksa vb.
            log.error("Ses sistemi başlatılamadı: %s", exc)
            return False


def _reset_mixer():
    with _mixer_lock:
        try:
            pygame.mixer.quit()
        except Exception:  # noqa: BLE001
            pass


_ensure_mixer()


class Player:
    """Çalma isteklerini bir kuyrukta toplar; aynı anda tek ses çalar.

    Her istek, kuyruğa eklendiği andaki "nesil" numarasını taşır. stop() nesli artırır;
    böylece çalan ses de, kuyrukta bekleyenler de kesin olarak iptal olur.
    """

    def __init__(self, get_config, on_state=None):
        self._get_config = get_config
        self._on_state = on_state or (lambda playing, text: None)
        self._queue = queue.Queue()
        self._gen = 0
        self._current_kind = None
        self.playing = False
        threading.Thread(target=self._worker, name="zil-oynatici", daemon=True).start()

    @property
    def available(self) -> bool:
        return _HAVE_PYGAME and bool(pygame.mixer.get_init())

    def ring(self, event, announce=True) -> None:
        """Bir zil olayını (schedule.BellEvent) kuyruğa ekler."""
        self._queue.put((self._gen, "event", event, announce))

    def preview_sound(self, sound_id: str, duration=None) -> None:
        """Sesi dinletir; süre verilirse zil gerçekte ne kadar çalacaksa o kadar çalar.
        Gerçek bir zil çalıyorsa onu kesmez, arkasından çalar."""
        self.stop_preview()
        self._queue.put((self._gen, "sound", sound_id, duration))

    def preview_file(self, path, start=0.0, part_end=None, duration=None) -> None:
        """Bir dosyanın belirli bölümünü dinletir (kaydetmeden önce bölüm seçerken)."""
        self.stop_preview()
        self._queue.put((self._gen, "file", str(path), (start, part_end, duration)))

    def say(self, text: str, tts_cfg=None, preview=False) -> None:
        """Metni okur. tts_cfg verilirse kayıtlı anons ayarları yerine o kullanılır (deneme için)."""
        if preview:
            self.stop_preview()
        self._queue.put((self._gen, "trysay" if preview else "say", text, tts_cfg))

    def stop(self) -> None:
        """Çalan sesi durdurur ve bekleyen tüm istekleri iptal eder (ana ekrandaki «Sustur»)."""
        self._gen += 1
        try:
            while True:
                self._queue.get_nowait()
        except queue.Empty:
            pass

    def stop_preview(self) -> None:
        """Yalnızca ayarlar penceresinden başlatılan deneme seslerini durdurur; gerçek zillere dokunmaz."""
        if self._current_kind in ("sound", "trysay", "file"):
            self.stop()
        else:
            pending = []
            try:
                while True:
                    item = self._queue.get_nowait()
                    if item[1] not in ("sound", "trysay", "file"):
                        pending.append(item)
            except queue.Empty:
                pass
            for item in pending:
                self._queue.put(item)

    # -- iç işleyiş --------------------------------------------------------

    def _cancelled(self, gen) -> bool:
        return gen != self._gen

    def _worker(self):
        while True:
            gen, kind, a, b = self._queue.get()
            if self._cancelled(gen):
                continue
            self._current_kind = kind
            cfg = self._get_config()
            try:
                if kind == "event":
                    self._play_event(cfg, a, b, gen)
                elif kind == "sound":
                    self._set_state(True, sounds.display_name(a))
                    path = sounds.resolve(a)
                    if path is None and not sounds.is_silent(a):
                        self._warning_beep(b or 3.5, gen)
                    else:
                        part_start, part_end = sounds.part(a)
                        if not self._play_file(path, cfg["master_volume"], gen, duration=b,
                                               start=part_start, part_end=part_end):
                            self._warning_beep(b or 3.5, gen)
                elif kind == "file":
                    self._set_state(True, "Bölüm dinleniyor")
                    start, part_end, duration = b
                    self._play_file(a, cfg["master_volume"], gen, duration=duration, start=start, part_end=part_end)
                elif kind in ("say", "trysay"):
                    self._set_state(True, "Anons")
                    self._announce(cfg if b is None else dict(cfg, tts=b), a, gen)
            except Exception as exc:  # noqa: BLE001 - oynatıcı asla durmamalı
                log.exception("Çalma hatası: %s", exc)
            finally:
                self._current_kind = None
                self._set_state(False, "")

    def _set_state(self, playing, text):
        self.playing = playing
        try:
            self._on_state(playing, text)
        except Exception:  # noqa: BLE001
            pass

    def _play_event(self, cfg, event, announce, gen):
        self._set_state(True, event.label)
        volume = cfg["master_volume"] * event.volume / 100
        path = sounds.resolve(event.sound)
        if sounds.is_silent(event.sound):
            pass  # yalnızca anons
        elif path is None:
            # Ses seçilmemiş ya da kütüphaneden silinmiş: zil sessiz kalmasın.
            log.warning("Zil sesi bulunamadı (%s), Windows uyarı sesi çalınıyor", event.sound or "seçilmedi")
            self._warning_beep(event.duration, gen)
        else:
            part_start, part_end = sounds.part(event.sound)
            if not self._play_file(path, volume, gen, duration=event.duration, start=part_start, part_end=part_end):
                log.warning("Zil sesi çalınamadı, Windows uyarı sesi çalınıyor: %s", path)
                self._warning_beep(event.duration, gen)
        if self._cancelled(gen):
            return
        if announce and event.tts and event.text:
            if path:
                time.sleep(cfg["tts"].get("pause_ms", 400) / 1000)
            self._announce(cfg, event.text, gen)

    def _warning_beep(self, duration, gen):
        """Zil sesi yokken yedek olarak Windows'un kendi uyarı sesini, süre boyunca saniyede bir çalar."""
        end = time.monotonic() + (duration or 3.5)
        while time.monotonic() < end and not self._cancelled(gen):
            try:
                import winsound
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            except ImportError:
                sys.stdout and sys.stdout.write("\a")
            time.sleep(1.0)

    def _announce(self, cfg, text, gen):
        if self._cancelled(gen):
            return
        path = tts.synthesize(text, cfg["tts"])
        if path is None:
            log.warning("Anons çalınamadı: %s", text)
            return
        volume = cfg["master_volume"] * cfg["tts"].get("volume", 100) / 100
        self._play_file(path, volume, gen)

    def _play_file(self, path, volume, gen, duration=None, start=0.0, part_end=None) -> bool:
        """Dosyayı çalar; çalınamazsa False döndürür.

        start / part_end: şarkının çalınacak bölümü (saniye; part_end None ise dosyanın sonuna kadar).
        duration verilirse ses tam o süre çalar: bölüm kısaysa başa (bölümün başına) sarılarak tekrarlanır,
        uzunsa sonunda yumuşakça kısılır. duration None ise bölüm bir kez, sonuna kadar çalınır."""
        if path is None or self._cancelled(gen):
            return True
        if not _ensure_mixer():
            return _fallback_play(path)
        try:
            pygame.mixer.music.load(str(path))
        except Exception as exc:  # noqa: BLE001 - bozuk dosya ya da kopmuş ses aygıtı
            log.error("Ses dosyası açılamadı (%s): %s", path, exc)
            if not pygame.mixer.get_init() or "device" in str(exc).lower():
                _reset_mixer()
            return False
        base = max(0.0, min(1.0, volume / 100))
        start = max(0.0, float(start or 0.0))
        part_len = (part_end - start) if part_end and part_end > start else None
        total = duration if duration else (part_len or MAX_FULL_SECONDS)
        fade_s = min(0.5, total * 0.2) if (duration or part_len) else 0.0

        def begin():
            pygame.mixer.music.set_volume(base)
            if start > 0:
                pygame.mixer.music.play(start=start)
            else:
                pygame.mixer.music.play()
            return time.monotonic()

        try:
            t0 = seg_t0 = begin()
        except Exception as exc:  # noqa: BLE001
            log.error("Ses çalınamadı, ses sistemi yeniden başlatılacak: %s", exc)
            _reset_mixer()
            return False
        end = t0 + total
        while True:
            time.sleep(0.02)
            if self._cancelled(gen):
                break
            now = time.monotonic()
            left = end - now
            if left <= 0:
                break   # süre doldu: kesin olarak dur
            if fade_s and left <= fade_s:
                # Sonda sesi elle kısarak yumuşak bitiş (fadeout süresi her sistemde kesin değil)
                pygame.mixer.music.set_volume(base * left / fade_s)
            segment_over = not pygame.mixer.music.get_busy() or (part_len and now - seg_t0 >= part_len)
            if segment_over:
                if duration and left > 0.05:
                    seg_t0 = begin()   # bölüm bitti ama zil süresi dolmadı: bölümün başından tekrar
                    if fade_s and left <= fade_s:
                        pygame.mixer.music.set_volume(base * left / fade_s)
                else:
                    break
        try:
            pygame.mixer.music.stop()
            pygame.mixer.music.unload()
        except Exception:  # noqa: BLE001
            pass
        return True


def _fallback_play(path) -> bool:
    """pygame kullanılamıyorsa Windows'un yerleşik WAV oynatıcısı denenir."""
    try:
        import winsound
        if str(path).lower().endswith(".wav"):
            winsound.PlaySound(str(path), winsound.SND_FILENAME)
            return True
    except ImportError:
        pass
    log.error("Ses çalınamadı (ses sistemi yok): %s", path)
    return False
