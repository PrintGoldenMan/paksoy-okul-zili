"""Arayüz duman testi: ana pencere, her düzeyde her ayar sekmesi ve pencereler hatasız açılmalı.

Ekran yoksa (ör. sanal ekransız Linux) atlanır. CI'da Windows'ta doğrudan, Linux'ta xvfb-run ile çalışır.
"""

import os
import shutil
import tempfile
import unittest

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")


def _display_available():
    try:
        import tkinter
        root = tkinter.Tk()
        root.destroy()
        return True
    except Exception:  # noqa: BLE001
        return False


@unittest.skipUnless(_display_available(), "ekran yok")
class UISmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._home = tempfile.mkdtemp(prefix="okulzili_ui_")
        cls._old = {k: os.environ.get(k) for k in ("HOME", "APPDATA", "XDG_DATA_HOME", "XDG_CONFIG_HOME")}
        for k in cls._old:
            os.environ[k] = cls._home
        import customtkinter as ctk
        from okul_zili import app as appmod, config, system, updater
        from okul_zili.ui import theme
        from okul_zili.ui.main_window import MainWindow
        # Ağ ve sistem değişikliği yapan parçalar testte çalışmasın.
        system.set_watchdog = lambda enabled: None
        system.set_keep_awake = lambda on: None
        updater.UpdateChecker.__init__ = lambda self, *a, **k: setattr(self, "latest", None)
        cfg = config.default_config()
        cfg.update(setup_done=True, level="basit", check_clock=False, check_volume=False, watchdog=False,
                   school_name="Deneme Okulu")
        config.save(cfg)
        ctk.set_default_color_theme("blue")
        theme.apply_overrides()
        cls.app = appmod.App()
        cls.errors = []
        cls.app.window = cls.win = MainWindow(cls.app)
        cls.win.report_callback_exception = lambda exc, val, tb: cls.errors.append(val)
        cls.win.update()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.win.destroy()
        except Exception:  # noqa: BLE001
            pass
        for k, v in cls._old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(cls._home, ignore_errors=True)

    def tearDown(self):
        self.win.update()
        self.assertEqual(self.errors, [], "arayüz geri çağrısında hata")

    def test_settings_every_tab_every_level(self):
        from okul_zili import config
        from okul_zili.ui.settings_window import SettingsWindow
        for level in config.LEVELS:
            with self.subTest(level=level):
                self.app.cfg["level"] = level
                s = SettingsWindow(self.win, self.app)
                s.update()
                for tab in list(s.tabs._name_list):
                    s._ensure_built(tab)
                    s.tabs.set(tab)
                    s.update()
                self.assertTrue(s._collect(show_errors=False), level)
                s._cancel_without_prompt()
        self.app.cfg["level"] = "basit"

    def test_settings_save_keeps_background_changes(self):
        import customtkinter as ctk
        from okul_zili.ui.settings_window import SettingsWindow

        def buttons(widget, text):
            found = [widget] if isinstance(widget, ctk.CTkButton) and widget.cget("text") == text else []
            for child in widget.winfo_children():
                found += buttons(child, text)
            return found
        self.app.cfg["level"] = "uzman"
        self.app.cfg["tts"]["offline_voice"] = "HKEY\\Voices\\TTS_MS_TR-TR_TOLGA_11.0"
        s = SettingsWindow(self.win, self.app)
        try:
            for tab in list(s.tabs._name_list):
                s._ensure_built(tab)
            s.update()
            # Ayarlar açıkken ana ekrandan / arka planda yapılan değişiklikler
            self.app.cfg["holidays"] = [{"start": "2026-11-10", "end": "2026-11-10", "name": "Ara tatil"}]
            self.app.cfg["meb_applied"] = {"2026-2027": "abc"}
            # Ek ziller: ortadaki kart silinip yenisi eklenince kartlar üst üste binmemeli
            extra = s.tabs.tab("Ek Ziller")
            flag, friday = buttons(extra, "Pazartesi bayrak töreni")[0], buttons(extra, "Cuma haftayı kapatma")[0]
            flag.invoke()
            friday.invoke()
            buttons(extra, "+ Ek zil ekle")[0].invoke()
            buttons(extra, "Sil")[1].invoke()
            friday.invoke()
            s.update()
            cards = [b.master.master for b in buttons(extra, "Sil")]
            rows = [int(c.grid_info()["row"]) for c in cards]
            self.assertEqual(len(rows), len(set(rows)), rows)
            s._save()
        finally:
            if s.winfo_exists():
                s._cancel_without_prompt()
        cfg = self.app.cfg
        self.assertEqual(cfg["holidays"][0]["name"], "Ara tatil")
        self.assertEqual(cfg["meb_applied"], {"2026-2027": "abc"})
        self.assertEqual(len(cfg["extra_bells"]), 3)
        self.assertEqual(cfg["tts"]["offline_voice"], "HKEY\\Voices\\TTS_MS_TR-TR_TOLGA_11.0")
        self.app.update_config(level="basit", holidays=[], extra_bells=[], meb_applied={})

    def test_dialogs(self):
        from okul_zili.ui.credits import CreditsDialog
        from okul_zili.ui.level_dialog import LevelDialog
        from okul_zili.ui.library_window import LibraryWindow
        from okul_zili.ui.setup_wizard import SetupWizard
        for make in (lambda: LibraryWindow(self.win, self.app), lambda: LevelDialog(self.win, "basit"),
                     lambda: CreditsDialog(self.win), lambda: SetupWizard(self.win, self.app, on_done=lambda: None)):
            d = make()
            d.update()
            d.destroy()

    def test_main_window_ceremony_state(self):
        import time
        p = self.app.player
        p._ceremony = {"gen": p._gen, "key": "istiklal", "title": "İstiklal Marşı", "started": time.monotonic(),
                       "length": 59.0}
        try:
            self.win._update(__import__("datetime").datetime.now())
            self.assertIn("Durdur", self.win.cer_btns["istiklal"].cget("text"))
        finally:
            p._ceremony = None
        self.win._update(__import__("datetime").datetime.now())


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(_display_available(), "ekran yok")
class StartHiddenTests(unittest.TestCase):
    """Bilgisayar açılınca tepside başlama: simge görünüyorsa pencere gizlenir, görünmüyorsa küçültülür."""

    def _window(self, visible):
        import tkinter
        from types import SimpleNamespace
        from okul_zili.ui.main_window import MainWindow

        class FakeTray:
            available = True

            def is_visible(self):
                return visible

        win = tkinter.Tk()
        win.app = SimpleNamespace(tray=FakeTray())
        win._tray_visible = MainWindow._tray_visible.__get__(win)
        win.start_hidden = MainWindow.start_hidden.__get__(win)
        win.update()
        return win

    def test_hidden_when_tray_visible(self):
        win = self._window(True)
        try:
            win.start_hidden(tries=0)
            win.update()
            self.assertEqual(win.state(), "withdrawn")
        finally:
            win.destroy()

    def test_minimized_when_no_tray(self):
        win = self._window(False)
        calls = []
        win.iconify = lambda: calls.append("iconify")   # sanal ekranda pencere yöneticisi yok
        try:
            win.start_hidden(tries=0)
            win.update()
            self.assertEqual(calls, ["iconify"])
            self.assertNotEqual(win.state(), "withdrawn")   # gizlenmedi: görev çubuğundan geri açılabilir
        finally:
            win.destroy()
