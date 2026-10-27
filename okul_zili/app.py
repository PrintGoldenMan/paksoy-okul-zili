"""Programın giriş noktası: ayarları yükler, zamanlayıcıyı ve pencereyi başlatır."""

import logging
import logging.handlers
import os
import sys
import threading

import customtkinter as ctk

from . import APP_NAME, __version__, autostart, config, paths, sounds
from .audio import Player
from .config import BELL_NAMES
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

    def apply_config(self, new_cfg):
        self.cfg = new_cfg
        config.save(self.cfg)
        self.scheduler.reload()
        if self.cfg.get("autostart") != autostart.is_enabled():
            autostart.set_enabled(bool(self.cfg.get("autostart")))
        if self.window is not None:
            self.window.refresh_all()

    def ring_now(self, kind):
        b = self.cfg["bells"][kind]
        log.info("Elle çalındı: %s", BELL_NAMES[kind])
        self.player.ring(BellEvent(minute=0, kind=kind, label=BELL_NAMES[kind], sound=b.get("sound", ""),
                                   repeat=max(1, int(b.get("repeat", 1))), volume=int(b.get("volume", 100))),
                         announce=False)

    def run(self):
        ctk.set_default_color_theme("blue")
        ctk.set_appearance_mode({"light": "light", "dark": "dark"}.get(self.cfg["theme"], "system"))
        # Hazır sesleri arka planda hazırla (ilk açılışta birkaç saniye sürer).
        threading.Thread(target=sounds.ensure_all, name="ses-hazirlik", daemon=True).start()
        from .ui.main_window import MainWindow
        self.window = MainWindow(self)
        self.scheduler.start()
        if not self.cfg.get("level"):
            self.window.after(300, self.window.open_level_dialog)
        self.window.mainloop()


def main():
    _setup_logging()
    log.info("%s %s başlatıldı (veri klasörü: %s)", APP_NAME, __version__, paths.data_dir())
    if os.name == "nt":
        try:  # Görev çubuğunda Python simgesi yerine programın kendi kimliği görünsün.
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("OkulZili.App")
        except Exception:  # noqa: BLE001
            pass
    App().run()
