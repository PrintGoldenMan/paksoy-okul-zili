"""Linux uyumluluğu: otomatik başlatma dosyası, ses düzeyi okuma, tepsi başlığı."""

import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from okul_zili import autostart, system
from okul_zili.tray import _safe_title


class DesktopExecTests(unittest.TestCase):
    def test_quoting(self):
        self.assertEqual(autostart.desktop_exec(["/home/a/.local/bin/okulzili"]), "/home/a/.local/bin/okulzili")
        self.assertEqual(autostart.desktop_exec(["/usr/bin/python3", "/home/a b/main.py"]),
                         '/usr/bin/python3 "/home/a b/main.py"')
        # « " » ve « $ » tırnak içinde kaçırılır; ters eğik çizgiler dize değeri için bir kez daha kaçırılır.
        self.assertEqual(autostart.desktop_exec(['/p/a"b$c%d']), '"/p/a\\\\"b\\\\$c%%d"')


@unittest.skipUnless(sys.platform.startswith("linux"), "yalnızca Linux")
class AutostartTests(unittest.TestCase):
    def setUp(self):
        self._old = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()

    def tearDown(self):
        if self._old is None:
            os.environ.pop("XDG_CONFIG_HOME", None)
        else:
            os.environ["XDG_CONFIG_HOME"] = self._old

    def test_enable_disable(self):
        self.assertTrue(autostart.supported())
        self.assertFalse(autostart.is_enabled())
        autostart.set_enabled(True)
        text = (autostart._desktop_file()).read_text(encoding="utf-8")
        self.assertIn("[Desktop Entry]", text)
        self.assertIn("main.py", text)
        self.assertTrue(autostart.is_enabled())
        autostart.set_enabled(False)
        self.assertFalse(autostart.is_enabled())


def _result(out="", err="", code=0):
    return subprocess.CompletedProcess([], code, stdout=out, stderr=err)


@unittest.skipUnless(sys.platform.startswith("linux"), "yalnızca Linux")
class LinuxVolumeTests(unittest.TestCase):
    def read(self, which, results):
        with mock.patch.object(system.shutil, "which", lambda name: f"/usr/bin/{name}" if name in which else None), \
                mock.patch.object(system, "_run_quiet", side_effect=results):
            return system._read_linux_volume()

    def test_pipewire(self):
        self.assertEqual(self.read({"wpctl"}, [_result("Volume: 0.45\n")]),
                         {"muted": False, "level": 0.45, "device": True})
        self.assertEqual(self.read({"wpctl"}, [_result("Volume: 0.80 [MUTED]\n")])["muted"], True)

    def test_pulseaudio(self):
        state = self.read({"pactl"}, [_result("Mute: no\n"),
                                      _result("Volume: front-left: 32768 /  50% / -18.06 dB,   "
                                              "front-right: 32768 /  50% / -18.06 dB\n")])
        self.assertEqual(state, {"muted": False, "device": True, "level": 0.5})

    def test_no_sound_server_is_unknown(self):
        # Ses sunucusuna bağlanılamıyorsa uyarı gösterilmez (None = bilinmiyor).
        self.assertIsNone(self.read({"wpctl"}, [_result(err="Could not connect to PipeWire", code=1)]))
        self.assertIsNone(self.read(set(), []))


class TrayTitleTests(unittest.TestCase):
    def test_latin1_safe_for_xorg(self):
        title = _safe_title("Okul Zili – ziller çalışıyor", "pystray._xorg")
        title.encode("latin-1")
        self.assertEqual(title, "Okul Zili - ziller çalisiyor")
        self.assertEqual(_safe_title("ı – ş", "pystray._appindicator"), "ı – ş")


if __name__ == "__main__":
    unittest.main()
