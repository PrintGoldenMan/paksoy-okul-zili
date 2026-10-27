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
        self.assertEqual(next(e for e in events if e.time_str == "08:28").off, "Kapalı")

    def test_morning_bells_can_be_disabled_separately(self):
        self.cfg["timing"]["morning_teacher_bell"] = False
        off = {e.time_str: e.off for e in schedule.events_for_date(self.cfg, MONDAY)}
        self.assertEqual((off["08:28"], off["08:30"], off["09:20"]), ("", "Kapalı", ""))
        self.cfg["timing"]["morning_student_bell"] = False
        off = {e.time_str: e.off for e in schedule.events_for_date(self.cfg, MONDAY)}
        self.assertEqual((off["08:28"], off["08:30"], off["09:18"]), ("Kapalı", "Kapalı", ""))

    def test_disabled_bells_every_day_and_single_day(self):
        self.cfg["disabled_bells"] = {"all": ["cikis-8"], "0": ["ogrenci-6"]}
        mon = {e.time_str: e.off for e in schedule.events_for_date(self.cfg, MONDAY)}
        self.assertEqual(mon["15:30"], "Kapalı")
        self.assertEqual(mon["13:08"], "Kapalı")
        self.assertEqual(mon["13:10"], "")
        tue = {e.time_str: e.off for e in schedule.events_for_date(self.cfg, MONDAY + dt.timedelta(days=1))}
        self.assertEqual(tue["13:08"], "")
        self.assertEqual(tue["15:30"], "Kapalı")

    def test_skip_single_bell_today_only(self):
        self.cfg["skip_today"] = {"date": MONDAY.isoformat(), "ids": ["ogretmen-1"]}
        mon = {e.time_str: e.off for e in schedule.events_for_date(self.cfg, MONDAY)}
        self.assertEqual(mon["08:30"], "Bugün kapalı")
        tue = {e.time_str: e.off for e in schedule.events_for_date(self.cfg, MONDAY + dt.timedelta(days=1))}
        self.assertEqual(tue["08:30"], "")

    def test_profile_assigned_to_date(self):
        snap = config.profile_snapshot(self.cfg)
        snap["timing"]["lesson_minutes"] = 30
        self.cfg["profiles"] = {"Kısa": snap}
        self.cfg["profile_dates"] = [{"date": MONDAY.isoformat(), "profile": "Kısa"}]
        mon = [e.time_str for e in schedule.events_for_date(self.cfg, MONDAY) if e.kind == "cikis"]
        self.assertEqual(mon[0], "09:00")
        tue = [e.time_str for e in schedule.events_for_date(self.cfg, MONDAY + dt.timedelta(days=1))
               if e.kind == "cikis"]
        self.assertEqual(tue[0], "09:10")

    def test_ring_duration_default_and_limits(self):
        events = schedule.events_for_date(self.cfg, MONDAY)
        self.assertTrue(all(e.duration == 3.5 for e in events))
        self.cfg["bells"]["ogretmen"]["duration"] = 99
        self.cfg["bells"]["ogrenci"]["duration"] = "7,5"
        events = schedule.events_for_date(self.cfg, MONDAY)
        self.assertEqual({e.kind: e.duration for e in events}, {"ogrenci": 7.5, "ogretmen": 30.0, "cikis": 3.5})
        self.assertEqual(config.ring_seconds(0), 0.5)

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

    def test_disabled_bell_does_not_ring(self):
        cfg = config.default_config()
        cfg["timing"]["morning_teacher_bell"] = False
        cfg["skip_today"] = {"date": "2026-10-26", "ids": ["ogrenci-1"]}
        player = FakePlayer()
        s = BellScheduler(lambda: cfg, player)
        for sec in range(0, 46 * 60):
            s._tick(dt.datetime(2026, 10, 26, 8, 25, 0) + dt.timedelta(seconds=sec))
        self.assertEqual(player.rung, ["09:10 cikis"])
        self.assertEqual(s.next_event(dt.datetime(2026, 10, 26, 8, 0)).time_str, "09:10")

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
