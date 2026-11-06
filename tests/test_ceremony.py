"""Tören (İstiklal Marşı) sırasında zillerin bekletilmesi ve oynatıcının tören durumu."""

import datetime as dt
import os
import time
import unittest

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from okul_zili import ceremony, config  # noqa: E402
from okul_zili.scheduler import HELD_GAP_SECONDS, BellScheduler  # noqa: E402

from test_schedule import FakePlayer  # noqa: E402


def run(s, start, seconds, player=None, ceremony_between=None):
    for sec in range(seconds):
        now = start + dt.timedelta(seconds=sec)
        if player is not None and ceremony_between is not None:
            a, b = ceremony_between
            player.ceremony_active = a <= now < b
        s._tick(now)


class HoldTests(unittest.TestCase):
    def setUp(self):
        self.cfg = config.default_config()   # 09:18 öğrenci, 09:20 öğretmen, 10:00 çıkış …
        self.player = FakePlayer()
        self.s = BellScheduler(lambda: self.cfg, self.player)
        self.day = dt.datetime(2026, 10, 26, 9, 17, 0)

    def test_bell_during_ceremony_rings_after_gap(self):
        # Marş 09:17:50 – 09:19:30: 09:18 öğrenci zili bekler, marştan 3 sn sonra çalar.
        cer = (self.day.replace(second=50), self.day.replace(minute=19, second=30))
        rung_at = []
        orig = self.player.ring
        t = {"now": None}

        def ring(event, announce=True):
            rung_at.append(t["now"])
            orig(event, announce)
        self.player.ring = ring
        for sec in range(4 * 60):
            now = self.day + dt.timedelta(seconds=sec)
            t["now"] = now
            self.player.ceremony_active = cer[0] <= now < cer[1]
            self.s._tick(now)
        self.assertEqual(self.player.rung, ["09:18 ogrenci", "09:20 ogretmen"])
        self.assertEqual(rung_at[0], cer[1] + dt.timedelta(seconds=HELD_GAP_SECONDS))

    def test_only_latest_held_bell_rings(self):
        # Uzun tören 09:17:30 – 09:21:00: öğrenci ve öğretmen zilleri bekler, yalnızca öğretmen zili çalar.
        run(self.s, self.day, 6 * 60, self.player,
            (self.day.replace(second=30), self.day.replace(minute=21, second=0)))
        self.assertEqual(self.player.rung, ["09:20 ogretmen"])

    def test_held_bell_dropped_when_too_late(self):
        # 15 dakikalık ses: bekleyen zilin saatinin üzerinden 5 dakikadan fazla geçti, çalmaz.
        run(self.s, self.day, 22 * 60, self.player,
            (self.day.replace(second=30), self.day.replace(minute=32)))
        self.assertEqual(self.player.rung, [])

    def test_held_bell_respects_bells_switched_off(self):
        cer = (self.day.replace(second=30), self.day.replace(minute=18, second=40))
        for sec in range(2 * 60):
            now = self.day + dt.timedelta(seconds=sec)
            self.player.ceremony_active = cer[0] <= now < cer[1]
            if now == cer[1]:
                self.cfg["auto_ring"] = False   # tören sırasında ziller kapatıldı
            self.s._tick(now)
        self.assertEqual(self.player.rung, [])

    def test_new_ceremony_in_gap_keeps_bell_waiting(self):
        # Marş bitti, 1 sn sonra ikinci tören başladı: zil ikinci törenden sonra çalar.
        a = (self.day.replace(second=30), self.day.replace(minute=18, second=20))
        b = (self.day.replace(minute=18, second=21), self.day.replace(minute=19, second=0))
        for sec in range(150):
            now = self.day + dt.timedelta(seconds=sec)
            self.player.ceremony_active = a[0] <= now < a[1] or b[0] <= now < b[1]
            self.s._tick(now)
            if now < b[1] + dt.timedelta(seconds=HELD_GAP_SECONDS):
                self.assertEqual(self.player.rung, [], now)
        self.assertEqual(self.player.rung, ["09:18 ogrenci"])


