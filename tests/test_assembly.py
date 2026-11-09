"""Toplanma zili: açıksa ilk dersten 10 dk önce çalar, o sabahki öğrenci zili (08:28) çalmaz."""

import datetime as dt
import unittest

from okul_zili import config, schedule
from okul_zili.scheduler import BellScheduler

from test_schedule import FakePlayer

MONDAY = dt.date(2026, 10, 26)


def morning(cfg):
    return [(e.time_str, e.kind) for e in schedule.events_for_date(cfg, MONDAY) if e.minute < 9 * 60]


class AssemblyBellTests(unittest.TestCase):
    def setUp(self):
        self.cfg = config.default_config()

    def test_off_by_default(self):
        self.assertFalse(self.cfg["timing"]["assembly_bell"])
        self.assertEqual(morning(self.cfg), [("08:28", "ogrenci"), ("08:30", "ogretmen")])

    def test_replaces_morning_student_bell(self):
        self.cfg["timing"]["assembly_bell"] = True
        self.assertEqual(morning(self.cfg), [("08:20", "toplanma"), ("08:30", "ogretmen")])
        events = schedule.events_for_date(self.cfg, MONDAY)
        # Sonraki derslerin öğrenci zilleri değişmez
        self.assertIn(("09:18", "ogrenci"), [(e.time_str, e.kind) for e in events])
        bell = next(e for e in events if e.kind == "toplanma")
        self.assertEqual(bell.label, "Toplanma Zili")
        self.assertEqual(bell.sound, config.DEFAULT_BELL_SOUND)
        self.assertEqual(bell.bell_id, "toplanma-1")

    def test_follows_first_lesson_and_minutes(self):
        self.cfg["timing"].update(assembly_bell=True, first_lesson="08:40", assembly_minutes=15)
        self.assertEqual(morning(self.cfg)[0], ("08:25", "toplanma"))
        self.cfg["timing"]["assembly_minutes"] = "bozuk"
        self.assertEqual(morning(self.cfg)[0], ("08:30", "toplanma"))   # varsayılan 10 dk

    def test_only_morning_shift(self):
        self.cfg["timing"].update(assembly_bell=True, first_lesson="07:40", lesson_count=6, lunch_after=0,
                                  lunch_minutes=0)
        self.cfg["second_shift"]["enabled"] = True
        kinds = {(e.shift, e.kind) for e in schedule.events_for_date(self.cfg, MONDAY)}
        self.assertIn((1, "toplanma"), kinds)
        self.assertNotIn((2, "toplanma"), kinds)
        self.assertIn((2, "ogrenci"), kinds)   # öğlencinin ilk öğrenci zili çalar

    def test_scheduler_rings_assembly(self):
        self.cfg["timing"]["assembly_bell"] = True
        player = FakePlayer()
        s = BellScheduler(lambda: self.cfg, player)
        start = dt.datetime(2026, 10, 26, 8, 19, 0)
        for sec in range(0, 12 * 60):
            s._tick(start + dt.timedelta(seconds=sec))
        self.assertEqual(player.rung, ["08:20 toplanma", "08:30 ogretmen"])

    def test_disable_today_from_bell_list(self):
        self.cfg["timing"]["assembly_bell"] = True
        self.cfg["skip_today"] = {"date": MONDAY.isoformat(), "ids": ["toplanma-1"]}
        bell = next(e for e in schedule.events_for_date(self.cfg, MONDAY) if e.kind == "toplanma")
        self.assertTrue(bell.off)


if __name__ == "__main__":
    unittest.main()


class AssemblyAdvancedTests(unittest.TestCase):
    """Uzman / Profesyonel ayarları: ad, sabit saat, günler, öğrenci zili, öğlenciler."""

    def setUp(self):
        self.cfg = config.default_config()
        self.cfg["timing"]["assembly_bell"] = True

    def test_fixed_time_and_name(self):
        self.cfg["timing"].update(assembly_time="08:15", assembly_name="Bayrak Töreni Zili")
        first = schedule.events_for_date(self.cfg, MONDAY)[0]
        self.assertEqual((first.time_str, first.kind, first.label), ("08:15", "toplanma", "Bayrak Töreni Zili"))
        self.assertEqual(first.bell_id, "toplanma-1")   # ad değişse de kalıcı kimlik aynı

    def test_fixed_time_after_first_lesson_falls_back(self):
        self.cfg["timing"]["assembly_time"] = "08:45"   # ilk dersten sonra: dakika ayarı kullanılır
        self.assertEqual(morning(self.cfg)[0], ("08:20", "toplanma"))

    def test_days(self):
        self.cfg["timing"]["assembly_days"] = [0]        # yalnızca pazartesi
        self.assertEqual(morning(self.cfg)[0], ("08:20", "toplanma"))
        tuesday = [(e.time_str, e.kind) for e in schedule.events_for_date(self.cfg, MONDAY + dt.timedelta(days=1))
                   if e.minute < 9 * 60]
        self.assertEqual(tuesday, [("08:28", "ogrenci"), ("08:30", "ogretmen")])

    def test_keep_student_bell(self):
        self.cfg["timing"]["assembly_keep_student"] = True
        self.assertEqual(morning(self.cfg), [("08:20", "toplanma"), ("08:28", "ogrenci"), ("08:30", "ogretmen")])

    def test_second_shift(self):
        self.cfg["timing"].update(first_lesson="07:40", lesson_count=6, lunch_after=0, lunch_minutes=0,
                                  assembly_second_shift=True, assembly_time="07:25")
        self.cfg["second_shift"]["enabled"] = True
        bells = [(e.shift, e.time_str) for e in schedule.events_for_date(self.cfg, MONDAY) if e.kind == "toplanma"]
        # Sabit saat yalnızca sabahçılar için; öğlencilerde ilk dersten 10 dk önce
        self.assertEqual(bells, [(1, "07:25"), (2, "12:50")])

    def test_broken_values_are_sanitized(self):
        cfg = config._sanitize(config._merge(config.DEFAULTS, {"timing": {
            "assembly_days": [0, 9, "x"], "assembly_time": "25:99", "assembly_name": 5}}))
        self.assertEqual(cfg["timing"]["assembly_days"], [0])
        self.assertEqual(cfg["timing"]["assembly_time"], "")
        self.assertEqual(cfg["timing"]["assembly_name"], "Toplanma Zili")

    def test_empty_days_mean_every_day(self):
        # Elle düzenlenmiş boş liste pencerede bütün günler seçili görünür; ayar da öyle düzeltilir.
        cfg = config._sanitize(config._merge(config.DEFAULTS, {"timing": {"assembly_days": []}}))
        self.assertEqual(cfg["timing"]["assembly_days"], list(range(7)))

    def test_first_lesson_just_after_midnight(self):
        # 00:05'teki ilk dersin 10 dk öncesi önceki güne düşer: toplanma zili çalmaz, öğrenci zili çalar.
        self.cfg["timing"]["first_lesson"] = "00:05"
        self.assertIsNone(schedule.assembly_minute(self.cfg, 5))
        self.assertEqual(morning(self.cfg)[:2], [("00:03", "ogrenci"), ("00:05", "ogretmen")])
