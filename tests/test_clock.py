"""İnternet saati (clock.py): kapalıyken bilgisayar saati, açıkken ölçülen fark eklenir."""

import datetime as dt
import unittest
from unittest import mock

from okul_zili import clock, config


class ClockTests(unittest.TestCase):
    def tearDown(self):
        clock.configure(False)
        clock._offset = None
        clock._last = None

    def test_default_is_off(self):
        self.assertFalse(config.default_config()["use_network_time"])

    def test_off_uses_computer_time_even_with_offset(self):
        clock.configure(False)
        clock.set_offset(600)
        self.assertLess(abs((clock.now() - dt.datetime.now()).total_seconds()), 1)
        self.assertFalse(clock.network_active())

    def test_on_adds_measured_offset(self):
        clock.configure(True)
        self.assertFalse(clock.network_active())     # henüz ölçülmedi: bilgisayar saati
        self.assertLess(abs((clock.now() - dt.datetime.now()).total_seconds()), 1)
        clock.set_offset(-185.5)                     # bilgisayar saati 3 dk 5,5 sn ileri
        self.assertTrue(clock.network_active())
        diff = (clock.now() - dt.datetime.now()).total_seconds()
        self.assertAlmostEqual(diff, -185.5, delta=1)
        self.assertEqual(clock.today(), (dt.datetime.now() - dt.timedelta(seconds=185.5)).date())

    def test_computer_clock_jump_triggers_resync(self):
        calls = []
        clock.configure(True, on_jump=lambda: calls.append(1))
        clock.set_offset(0)
        with mock.patch.object(clock.time, "time", return_value=1000.0), \
                mock.patch.object(clock.time, "monotonic", return_value=50.0):
            clock.now()
        with mock.patch.object(clock.time, "time", return_value=1001.0), \
                mock.patch.object(clock.time, "monotonic", return_value=51.0):
            clock.now()                               # normal ilerleme: yeniden ölçüm yok
        self.assertEqual(calls, [])
        with mock.patch.object(clock.time, "time", return_value=4600.0), \
                mock.patch.object(clock.time, "monotonic", return_value=52.0):
            clock.now()                               # saat elle 1 saat ileri alındı
        self.assertEqual(calls, [1])

    def test_scheduler_rings_on_network_time(self):
        from okul_zili.scheduler import BellScheduler
        from test_schedule import FakePlayer
        cfg = config.default_config()
        player = FakePlayer()
        s = BellScheduler(lambda: cfg, player)
        clock.configure(True)
        clock.set_offset(120)        # bilgisayar saati 2 dakika geri
        real = dt.datetime(2026, 10, 26, 9, 15, 0)
        with mock.patch.object(clock.dt, "datetime", wraps=dt.datetime) as fake:
            fake.now.return_value = real
            now = clock.now()
        self.assertEqual(now, dt.datetime(2026, 10, 26, 9, 17, 0))
        for sec in range(0, 90):
            s._tick(now + dt.timedelta(seconds=sec))
        self.assertEqual(player.rung, ["09:18 ogrenci"])   # bilgisayar saatiyle 09:16'da çalar


if __name__ == "__main__":
    unittest.main()
