import datetime as dt
import unittest

from okul_zili import config, schedule
from okul_zili.scheduler import BellScheduler

# Okulun ders programındaki (10G) saatler
EXPECTED_LESSONS = [("08:30", "09:10"), ("09:20", "10:00"), ("10:10", "10:50"), ("11:00", "11:40"),
                    ("11:50", "12:30"), ("13:10", "13:50"), ("14:00", "14:40"), ("14:50", "15:30")]
MONDAY = dt.date(2026, 10, 26)


class ScheduleTests(unittest.TestCase):
    def setUp(self):
        self.cfg = config.default_config()
        self.cfg["level"] = "basit"

    def test_auto_lessons_match_timetable(self):
        got = [(schedule.fmt_hm(a), schedule.fmt_hm(b)) for a, b in schedule.auto_lessons(self.cfg["timing"])]
        self.assertEqual(got, EXPECTED_LESSONS)

    def test_manual_defaults_match_auto(self):
        self.cfg["schedule_mode"] = "manual"
        self.assertEqual(schedule.lessons_for_weekday(self.cfg, 0), schedule.auto_lessons(self.cfg["timing"]))

    def test_student_bell_two_minutes_before_each_lesson(self):
        events = schedule.events_for_date(self.cfg, MONDAY)
        students = [e.time_str for e in events if e.kind == "ogrenci"]
        self.assertEqual(students, ["08:28", "09:18", "10:08", "10:58", "11:48", "13:08", "13:58", "14:48"])
        self.assertEqual(len(events), 24)

    def test_lunch_and_last_bell_variants(self):
        events = schedule.events_for_date(self.cfg, MONDAY)
        exits = {e.time_str: e.variant for e in events if e.kind == "cikis"}
        self.assertEqual(exits["12:30"], "lunch")
        self.assertEqual(exits["15:30"], "last")
        self.assertEqual(exits["09:10"], "")

    def test_no_morning_student_bell_option(self):
        self.cfg["timing"]["morning_student_bell"] = False
        events = schedule.events_for_date(self.cfg, MONDAY)
        self.assertNotIn("08:28", [e.time_str for e in events])

    def test_weekend_and_holiday(self):
        self.assertEqual(schedule.events_for_date(self.cfg, dt.date(2026, 10, 25)), [])
        self.cfg["holidays"] = [{"name": "Cumhuriyet Bayramı", "start": "2026-10-29", "end": "2026-10-29"}]
        self.assertEqual(schedule.events_for_date(self.cfg, dt.date(2026, 10, 29)), [])
        self.assertEqual(schedule.holiday_name(self.cfg, dt.date(2026, 10, 29)), "Cumhuriyet Bayramı")

    def test_day_override(self):
        self.cfg["day_overrides"] = {"4": [["08:30", "09:00"], ["09:10", "09:40"]]}
        friday = dt.date(2026, 10, 30)
        times = [e.time_str for e in schedule.events_for_date(self.cfg, friday)]
        self.assertEqual(times, ["08:28", "08:30", "09:00", "09:08", "09:10", "09:40"])

    def test_announcement_text_uses_turkish_ordinals(self):
        self.cfg["tts"]["enabled"] = True
        events = schedule.events_for_date(self.cfg, MONDAY)
        teacher2 = next(e for e in events if e.kind == "ogretmen" and e.lesson == 2)
        self.assertEqual(teacher2.text, "Sayın öğretmenlerimiz, ikinci ders başlamıştır.")
        exit2 = next(e for e in events if e.kind == "cikis" and e.lesson == 2)
        self.assertTrue(exit2.text.startswith("İkinci ders"))
        self.assertTrue(teacher2.tts)

    def test_extra_bell(self):
        self.cfg["extra_bells"] = [{"enabled": True, "time": "08:20", "days": [0], "label": "Tören",
                                    "sound": "builtin:gong", "text": ""}]
        events = schedule.events_for_date(self.cfg, MONDAY)
        self.assertEqual((events[0].time_str, events[0].kind), ("08:20", "ek"))


class FakePlayer:
    def __init__(self):
        self.rung = []

    def ring(self, event, announce=True):
        self.rung.append(event.time_str + " " + event.kind)


class SchedulerTests(unittest.TestCase):
    def test_each_bell_rings_once_and_past_bells_are_skipped(self):
        cfg = config.default_config()
        player = FakePlayer()
        s = BellScheduler(lambda: cfg, player)
        start = dt.datetime(2026, 10, 26, 9, 15, 0)  # program 09:15'te açıldı
        for sec in range(0, 6 * 60, 1):
            s._tick(start + dt.timedelta(seconds=sec))
        self.assertEqual(player.rung, ["09:18 ogrenci", "09:20 ogretmen"])

    def test_skip_today_and_auto_off(self):
        cfg = config.default_config()
        cfg["skip_date"] = "2026-10-26"
        player = FakePlayer()
        s = BellScheduler(lambda: cfg, player)
        for sec in range(0, 4 * 60):
            s._tick(dt.datetime(2026, 10, 26, 9, 17, 0) + dt.timedelta(seconds=sec))
        self.assertEqual(player.rung, [])


if __name__ == "__main__":
    unittest.main()
