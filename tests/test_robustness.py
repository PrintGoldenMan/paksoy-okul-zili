"""Bozuk ayar dosyaları, tören sırasında kuyruktaki ziller, güncelleme ve bekçi dosyaları, ayar birleştirme."""

import datetime as dt
import io
import json
import os
import shutil
import tempfile
import threading
import time
import unittest
import xml.etree.ElementTree as ET
from unittest import mock

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from okul_zili import backup, config, downloader, library, schedule, system, updater  # noqa: E402
from okul_zili.scheduler import BellScheduler, safe_events  # noqa: E402

from test_schedule import FakePlayer  # noqa: E402

MONDAY = dt.date(2026, 10, 26)


def _clean(cfg):
    return config._sanitize(config._merge(config.DEFAULTS, cfg))


class HolidaySanitizeTests(unittest.TestCase):
    def test_invalid_holidays_dropped_valid_normalized(self):
        cfg = _clean({"holidays": [
            {"start": "2026-10-29", "end": 5, "name": "bozuk bitiş"},
            {"start": "2026-11-02", "end": "2026-11-03", "name": 7},
            {"start": "dün"},
            {"start": "2026-10-28", "from": "25:00", "name": "bozuk saat"},
            {"start": "2026-10-28", "from": "13.00", "name": "Yarım gün"},
            {"start": "2026-12-01", "end": "2026-11-01"},
            {"start": "2026-12-10", "end": ""},
        ]})
        self.assertEqual(cfg["holidays"], [
            {"start": "2026-11-02", "end": "2026-11-03", "name": "Tatil"},
            {"start": "2026-10-28", "end": "2026-10-28", "from": "13:00", "name": "Yarım gün"},
            {"start": "2026-12-10", "end": "2026-12-10"},
        ])
        self.assertEqual(schedule.holiday_name(cfg, dt.date(2026, 11, 3)), "Tatil")
        self.assertEqual(schedule.half_day(cfg, dt.date(2026, 10, 28)), ("Yarım gün", 13 * 60))

    def test_scheduler_fallback_keeps_rest_of_config(self):
        # Ayar dosyası temizlenmeden gelmiş bozuk tatil: yalnızca tatiller yok sayılır,
        # Pazartesiye özel ders saatleri korunur (eskiden bütün ayarlar varsayılana dönüyordu).
        cfg = config.default_config()
        cfg["holidays"] = [{"start": "2026-10-20", "end": 5}]
        cfg["day_overrides"] = {"0": [["09:00", "09:40"]]}
        with self.assertLogs("okul_zili.scheduler", "WARNING"):
            events = safe_events(cfg, MONDAY)
        self.assertEqual([e.time_str for e in events], ["08:58", "09:00", "09:40"])

    def test_scheduler_fallback_keeps_holidays_when_other_section_broken(self):
        cfg = config.default_config()
        cfg["holidays"] = [{"start": MONDAY.isoformat(), "end": MONDAY.isoformat(), "name": "Tatil"}]
        cfg["short_day"] = {"date": MONDAY.isoformat(), "lesson_minutes": "otuz"}
        self.assertEqual(safe_events(cfg, MONDAY), [])   # tatil korunur: zil yok
        cfg["holidays"] = []
        with self.assertLogs("okul_zili.scheduler", "WARNING"):
            events = safe_events(cfg, MONDAY)
        self.assertEqual(events[1].time_str, "08:30")


