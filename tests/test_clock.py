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
        self._at(1000.0, 50.0)
        self._at(1001.0, 51.0)                       # normal ilerleme: yeniden ölçüm yok
        self.assertEqual(calls, [])
        self._at(4600.0, 52.0)                       # saat elle 1 saat ileri alındı
        self.assertEqual(calls, [1])

    @staticmethod
    def _at(wall, steady):
        with mock.patch.object(clock.time, "time", return_value=wall), \
                mock.patch.object(clock, "_steady", return_value=steady):
            clock.now()

    def test_manual_jump_offline_keeps_network_time_continuous(self):
        calls = []
        clock.configure(True, on_jump=lambda: calls.append(1))
        clock.set_offset(100)
        self._at(1000.0, 50.0)                       # internet saati: 1100
        self._at(4600.0, 51.0)                       # saat elle 1 saat ileri alındı, internet yok
        self.assertEqual(calls, [1])
        self.assertAlmostEqual(4600.0 + clock.offset(), 1101.0)   # internet saati kesintisiz
        self._at(4602.0, 53.0)                       # sonrası normal: yeni atlama yok
        self.assertEqual(calls, [1])
        self.assertAlmostEqual(clock.offset(), -3499.0)

    def test_suspend_is_not_a_jump(self):
        calls = []
        clock.configure(True, on_jump=lambda: calls.append(1))
        clock.set_offset(100)
        self._at(1000.0, 50.0)
        self._at(4600.0, 3650.0)                     # bir saat uyku: iki saat de ilerledi
        self.assertEqual(calls, [])
        self.assertEqual(clock.offset(), 100.0)

    def test_steady_clock_counts_suspend_on_linux(self):
        if getattr(clock.time, "CLOCK_BOOTTIME", None) is None:
            self.skipTest("CLOCK_BOOTTIME yok")
        with mock.patch.object(clock.time, "clock_gettime", return_value=123.0) as fake:
            self.assertEqual(clock._steady(), 123.0)
        fake.assert_called_once_with(clock.time.CLOCK_BOOTTIME)

    def test_version_changes_only_when_program_time_moves(self):
        v = clock.version()
        clock.set_offset(-1200)                      # kapalıyken ölçüm programın saatini değiştirmez
        self.assertEqual(clock.version(), v)
        clock.configure(True)
        self.assertEqual(clock.version(), v + 1)
        clock.set_offset(-1199.5)                    # küçük düzeltme: sıçrama sayılmaz
        self.assertEqual(clock.version(), v + 1)
        clock.set_offset(-1100)
        self.assertEqual(clock.version(), v + 2)
        clock.configure(False)
        self.assertEqual(clock.version(), v + 3)

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


    def _scheduler(self):
        from okul_zili.scheduler import BellScheduler
        from test_schedule import FakePlayer
        player = FakePlayer()
        cfg = config.default_config()
        return BellScheduler(lambda: cfg, player), player

    @staticmethod
    def _run(s, start, seconds, step=5):
        for sec in range(0, seconds + 1, step):
            s._tick(start + dt.timedelta(seconds=sec))

    def test_bells_ring_when_network_time_arrives_after_first_tick(self):
        # Bilgisayar saati 20 dk ileri: ilk denetimde (08:45) 08:28/08:30 geçmiş görünür; internet
        # saati gelince (08:25) yeniden hesaplanır ve ikisi de zamanında bir kez çalar.
        s, player = self._scheduler()
        clock.configure(True)
        s._tick(dt.datetime(2026, 10, 26, 8, 45, 0))
        self.assertTrue(s.was_fired(s._events[0]))      # yanlışlıkla «geçmiş» sayıldı
        clock.set_offset(-1200)
        self._run(s, dt.datetime(2026, 10, 26, 8, 25, 0), 15 * 60)
        self.assertEqual(player.rung, ["08:28 ogrenci", "08:30 ogretmen"])

    def test_offset_changes_never_ring_a_bell_twice(self):
        s, player = self._scheduler()
        clock.configure(True)
        clock.set_offset(0)
        self._run(s, dt.datetime(2026, 10, 26, 8, 27, 50), 15)   # 08:28 çaldı
        clock.set_offset(-10)                       # geri: 08:28 yine süre içinde ama çalındı
        self._run(s, dt.datetime(2026, 10, 26, 8, 27, 55), 4 * 60)
        self.assertEqual(player.rung, ["08:28 ogrenci", "08:30 ogretmen"])
        clock.set_offset(2400)                      # ileri: 09:10 kaçırıldı sayılır
        self._run(s, dt.datetime(2026, 10, 26, 9, 12, 0), 30)
        self.assertEqual(player.rung, ["08:28 ogrenci", "08:30 ogretmen"])
        clock.set_offset(600)                       # yeniden geri: 09:10 çalmamıştı, şimdi çalar
        self._run(s, dt.datetime(2026, 10, 26, 9, 5, 0), 6 * 60)
        self.assertEqual(player.rung, ["08:28 ogrenci", "08:30 ogretmen", "09:10 cikis"])
        clock.set_offset(-1200)                     # çalınan ziller bir daha çalmaz
        self._run(s, dt.datetime(2026, 10, 26, 8, 26, 0), 45 * 60, step=15)
        self.assertEqual(player.rung, ["08:28 ogrenci", "08:30 ogretmen", "09:10 cikis"])


class OffsetChoiceTests(unittest.TestCase):
    def test_small_offset_needs_one_source(self):
        from okul_zili.system import choose_offset
        self.assertEqual(choose_offset(iter([12.5, 9999.0])), 12.5)

    def test_large_offset_needs_confirmation(self):
        from okul_zili.system import choose_offset
        self.assertIsNone(choose_offset([7200.0]))                  # tek kaynak: güvenilmez
        self.assertIsNone(choose_offset([7200.0, 18000.0]))         # kaynaklar uyuşmuyor
        self.assertEqual(choose_offset([7200.0, 18000.0, 7215.0]), 7200.0)
        self.assertEqual(choose_offset([-3600.0, 2.0]), 2.0)        # yanlış kaynak atlanır
        self.assertIsNone(choose_offset([3.0], previous=-1200.0))   # öncekinden çok farklı
        # Pili bitmiş bilgisayar: yıllarca fark doğrulandıktan sonra tek kaynak yeter.
        years = 3 * 365 * 86400.0
        self.assertEqual(choose_offset([years + 1, years - 2]), years + 1)
        self.assertEqual(choose_offset([years + 3], previous=years), years + 3)

    def test_stops_measuring_once_accepted(self):
        from okul_zili.system import choose_offset
        asked = []

        def sources():
            for v in (7200.0, 7201.0, 7202.0):
                asked.append(v)
                yield v
        self.assertEqual(choose_offset(sources()), 7200.0)
        self.assertEqual(asked, [7200.0, 7201.0])

    def test_internet_clock_offset_uses_http_when_sntp_blocked(self):
        from okul_zili import system
        measured = []
        with mock.patch.object(system, "_sntp_offset", side_effect=OSError), \
                mock.patch.object(system, "_http_offset", side_effect=[7200.4, 7199.6]):
            self.assertEqual(system.internet_clock_offset(None, measured), 7200.4)
        self.assertEqual(measured, [7200.4, 7199.6])
        with mock.patch.object(system, "_sntp_offset", side_effect=OSError), \
                mock.patch.object(system, "_http_offset", side_effect=[7200.4, OSError]):
            self.assertIsNone(system.internet_clock_offset())


if __name__ == "__main__":
    unittest.main()
