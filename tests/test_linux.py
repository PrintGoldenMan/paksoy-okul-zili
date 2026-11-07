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
    def test_installer_reads_back_exec_path(self):
        # kur.sh exec_yolu, programın yazdığı Exec değerinden yolu doğru çıkarmalı (boşluk, tırnak, kaçış).
        script = os.path.join(os.path.dirname(__file__), "..", "installer", "linux", "kur.sh")
        for path in ("/home/a/.local/bin/okulzili", "/home/a b/.local/bin/okulzili", '/p/a"b$c%d`e\\f g'):
            value = autostart.desktop_exec([path, autostart.BACKGROUND_FLAG])
            out = subprocess.run(["bash", "-c", 'eval "$(sed -n "/^exec_yolu() {/,/^}/p" "$1")"; exec_yolu "$2"',
                                  "_", script, value], capture_output=True, text=True, check=True).stdout
            self.assertEqual(out, path)

    def test_installed_version_note(self):
        from okul_zili import __version__, updater
        with tempfile.TemporaryDirectory() as tmp:
            exe = os.path.join(tmp, "okulzili")
            note = os.path.join(tmp, ".okulzili.surum")
            with mock.patch.object(updater, "install_kind", return_value="linux"), \
                    mock.patch.object(updater.sys, "executable", exe):
                updater.note_installed_version()             # kur.sh ile kurulmamış: dosya açılmaz
                self.assertFalse(os.path.exists(note))
                with open(note, "w", encoding="utf-8") as f:
                    f.write("1.4.0\n")
                updater.note_installed_version()             # program kendini güncelledi
            with open(note, encoding="utf-8") as f:
                self.assertEqual(f.read(), __version__ + "\n")


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
