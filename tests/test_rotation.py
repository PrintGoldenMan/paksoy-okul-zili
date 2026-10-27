import datetime as dt
import os
import random
import shutil
import tempfile
import unittest

from okul_zili import config, library, rotation, schedule


class RotationTests(unittest.TestCase):
    def setUp(self):
        self._home = tempfile.mkdtemp()
        self._old = os.environ.get("HOME"), os.environ.get("APPDATA")
        os.environ["HOME"] = os.environ["APPDATA"] = self._home
        library._library = None
        lib = library.get_library()
        self.ids = []
        for name in ("Bir", "İki", "Üç", "Dört"):
            item_id, target = lib.new_target(name)
            target.write_bytes(b"x")
            lib.add(item_id, target, name)
            self.ids.append(library.PREFIX + item_id)
        self.cfg = config.default_config()
        self.bell = self.cfg["bells"]["ogretmen"]
        self.bell["sound"] = self.ids[3]
        self.bell["rotation"].update(enabled=True, period="week", pool=self.ids[:3])

    def tearDown(self):
        for key, value in zip(("HOME", "APPDATA"), self._old):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        library._library = None
        shutil.rmtree(self._home, ignore_errors=True)

    def test_period_keys(self):
        d = dt.date(2026, 10, 27)   # salı, 44. hafta
        self.assertEqual(rotation.period_key("day", d), "2026-10-27")
        self.assertEqual(rotation.period_key("week", d), "2026-W44")
        self.assertEqual(rotation.period_key("week", dt.date(2026, 11, 1)), "2026-W44")  # pazar: aynı hafta
        self.assertEqual(rotation.period_key("week", dt.date(2026, 11, 2)), "2026-W45")  # pazartesi: yeni hafta
        self.assertEqual(rotation.period_key("month", d), "2026-10")

    def test_same_period_keeps_sound_new_period_changes_it(self):
        rng = random.Random(1)
        monday, friday, next_monday = dt.date(2026, 10, 26), dt.date(2026, 10, 30), dt.date(2026, 11, 2)
        self.assertTrue(rotation.update(self.bell, monday, rng=rng))
        first = rotation.effective_sound(self.bell)
        self.assertIn(first, self.ids[:3])
        self.assertFalse(rotation.update(self.bell, friday, rng=rng))
        self.assertEqual(rotation.effective_sound(self.bell), first)
        for week in range(30):  # her yeni haftada bir öncekinden farklı ses
            prev = rotation.effective_sound(self.bell)
            self.assertTrue(rotation.update(self.bell, next_monday + dt.timedelta(weeks=week), rng=rng))
            self.assertNotEqual(rotation.effective_sound(self.bell), prev)

    def test_single_song_pool_always_plays_it(self):
        self.bell["rotation"]["pool"] = [self.ids[0]]
        for day in range(5):
            rotation.update(self.bell, dt.date(2026, 10, 1) + dt.timedelta(weeks=day))
            self.assertEqual(rotation.effective_sound(self.bell), self.ids[0])

    def test_disabled_or_empty_pool_uses_normal_sound(self):
        self.bell["rotation"]["enabled"] = False
        self.assertEqual(rotation.effective_sound(self.bell), self.ids[3])
        self.bell["rotation"].update(enabled=True, pool=[])
        self.assertFalse(rotation.update(self.bell, dt.date(2026, 10, 27)))
        self.assertEqual(rotation.effective_sound(self.bell), self.ids[3])

    def test_deleted_song_is_skipped_and_removed_from_pool(self):
        rotation.update(self.bell, dt.date(2026, 10, 27), rng=random.Random(3))
        current = rotation.effective_sound(self.bell)
        library.get_library().remove(current[len(library.PREFIX):])
        rotation.remove_from_pools(self.cfg, current)
        self.assertNotIn(current, self.bell["rotation"]["pool"])
        self.assertTrue(rotation.update(self.bell, dt.date(2026, 10, 27)))
        self.assertIn(rotation.effective_sound(self.bell), self.ids[:3])
        self.assertNotEqual(rotation.effective_sound(self.bell), current)

    def test_schedule_uses_this_periods_sound(self):
        rotation.update_all(self.cfg, dt.date(2026, 10, 26))
        events = schedule.events_for_date(self.cfg, dt.date(2026, 10, 26))
        teacher = next(e for e in events if e.kind == "ogretmen")
        self.assertEqual(teacher.sound, rotation.effective_sound(self.bell))
        student = next(e for e in events if e.kind == "ogrenci")
        self.assertEqual(student.sound, "")   # öğrenci zilinde değişen ses kapalı


if __name__ == "__main__":
    unittest.main()
