import datetime as dt
import json
import os
import shutil
import tempfile
import unittest
import zipfile

from okul_zili import backup, config, library, meb_takvim, schedule, sounds, system, updater

MONDAY = dt.date(2026, 10, 26)


class _TempHome(unittest.TestCase):
    def setUp(self):
        self._home = tempfile.mkdtemp()
        self._old = os.environ.get("HOME"), os.environ.get("APPDATA")
        os.environ["HOME"] = os.environ["APPDATA"] = self._home
        library._library = None

    def tearDown(self):
        for key, value in zip(("HOME", "APPDATA"), self._old):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        library._library = None
        shutil.rmtree(self._home, ignore_errors=True)


class KeepAwakeTests(unittest.TestCase):
    def test_window_is_30_min_before_first_to_5_min_after_last(self):
        events = schedule.events_for_date(config.default_config(), MONDAY)   # 08:28 … 15:30
        at = lambda h, m: dt.datetime(2026, 10, 26, h, m)  # noqa: E731
        self.assertFalse(system.keep_awake_needed(events, at(7, 57)))
        self.assertTrue(system.keep_awake_needed(events, at(7, 58)))
        self.assertTrue(system.keep_awake_needed(events, at(12, 0)))
        self.assertTrue(system.keep_awake_needed(events, at(15, 35)))
        self.assertFalse(system.keep_awake_needed(events, at(15, 36)))
        self.assertFalse(system.keep_awake_needed([], at(12, 0)))


class CalendarTests(unittest.TestCase):
    def test_meb_2026_2027(self):
        cfg = config.default_config()
        cal = meb_takvim.calendar_for(dt.date(2026, 10, 27))
        self.assertIsNotNone(cal)
        cfg["holidays"] = cal["holidays"]
        # 28 Ekim: sabah zilleri çalar, 13:00'dan sonrakiler kapalı
        ev = schedule.events_for_date(cfg, dt.date(2026, 10, 28))
        self.assertEqual({e.time_str: e.off for e in ev}["12:30"], "")
        self.assertEqual({e.time_str: e.off for e in ev}["13:10"], "Tatil (yarım gün)")
        self.assertIsNone(schedule.holiday_name(cfg, dt.date(2026, 10, 28)))
        for d in (dt.date(2026, 10, 29), dt.date(2026, 11, 18), dt.date(2027, 1, 29), dt.date(2027, 3, 10),
                  dt.date(2027, 5, 18), dt.date(2027, 7, 15)):
            self.assertEqual(schedule.events_for_date(cfg, d), [], d)
        self.assertEqual(len(schedule.events_for_date(cfg, dt.date(2026, 11, 23))), 24)   # ara tatil sonrası
        self.assertEqual(meb_takvim.school_year(dt.date(2027, 3, 1)), "2026-2027")
        self.assertEqual(meb_takvim.school_year(dt.date(2027, 9, 1)), "2027-2028")


class ExtraBellTests(unittest.TestCase):
    def test_full_length_extra_bell_has_no_duration_limit(self):
        cfg = config.default_config()
        cfg["extra_bells"] = [
            {"enabled": True, "time": "08:20", "days": [0], "label": "İstiklal Marşı", "sound": "", "full": True},
            {"enabled": True, "time": "08:25", "days": [0], "label": "Eski", "sound": "", "duration": 5}]
        ev = {e.label: e for e in schedule.events_for_date(cfg, MONDAY) if e.kind == "ek"}
        self.assertIsNone(ev["İstiklal Marşı"].duration)
        self.assertEqual(ev["Eski"].duration, 5)


class PartTests(_TempHome):
    def test_part_of_library_sound(self):
        lib = library.get_library()
        item_id, target = lib.new_target("Şarkı")
        target.write_bytes(b"x")
        lib.add(item_id, target, "Şarkı", duration=200)
        sid = library.PREFIX + item_id
        self.assertEqual(sounds.part(sid), (0.0, None))
        lib.set_part(item_id, 65, 80)
        self.assertEqual(sounds.part(sid), (65.0, 80.0))
        lib.set_part(item_id, 30, None)
        self.assertEqual(sounds.part(sid), (30.0, None))
        self.assertEqual(sounds.part(""), (0.0, None))


class BackupTests(_TempHome):
    def test_full_backup_round_trip(self):
        lib = library.get_library()
        item_id, target = lib.new_target("Zil")
        target.write_bytes(b"ses-verisi")
        lib.add(item_id, target, "Zil")
        cfg = config.default_config()
        cfg["school_name"] = "Deneme Lisesi"
        cfg["bells"]["ogretmen"]["sound"] = library.PREFIX + item_id
        zpath = os.path.join(self._home, "yedek.zip")
        result = backup.create_backup(cfg, zpath)
        self.assertEqual(result["sounds"], 1)
        # her şeyi sil, sonra geri yükle
        shutil.rmtree(library.library_dir())
        library._library = None
        self.assertIsNone(sounds.resolve(library.PREFIX + item_id))
        restored = backup.restore_backup(zpath)
        self.assertEqual(restored["school_name"], "Deneme Lisesi")
        self.assertEqual(sounds.resolve(restored["bells"]["ogretmen"]["sound"]).read_bytes(), b"ses-verisi")

    def test_rejects_non_backup_and_path_traversal(self):
        bad = os.path.join(self._home, "bad.zip")
        with zipfile.ZipFile(bad, "w") as zf:
            zf.writestr("baska.txt", "x")
        with self.assertRaises(ValueError):
            backup.read_backup_info(bad)
        evil = os.path.join(self._home, "evil.zip")
        with zipfile.ZipFile(evil, "w") as zf:
            zf.writestr("ayarlar.json", json.dumps({}))
            zf.writestr("../../kotu.txt", "x")
        with self.assertRaises(ValueError):
            backup.restore_backup(evil)


class UpdaterTests(unittest.TestCase):
    def test_version_compare(self):
        self.assertGreater(updater.version_tuple("1.10.0"), updater.version_tuple("1.9.3"))
        self.assertEqual(updater.version_tuple("v1.2.0"), (1, 2, 0))
        self.assertEqual(updater.install_kind(), "source")


if __name__ == "__main__":
    unittest.main()
