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