class ExtraBellTests(unittest.TestCase):
    def test_sanitize_fields(self):
        cfg = _clean({"extra_bells": [
            {"time": "08:20", "days": [0, "1", 9], "text": None, "volume": "yüksek", "duration": "uzun",
             "label": 5},
            {"time": "08:25", "days": [0], "volume": float("inf"), "duration": float("nan")},
        ]})
        a, b = cfg["extra_bells"]
        self.assertEqual((a["days"], a["text"], a["volume"], a["duration"], a["label"]),
                         ([0], "", 100, config.DEFAULT_RING_SECONDS, ""))
        self.assertEqual((b["volume"], b["duration"]), (100, config.DEFAULT_RING_SECONDS))

    def test_broken_extra_bell_skipped_alone(self):
        cfg = config.default_config()
        cfg["extra_bells"] = [{"time": "08:20", "days": [0], "volume": "yüksek"},
                              {"time": "08:21", "days": [0], "label": "Sağlam"}]
        with self.assertLogs("okul_zili.schedule", "ERROR"):
            events = schedule.extra_events(cfg, 0)
        self.assertEqual([e.label for e in events], ["Sağlam"])

    def test_two_extra_bells_same_minute_both_ring(self):
        cfg = config.default_config()
        cfg["extra_bells"] = [{"time": "09:05", "days": [0], "sound": "a"},
                              {"time": "09:05", "days": [0], "sound": "b"}]
        events = schedule.extra_events(cfg, 0)
        self.assertEqual(len({e.key for e in events}), 2)
        self.assertEqual(events[0].bell_id, "ek-Ek Zil-09:05")   # kalıcı kimlik değişmedi
        player = FakePlayer()
        s = BellScheduler(lambda: cfg, player)
        for sec in range(90):
            s._tick(dt.datetime(2026, 10, 26, 9, 4, 30) + dt.timedelta(seconds=sec))
        self.assertEqual(player.rung.count("09:05 ek"), 2)


class InfinityTests(unittest.TestCase):
    def setUp(self):
        self._home = tempfile.mkdtemp()
        self._old = {k: os.environ.get(k) for k in ("HOME", "APPDATA", "XDG_DATA_HOME")}
        for k in self._old:
            os.environ[k] = self._home

    def tearDown(self):
        for k, v in self._old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self._home, ignore_errors=True)

    def test_infinity_and_nan_fall_back_to_defaults(self):
        config.paths.config_file().write_text(
            '{"ceremony": {"volume": Infinity}, "timing": {"lesson_count": Infinity, "lesson_minutes": NaN},'
            ' "master_volume": -Infinity, "short_day": {"lunch_minutes": Infinity}}', encoding="utf-8")
        cfg = config.load()
        self.assertEqual(cfg["ceremony"]["volume"], 100)
        self.assertEqual(cfg["timing"]["lesson_count"], 8)
        self.assertEqual(cfg["timing"]["lesson_minutes"], 40)
        self.assertEqual(cfg["master_volume"], 85)
        self.assertIsNone(cfg["short_day"]["lunch_minutes"])
        self.assertEqual(len(schedule.events_for_date(cfg, MONDAY)), 24)

    def test_unexpected_error_keeps_broken_file(self):
        path = config.paths.config_file()
        path.write_text('{"school_name": "X"}', encoding="utf-8")
        with mock.patch.object(config, "_sanitize", side_effect=TypeError("beklenmedik")):
            cfg = config.load()
        self.assertEqual(cfg, config.default_config())
        self.assertTrue(path.with_suffix(".bozuk.json").exists())


