import datetime as dt
import unittest

from okul_zili import config, schedule

MONDAY = dt.date(2026, 10, 26)


def at(h, m):
    return dt.datetime(2026, 10, 26, h, m)


class DoubleShiftTests(unittest.TestCase):
    def setUp(self):
        self.cfg = config.default_config()
        t = self.cfg["timing"]
        t.update(first_lesson="07:30", lesson_count=6, lesson_minutes=40, break_minutes=10, lunch_after=0)
        self.cfg["second_shift"].update(enabled=True)
        self.cfg["second_shift"]["timing"].update(first_lesson="13:00", lesson_count=6)

    def test_both_shifts_ring_with_separate_ids(self):
        events = schedule.events_for_date(self.cfg, MONDAY)
        teacher = [e for e in events if e.kind == "ogretmen"]
        self.assertEqual([e.time_str for e in teacher],
                         ["07:30", "08:20", "09:10", "10:00", "10:50", "11:40",
                          "13:00", "13:50", "14:40", "15:30", "16:20", "17:10"])
        ids = [e.bell_id for e in events]
        self.assertEqual(len(ids), len(set(ids)))           # sabah ve öğleden sonra kimlikleri çakışmaz
        self.assertIn("s2-ogretmen-1", ids)
        last_morning = next(e for e in events if e.kind == "cikis" and e.shift == 1 and e.lesson == 6)
        self.assertEqual((last_morning.time_str, last_morning.note), ("12:20", "Sabahçı dersleri biter"))
        first_afternoon = next(e for e in events if e.kind == "ogrenci" and e.shift == 2)
        self.assertEqual((first_afternoon.time_str, first_afternoon.note), ("12:58", "Öğlenci · Öğrenciler sınıfa girer"))

    def test_disable_afternoon_bell_only(self):
        self.cfg["disabled_bells"] = {"all": ["s2-ogretmen-1"]}
        off = {(e.shift, e.bell_id): e.off for e in schedule.events_for_date(self.cfg, MONDAY)}
        self.assertEqual(off[(2, "s2-ogretmen-1")], "Kapalı")
        self.assertEqual(off[(1, "ogretmen-1")], "")

    def test_status_across_shifts(self):
        self.assertEqual(schedule.current_status(self.cfg, at(7, 0))[1], "Sabahçı dersleri 07:30'da başlıyor")
        self.assertEqual(schedule.current_status(self.cfg, at(8, 0))[0], "Sabahçı · 1. ders devam ediyor")
        title, detail, _ = schedule.current_status(self.cfg, at(12, 40))
        self.assertEqual((title, detail), ("Sabahçı dersleri bitti", "Öğlenci dersleri 13:00'da başlıyor"))
        self.assertEqual(schedule.current_status(self.cfg, at(13, 45))[0], "Öğlenci · Teneffüs")
        self.assertEqual(schedule.current_status(self.cfg, at(18, 0))[0], "Dersler sona erdi")

    def test_single_shift_unchanged(self):
        self.cfg["second_shift"]["enabled"] = False
        events = schedule.events_for_date(self.cfg, MONDAY)
        self.assertFalse(any(e.shift == 2 for e in events))
        self.assertEqual(schedule.current_status(self.cfg, at(8, 0))[0], "1. ders devam ediyor")


class ShortDayTests(unittest.TestCase):
    def test_short_day_only_today(self):
        cfg = config.default_config()      # 08:30, 8 ders, 40+10, 5. dersten sonra 40 dk öğle
        cfg["short_day"] = {"date": MONDAY.isoformat(), "lesson_minutes": 30, "break_minutes": 10,
                            "lunch_minutes": None}
        today = [e.time_str for e in schedule.events_for_date(cfg, MONDAY) if e.kind == "ogretmen"]
        self.assertEqual(today, ["08:30", "09:10", "09:50", "10:30", "11:10", "12:20", "13:00", "13:40"])
        tomorrow = [e.time_str for e in schedule.events_for_date(cfg, MONDAY + dt.timedelta(days=1))
                    if e.kind == "ogretmen"]
        self.assertEqual(tomorrow[:3], ["08:30", "09:20", "10:10"])

    def test_short_day_with_manual_lessons_and_shorter_lunch(self):
        cfg = config.default_config()
        cfg["schedule_mode"] = "manual"
        cfg["short_day"] = {"date": MONDAY.isoformat(), "lesson_minutes": 30, "break_minutes": 5,
                            "lunch_minutes": 20}
        exits = [e for e in schedule.events_for_date(cfg, MONDAY) if e.kind == "cikis"]
        self.assertEqual(exits[4].variant, "lunch")
        self.assertEqual([e.time_str for e in exits][:6], ["09:00", "09:35", "10:10", "10:45", "11:20", "12:10"])


if __name__ == "__main__":
    unittest.main()