class PlayerCeremonyTests(unittest.TestCase):
    def test_ceremony_flag_and_stop(self):
        from okul_zili.audio import Player
        cfg = config.default_config()
        ended = []
        p = Player(lambda: cfg)
        p.on_ceremony_end = lambda title, ok, stopped: ended.append((title, ok, stopped))
        # Ses yok: tören hemen biter, çalınamadı bildirilir (uyarı bip sesi çalınmaz).
        p.ceremony("istiklal", "", "İstiklal Marşı")
        for _ in range(100):
            if ended:
                break
            time.sleep(0.02)
        self.assertEqual(ended, [("İstiklal Marşı", False, False)])
        self.assertFalse(p.ceremony_active)
        # Tören sürerken zamanlanmış zil kuyruğa girmez; stop() töreni kesin olarak bitirir.
        from okul_zili import audio
        orig = audio.sounds.resolve
        import threading
        opening = threading.Event()
        audio.sounds.resolve = lambda sid: (opening.set(), time.sleep(0.5), None)[2]   # ses açılırken
        try:
            p.ceremony("saygi", "", "Saygı Duruşu + İstiklal Marşı")
            self.assertTrue(p.ceremony_active)
            self.assertTrue(opening.wait(2))
            self.assertEqual(p.ceremony_info["key"], "saygi")
            self.assertFalse(p.ring_scheduled(object()))
            p.stop()
            self.assertFalse(p.ceremony_active)
            self.assertIsNone(p.ceremony_info)
            time.sleep(0.7)
            self.assertEqual(ended[-1], ("Saygı Duruşu + İstiklal Marşı", False, True))
        finally:
            audio.sounds.resolve = orig

    def test_previews_ignored_during_ceremony(self):
        from okul_zili.audio import Player
        p = Player(lambda: config.default_config())
        p._ceremony = {"gen": p._gen, "key": "istiklal", "title": "x", "started": time.monotonic(), "length": None}
        before = p._queue.qsize()
        p.preview_sound("lib:yok", 3)
        p.preview_file("/yok.opus")
        p.say("deneme", preview=True)
        self.assertEqual(p._queue.qsize(), before)


class ConfigTests(unittest.TestCase):
    def test_defaults_and_broken_values(self):
        cfg = config._sanitize(config._merge(config.DEFAULTS, {"ceremony": {"items": {"istiklal": 5}, "volume": "x"}}))
        self.assertEqual(cfg["ceremony"]["items"]["istiklal"], {"sound": "", "url": ""})
        self.assertEqual(cfg["ceremony"]["volume"], 100)
        self.assertFalse(ceremony.is_ready(cfg, "istiklal"))
        self.assertEqual(ceremony.url_of(cfg, "saygi"), "https://youtu.be/PMhKP8QyxFQ")

    def test_video_id(self):
        for url in ("https://youtu.be/s3GnMgOQs5k", "https://www.youtube.com/watch?v=s3GnMgOQs5k&t=3",
                    "https://youtube.com/shorts/s3GnMgOQs5k"):
            self.assertEqual(ceremony.video_id(url), "s3GnMgOQs5k")
        self.assertIsNone(ceremony.video_id("https://example.com/a.mp3"))


if __name__ == "__main__":
    unittest.main()


class EmbeddedSoundTests(unittest.TestCase):
    """Programla gelen (koda gömülü) sesler: ilk kullanımda çıkarılır, bozulursa yeniden çıkarılır."""

    def setUp(self):
        import base64
        import hashlib
        import tempfile
        from okul_zili import sounds
        self.sounds = sounds
        self._home = tempfile.mkdtemp()
        self._old = os.environ.get("HOME"), os.environ.get("APPDATA")
        os.environ["HOME"] = os.environ["APPDATA"] = self._home
        data = b"OggS" + bytes(range(256)) * 8
        self.fake = {"istiklal": {"ad": "İstiklal Marşı", "sure": 88.5, "boyut": len(data),
                                  "sha256": hashlib.sha256(data).hexdigest(),
                                  "veri": (base64.b64encode(data).decode()[:100], base64.b64encode(data).decode()[100:])}}
        self._orig = sounds.builtin_sounds
        sounds.builtin_sounds = lambda: self.fake

    def tearDown(self):
        self.sounds.builtin_sounds = self._orig
        for key, value in zip(("HOME", "APPDATA"), self._old):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_extract_and_repair(self):
        s = self.sounds
        p = s.resolve("gomulu:istiklal")
        self.assertEqual(p.stat().st_size, self.fake["istiklal"]["boyut"])
        self.assertEqual(s.length_seconds("gomulu:istiklal"), 88.5)
        self.assertEqual(s.display_name("gomulu:istiklal"), "İstiklal Marşı (programla gelen)")
        p.write_bytes(b"bozuk")
        self.assertEqual(s.resolve("gomulu:istiklal").stat().st_size, self.fake["istiklal"]["boyut"])
        self.assertIsNone(s.resolve("gomulu:yok"))
        self.assertTrue(s.is_missing("gomulu:yok"))

    def test_corrupt_module_data_is_rejected(self):
        self.fake["istiklal"]["sha256"] = "0" * 64
        self.assertIsNone(self.sounds.resolve("gomulu:istiklal"))

    def test_ceremony_defaults_to_embedded_sound(self):
        cfg = config.default_config()
        self.assertEqual(ceremony.sound_of(cfg, "istiklal"), "gomulu:istiklal")
        self.assertTrue(ceremony.is_ready(cfg, "istiklal"))
        self.assertEqual(ceremony.sound_of(cfg, "saygi"), "")   # bu ses gömülü değil: indirme önerilir
        cfg["ceremony"]["items"]["istiklal"]["sound"] = "lib:baska"
        self.assertEqual(ceremony.sound_of(cfg, "istiklal"), "lib:baska")