class PreemptedBellTests(unittest.TestCase):
    def test_ceremony_keeps_queued_scheduled_bell(self):
        from okul_zili import audio
        p = audio.Player(config.default_config)
        busy = threading.Event()
        orig = audio.sounds.resolve
        audio.sounds.resolve = lambda sid: (busy.set(), time.sleep(0.4), None)[2]
        try:
            p.preview_sound("lib:yok", 1)          # oynatıcı meşgul
            self.assertTrue(busy.wait(2))
            bell = schedule.BellEvent(minute=9 * 60 + 20, kind="ogretmen", lesson=1)
            manual = schedule.BellEvent(minute=0, kind="ogrenci")
            self.assertTrue(p.ring_scheduled(bell))   # kuyrukta, henüz çalmadı
            p.ring(manual, announce=False)           # elle çalınan zil
            p.ceremony("istiklal", "", "İstiklal Marşı")
            self.assertEqual(p.take_preempted(), [bell])
            self.assertEqual(p.take_preempted(), [])
            p.stop()
        finally:
            time.sleep(0.5)
            audio.sounds.resolve = orig

    def test_scheduler_holds_preempted_bell(self):
        cfg = config.default_config()
        player = FakePlayer()
        bell = schedule.events_for_date(cfg, MONDAY)[1]    # 08:30 öğretmen zili
        player.take_preempted = lambda: [player.preempted.pop()] if player.preempted else []
        player.preempted = [bell]
        s = BellScheduler(lambda: cfg, player)
        start = dt.datetime(2026, 10, 26, 8, 30, 5)
        for sec in range(20):
            now = start + dt.timedelta(seconds=sec)
            player.ceremony_active = sec < 10
            s._tick(now)
        self.assertEqual(player.rung, ["08:30 ogretmen"])


class FallbackPlayTests(unittest.TestCase):
    """pygame yokken sistemin oynatıcısı: «Sustur» ve süre sınırı çalmayı keser."""

    def test_cancel_and_duration_stop_player(self):
        from okul_zili import audio
        sleep = shutil.which("sleep")
        if not sleep or os.name == "nt":
            self.skipTest("sleep yok")
        with mock.patch("shutil.which", side_effect=lambda name: sleep if name == "pw-play" else None):
            t0 = time.monotonic()
            self.assertTrue(audio._fallback_play("30", cancelled=lambda: time.monotonic() - t0 > 0.2))
            self.assertLess(time.monotonic() - t0, 3)
            t0 = time.monotonic()
            self.assertTrue(audio._fallback_play("30", duration=0.3))
            self.assertLess(time.monotonic() - t0, 3)


class _Response(io.BytesIO):
    def __init__(self, data, length):
        super().__init__(data)
        self.headers = {"Content-Length": str(length)}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class DownloadLengthTests(unittest.TestCase):
    def test_truncated_update_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = updater.Path(tmp) / "kurulum.exe"
            with mock.patch.object(updater.urllib.request, "urlopen",
                                   return_value=_Response(b"x" * 1_500_000, 2_000_000)):
                with self.assertRaises(OSError):
                    updater._download("https://example.invalid/a.exe", target)
            with mock.patch.object(updater.urllib.request, "urlopen",
                                   return_value=_Response(b"x" * 1_500_000, 1_500_000)):
                updater._download("https://example.invalid/a.exe", target)

    def test_truncated_fetch_rejected(self):
        with mock.patch.object(downloader.urllib.request, "urlopen", return_value=_Response(b"abc", 10)):
            with self.assertRaises(downloader.DownloadError):
                downloader._fetch("https://example.invalid/deno.zip")
        with mock.patch.object(downloader.urllib.request, "urlopen", return_value=_Response(b"abc", 3)):
            self.assertEqual(downloader._fetch("https://example.invalid/deno.zip"), b"abc")


