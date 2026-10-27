"""Programın giriş noktası: ayarları yükler, zamanlayıcıyı ve pencereyi başlatır."""

import logging
import logging.handlers
import os
import sys
import threading

import customtkinter as ctk

from . import APP_NAME, __version__, autostart, config, paths, sounds
from .audio import Player
from .config import BELL_NAMES, ring_seconds
from .scheduler import BellScheduler
from .schedule import BellEvent

log = logging.getLogger("okul_zili")


def _setup_logging():
    handler = logging.handlers.RotatingFileHandler(paths.log_file(), maxBytes=512_000, backupCount=2,
                                                   encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s", "%d.%m.%Y %H:%M:%S"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    if sys.stderr is not None:
        root.addHandler(logging.StreamHandler())


class App:
    def __init__(self):
        self.cfg = config.load()
        self.now_playing = ""
        self.player = Player(lambda: self.cfg, on_state=self._on_player_state)
        self.scheduler = BellScheduler(lambda: self.cfg, self.player)
        self.window = None

    def _on_player_state(self, playing, text):
        self.now_playing = text if playing else ""

    def update_config(self, **changes):
        self.cfg.update(changes)
        self.apply_config(self.cfg)

    # Ana ekrandaki anahtarlarla değişen ayarlar: ayarlar penceresi açıkken değişmiş olabilirler,
    # pencere kaydedilince eski değerlerle ezilmemeleri için güncel halleri korunur.
    RUNTIME_KEYS = ("auto_ring", "skip_date", "skip_today")

    def apply_config(self, new_cfg, keep_runtime=False):
        if keep_runtime:
            for key in self.RUNTIME_KEYS:
                new_cfg[key] = self.cfg.get(key, new_cfg.get(key))
        self.cfg = new_cfg
        try:
            config.save(self.cfg)
        except OSError as exc:
            log.error("Ayarlar kaydedilemedi: %s", exc)
            if self.window is not None:
                from tkinter import messagebox
                messagebox.showerror("Ayarlar kaydedilemedi",
                                     f"Ayarlar diske yazılamadı. Program şimdilik bu ayarlarla çalışacak, "
                                     f"ancak yeniden açılınca eski ayarlar yüklenir.\n\n{exc}", parent=self.window)
        self.scheduler.reload()
        if self.cfg.get("autostart") != autostart.is_enabled():
            autostart.set_enabled(bool(self.cfg.get("autostart")))
        if self.window is not None:
            self.window.refresh_all()

    def ring_now(self, kind):
        b = self.cfg["bells"][kind]
        log.info("Elle çalındı: %s", BELL_NAMES[kind])
        self.player.ring(BellEvent(minute=0, kind=kind, label=BELL_NAMES[kind], sound=b.get("sound", ""),
                                   duration=ring_seconds(b.get("duration")), volume=int(b.get("volume", 100))),
                         announce=False)

    def run(self):
        ctk.set_default_color_theme("blue")
        from .ui import theme
        theme.apply_overrides()
        ctk.set_appearance_mode({"light": "light", "dark": "dark"}.get(self.cfg["theme"], "system"))
        # Hazır sesleri arka planda hazırla (ilk açılışta birkaç saniye sürer).
        threading.Thread(target=sounds.ensure_all, name="ses-hazirlik", daemon=True).start()
        from .ui.main_window import MainWindow
        self.window = MainWindow(self)
        self.scheduler.start()
        if not self.cfg.get("level"):
            self.window.after(300, self.window.open_level_dialog)
        self.window.mainloop()


_instance_handle = None


def _already_running() -> bool:
    """Program ikinci kez açılırsa ziller iki kez çalmasın diye tek kopya çalışmasını sağlar."""
    global _instance_handle
    if os.name == "nt":
        import ctypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        _instance_handle = kernel32.CreateMutexW(None, False, "Local\\OkulZili.TekKopya")
        return ctypes.get_last_error() == 183  # ERROR_ALREADY_EXISTS
    import fcntl
    _instance_handle = open(paths.data_dir() / "calisiyor.lock", "w")
    try:
        fcntl.flock(_instance_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return False
    except OSError:
        return True


def _show_already_running():
    import tkinter
    from tkinter import messagebox
    root = tkinter.Tk()
    root.withdraw()
    messagebox.showinfo(APP_NAME, "Okul Zili programı zaten açık.\n\n"
                                  "Görev çubuğundaki zil simgesine tıklayarak açık olan pencereye geçebilirsiniz.")
    root.destroy()


def main():
    _setup_logging()
    if _already_running():
        log.info("Program zaten açık; ikinci kopya kapatıldı")
        _show_already_running()
        return
    log.info("%s %s başlatıldı (veri klasörü: %s)", APP_NAME, __version__, paths.data_dir())
    if os.name == "nt":
        try:  # Görev çubuğunda Python simgesi yerine programın kendi kimliği görünsün.
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("OkulZili.App")
        except Exception:  # noqa: BLE001
            pass
    App().run()