class WindowsUpdateScriptTests(unittest.TestCase):
    def test_script_quoting(self):
        text = updater.update_script(['del /f /q "C:\\Kullanıcılar\\Öğretmen\\%TEMP%\\eski.exe"',
                                      'start "" "C:\\Program Files (x86)\\Okul & Zili\\yeni.exe" --oz-restart'])
        lines = text.split("\r\n")
        self.assertEqual(lines[:2], ["@echo off", "chcp 65001 >nul"])
        self.assertIn("timeout /t 4", lines[2])
        self.assertEqual(lines[-1], "")
        self.assertEqual(updater._bat_path("C:\\a%b%\\x.exe"), "C:\\a%%b%%\\x.exe")

    def test_launch_writes_utf8_bat_and_passes_plain_command_line(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(updater.subprocess, "Popen") as popen, \
                mock.patch.dict(os.environ, {"ComSpec": "C:\\Windows\\system32\\cmd.exe"}):
            updater._launch_script(updater.Path(tmp), ['start "" "C:\\Öğretmen\\OkulZili.exe" --oz-restart'])
            bat = os.path.join(tmp, "guncelle.bat")
            with open(bat, "rb") as f:
                content = f.read().decode("utf-8")
            self.assertIn('start "" "C:\\Öğretmen\\OkulZili.exe" --oz-restart\r\n', content)
            cmdline = popen.call_args.args[0]
            self.assertIsInstance(cmdline, str)   # liste verilseydi tırnaklar \" olurdu
            self.assertEqual(cmdline, f'"C:\\Windows\\system32\\cmd.exe" /d /s /c ""{bat}""')
            self.assertNotIn('\\"', cmdline)

    def test_installer_without_installer_asset_opens_page(self):
        info = {"version": "9.9.9", "page": "https://example.invalid/surum", "installer": None,
                "portable": "https://example.invalid/t.exe"}
        with mock.patch.object(updater, "IS_WINDOWS", True), \
                mock.patch.object(updater, "install_kind", return_value="installer"), \
                mock.patch.object(updater.webbrowser, "open") as browser, \
                mock.patch.object(updater, "_download") as download:
            self.assertFalse(updater.prepare_and_launch(info))
        browser.assert_called_once_with("https://example.invalid/surum")
        download.assert_not_called()


class WatchdogFileTests(unittest.TestCase):
    def test_task_xml(self):
        xml = system.watchdog_task_xml("C:\\Okul & Zili\\OkulZili.exe", "OKUL\\Öğretmen",
                                       dt.datetime(2026, 11, 6, 8, 0))
        root = ET.fromstring(xml)
        ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
        self.assertEqual(root.find("t:Settings/t:ExecutionTimeLimit", ns).text, "PT0S")
        self.assertEqual(root.find("t:Settings/t:DisallowStartIfOnBatteries", ns).text, "false")
        self.assertEqual(root.find("t:Triggers/t:TimeTrigger/t:Repetition/t:Interval", ns).text, "PT5M")
        self.assertEqual(root.find("t:Actions/t:Exec/t:Command", ns).text, "C:\\Okul & Zili\\OkulZili.exe")
        self.assertEqual(root.find("t:Actions/t:Exec/t:Arguments", ns).text, "--oz-watchdog")
        self.assertEqual(root.find("t:Principals/t:Principal/t:UserId", ns).text, "OKUL\\Öğretmen")
        self.assertIsNone(ET.fromstring(system.watchdog_task_xml("C:\\x.exe")).find(
            "t:Principals/t:Principal/t:UserId", ns))
        xml.encode("utf-16")   # dosyaya UTF-16 yazılır

    def test_windows_task_up_to_date_check(self):
        exe = "C:\\Okul & Zili\\OkulZili.exe"
        current = system.watchdog_task_xml(exe)
        old = current.replace("<ExecutionTimeLimit>PT0S", "<ExecutionTimeLimit>PT72H")
        result = mock.Mock(returncode=0)
        with mock.patch.object(system.sys, "executable", exe), \
                mock.patch.object(system, "_schtasks", return_value=result):
            result.stdout = current
            self.assertTrue(system._windows_watchdog_current())
            result.stdout = old
            self.assertFalse(system._windows_watchdog_current())
            result.stdout = system.watchdog_task_xml("C:\\eski\\OkulZili.exe")
            self.assertFalse(system._windows_watchdog_current())

    def test_systemd_quoting_and_session_vars(self):
        self.assertEqual(system.systemd_quote('/a b/%h$x"\\', exec_line=True), '"/a b/%%h$$x\\"\\\\"')
        self.assertEqual(system.systemd_quote("K=%v$"), '"K=%%v$"')
        env = {"DISPLAY": ":0", "XDG_DATA_HOME": "/home/ö/%veri", "XDG_CONFIG_HOME": "/home/ö/.ayar"}
        with mock.patch.dict(os.environ, env):
            text = system.watchdog_service_text("/home/ö/Okul %Zili/okulzili")
        self.assertIn('Environment="DISPLAY=:0"', text)
        self.assertIn('Environment="XDG_DATA_HOME=/home/ö/%%veri"', text)
        self.assertIn('Environment="XDG_CONFIG_HOME=/home/ö/.ayar"', text)
        self.assertIn('ExecStart="/home/ö/Okul %%Zili/okulzili" "--oz-watchdog"', text)


class MergeTests(unittest.TestCase):
    def test_three_way_merge(self):
        base = {"level": "basit", "holidays": [], "school_name": "A",
                "bells": {"ogrenci": {"sound": "x", "rotation": {"current": "a", "key": "1"}}},
                "ceremony": {"items": {"istiklal": {"sound": ""}}}, "eski": 1}
        mine = json.loads(json.dumps(base))
        current = json.loads(json.dumps(base))
        mine["bells"]["ogrenci"]["sound"] = "y"                # yalnızca pencerede değişti
        current["level"] = "uzman"                             # yalnızca ana ekranda değişti
        current["holidays"] = [{"start": "2026-11-10"}]
        current["bells"]["ogrenci"]["rotation"] = {"current": "b", "key": "2"}
        current["ceremony"]["items"]["istiklal"]["sound"] = "lib:indirilen"
        current["yeni"] = True
        del mine["eski"]
        mine["school_name"], current["school_name"] = "B", "C"   # ikisi de değişti: pencere kazanır
        out = config.merge_changes(base, mine, current)
        self.assertEqual(out["school_name"], "B")
        self.assertEqual(out["level"], "uzman")
        self.assertEqual(out["holidays"], [{"start": "2026-11-10"}])
        self.assertEqual(out["bells"]["ogrenci"], {"sound": "y", "rotation": {"current": "b", "key": "2"}})
        self.assertEqual(out["ceremony"]["items"]["istiklal"]["sound"], "lib:indirilen")
        self.assertTrue(out["yeni"])
        self.assertNotIn("eski", out)
        out["holidays"].append(1)
        self.assertEqual(len(current["holidays"]), 1)   # kopya: güncel ayarlarla paylaşılmaz

    def test_unchanged_window_keeps_everything_current(self):
        base = config.default_config()
        current = json.loads(json.dumps(base))
        current["meb_applied"] = {"2026-2027": "abc"}
        current["skip_today"] = {"date": "2026-11-06", "ids": ["ogretmen-1"]}
        self.assertEqual(config.merge_changes(base, json.loads(json.dumps(base)), current), current)


class RestoreLockedFileTests(unittest.TestCase):
    def setUp(self):
        self._home = tempfile.mkdtemp()
        self._old = {k: os.environ.get(k) for k in ("HOME", "APPDATA", "XDG_DATA_HOME")}
        for k in self._old:
            os.environ[k] = self._home
        library._library = None

    def tearDown(self):
        for k, v in self._old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        library._library = None
        shutil.rmtree(self._home, ignore_errors=True)

    def test_locked_sound_skipped_restore_finishes(self):
        lib = library.get_library()
        item_id, target = lib.new_target("Zil")
        target.write_bytes(b"ses")
        lib.add(item_id, target, "Zil")
        zpath = os.path.join(self._home, "yedek.zip")
        backup.create_backup(config.default_config(), zpath)
        orig = backup._copy_replace

        def locked(src, dest):
            if dest.suffix == ".opus":
                raise PermissionError("kullanımda")
            orig(src, dest)
        skipped = []
        with mock.patch.object(backup, "_copy_replace", side_effect=locked):
            backup.restore_backup(zpath, skipped)
        self.assertEqual(skipped, [target.name])
        self.assertEqual(len(library.get_library().items()), 1)


if __name__ == "__main__":
    unittest.main()
