"""Programın giriş noktası: ayarları yükler, zamanlayıcıyı ve pencereyi başlatır."""

import logging
import logging.handlers
import os
import shutil
import sys
import threading
import time

import customtkinter as ctk

from . import APP_NAME, __version__, autostart, config, meb_takvim, paths, rotation, sounds, system, updater
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


def _remove_old_builtin_sounds():
    """Eski sürümlerin ürettiği hazır ses dosyalarını siler (artık kütüphane kullanılıyor)."""
    old = paths.data_dir() / "hazir_sesler"
    if old.exists():
        shutil.rmtree(old, ignore_errors=True)
        log.info("Eski hazır ses dosyaları silindi")


class App:
    def __init__(self):
        self.cfg = config.load()
        if autostart.supported():
            # Kurulum programı da otomatik başlatmayı açıp kapatabilir; kayıt defteri esas alınır.
            self.cfg["autostart"] = autostart.is_enabled()
        if rotation.update_all(self.cfg):
            self._save_quietly()
        self._rotation_checked = None
        self.now_playing = ""
        self.player = Player(lambda: self.cfg, on_state=self._on_player_state)
        self.scheduler = BellScheduler(lambda: self.cfg, self.player)
        self.window = None
        self.tray = None
        self.volume = system.VolumeMonitor()
        self.clock = system.ClockMonitor()
        self.updates = updater.UpdateChecker(lambda: self.cfg.get("check_updates", True))
        self.calendar = meb_takvim.CalendarUpdater()
        self._calendar_checked = None
        if self.cfg.get("watchdog", True) != system.watchdog_installed():
            threading.Thread(target=system.set_watchdog, args=(self.cfg.get("watchdog", True),), daemon=True).start()

    def _save_quietly(self):
        try:
            config.save(self.cfg)
        except OSError as exc:
            log.error("Ayarlar kaydedilemedi: %s", exc)

    def check_rotation(self, now):
        """Yeni gün/hafta/ay başladıysa değişen zil seslerinden yenisini seçer (ana ekran her saniye çağırır)."""
        minute = now.replace(second=0, microsecond=0)
        if minute == self._rotation_checked:
            return
        self._rotation_checked = minute
        before = {k: rotation.effective_sound(b) for k, b in self.cfg["bells"].items()}
        if rotation.update_all(self.cfg, now.date()):
            self._save_quietly()
            self.scheduler.reload()
            for k, b in self.cfg["bells"].items():
                after = rotation.effective_sound(b)
                if after != before.get(k):
                    log.info("Değişen ses: %s artık «%s»", BELL_NAMES[k], sounds.display_name(after))
            if self.window is not None:
                self.window.refresh_all()

    def check_calendar(self, now):
        """İnternetten yeni MEB takvimi geldiyse ya da gün değiştiyse tatilleri günceller (MEB takvimini kullananlarda)."""
        if not self.calendar.changed and self._calendar_checked == now.date():
            return
        self.calendar.changed = False
        self._calendar_checked = now.date()
        changed = meb_takvim.auto_apply(self.cfg, now.date())
        if changed:
            log.info("MEB takvimi tatilleri güncellendi (%d kayıt)", changed)
            self._save_quietly()
            self.scheduler.reload()
            if self.window is not None:
                self.window.flash(f"📅  MEB takvimi güncellendi ({changed} tatil)")
                self.window.refresh_all()

    def _on_player_state(self, playing, text):
        self.now_playing = text if playing else ""

    def update_config(self, **changes):
        self.cfg.update(changes)
        self.apply_config(self.cfg)

    # Ana ekrandaki anahtarlarla değişen ayarlar: ayarlar penceresi açıkken değişmiş olabilirler,
    # pencere kaydedilince eski değerlerle ezilmemeleri için güncel halleri korunur.
    RUNTIME_KEYS = ("auto_ring", "skip_date", "skip_today", "short_day")

    def apply_config(self, new_cfg, keep_runtime=False):
        if keep_runtime:
            for key in self.RUNTIME_KEYS:
                new_cfg[key] = self.cfg.get(key, new_cfg.get(key))
        self.cfg = new_cfg
        rotation.update_all(self.cfg)   # havuz değiştiyse ya da yeni açıldıysa bu dönemin sesini seç
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
        if self.cfg.get("watchdog", True) != system.watchdog_installed():
            threading.Thread(target=system.set_watchdog, args=(self.cfg.get("watchdog", True),), daemon=True).start()
        if self.cfg.get("autostart") != autostart.is_enabled():
            autostart.set_enabled(bool(self.cfg.get("autostart")))
        if self.window is not None:
            self.window.refresh_all()

    def quit(self):
        """Kullanıcı programı bilerek kapattı: bekçi görevi onu yeniden açmasın."""
        log.info("Program kullanıcı tarafından kapatıldı")
        try:
            user_closed_marker().write_text(time.strftime("%Y-%m-%d %H:%M"), encoding="utf-8")
        except OSError:
            pass
        self.player.stop()
        system.set_keep_awake(False)
        if self.tray is not None:
            self.tray.stop()
        _release_instance()
        os._exit(0)

    def quit_for_update(self):
        """Güncelleme kurulumu başlatıldı: program kapanır (kullanıcı kapatması sayılmaz)."""
        log.info("Güncelleme için program kapanıyor")
        self.player.stop()
        system.set_keep_awake(False)
        if self.tray is not None:
            self.tray.stop()
        _release_instance()
        os._exit(0)

    def restart(self):
        """Programı kapatıp yeniden açar (yt-dlp ya da program güncellemesinden sonra)."""
        import subprocess
        log.info("Program yeniden başlatılıyor")
        self.player.stop()
        flags = {"creationflags": 0x00000008 | 0x00000200} if os.name == "nt" else {"start_new_session": True}
        subprocess.Popen(launch_args("--oz-restart"), close_fds=True, **flags)
        _release_instance()
        os._exit(0)

    def ring_now(self, kind):
        b = self.cfg["bells"][kind]
        log.info("Elle çalındı: %s", BELL_NAMES[kind])
        self.player.ring(BellEvent(minute=0, kind=kind, label=BELL_NAMES[kind], sound=rotation.effective_sound(b),
                                   duration=ring_seconds(b.get("duration")), volume=int(b.get("volume", 100))),
                         announce=False)

    def run(self):
        ctk.set_default_color_theme("blue")
        from .ui import theme
        theme.apply_overrides()
        ctk.set_appearance_mode({"light": "light", "dark": "dark"}.get(self.cfg["theme"], "system"))
        _remove_old_builtin_sounds()
        from .ui.main_window import MainWindow
        self.window = MainWindow(self)
        from .tray import Tray
        self.tray = Tray()
        self.scheduler.start()
        if not self.cfg.get("setup_done", True):
            self.window.after(300, self.window.open_setup_wizard)
        elif not self.cfg.get("level"):
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


def _release_instance():
    global _instance_handle
    if _instance_handle is None:
        return
    try:
        if os.name == "nt":
            import ctypes
            ctypes.WinDLL("kernel32").CloseHandle(_instance_handle)
        else:
            _instance_handle.close()
    except Exception:  # noqa: BLE001
        pass
    _instance_handle = None


def _acquire_instance(wait_seconds=0.0) -> bool:
    """Tek kopya kilidini alır. Yeniden başlatmada eski kopyanın kapanması wait_seconds kadar beklenir."""
    import time
    deadline = time.monotonic() + wait_seconds
    while True:
        if not _already_running():
            return True
        _release_instance()
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.5)


def launch_args(*extra) -> list:
    """Programı yeniden başlatmak için komut satırı (paketlenmiş ya da kaynak koddan)."""
    if getattr(sys, "frozen", False):
        return [sys.executable, *extra]
    main_py = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")
    exe = sys.executable
    if os.name == "nt":
        pythonw = os.path.join(os.path.dirname(exe), "pythonw.exe")
        exe = pythonw if os.path.exists(pythonw) else exe
    return [exe, main_py, *extra]


def _show_already_running():
    import tkinter
    from tkinter import messagebox
    root = tkinter.Tk()
    root.withdraw()
    messagebox.showinfo(APP_NAME, "Okul Zili programı zaten açık.\n\n"
                                  "Görev çubuğundaki zil simgesine tıklayarak açık olan pencereye geçebilirsiniz.")
    root.destroy()


def self_test(out_path):
    """Paketlenmiş programın indirme/dönüştürme/çalma parçalarını dener (derleme denetimi için).
    Sonuç JSON olarak out_path dosyasına yazılır; çıkış kodu 0 = başarılı."""
    import json
    import subprocess
    import tempfile
    result = {}
    try:
        from . import downloader
        result["ytdlp"] = downloader.ytdlp_version()
        import importlib
        importlib.import_module("yt_dlp_ejs")  # YouTube için gerekli bileşen paketlenmiş mi?
        result["ejs"] = True
        ffmpeg = downloader.ffmpeg_exe()
        result["ffmpeg"] = os.path.basename(ffmpeg)
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "deneme.opus")
            subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                            "sine=frequency=440:duration=2", "-c:a", "libopus", "-b:a", "96k", out],
                           check=True, **downloader._hidden_window_flags())
            result["opus_bytes"] = os.path.getsize(out)
            import pygame
            if not pygame.mixer.get_init():
                os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
                pygame.mixer.init()
            pygame.mixer.music.load(out)
            pygame.mixer.music.unload()
            result["opus_playable"] = True
        if os.name == "nt":
            importlib.import_module("pystray._win32")       # sistem tepsisi
            from . import system
            result["volume"] = system.read_system_volume()  # Windows ses düzeyi (aygıt yoksa device=False)
            if result["volume"] is None:
                raise RuntimeError("Windows ses düzeyi okunamadı (pycaw)")
        result["ok"] = True
    except Exception as exc:  # noqa: BLE001
        result["ok"] = False
        result["error"] = repr(exc)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return 0 if result["ok"] else 1


def user_closed_marker():
    return paths.data_dir() / "kullanici_kapatti"


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "--oz-selftest":
        sys.exit(self_test(sys.argv[2]))
    _setup_logging()
    watchdog = "--oz-watchdog" in sys.argv
    if watchdog:
        # Windows Görev Zamanlayıcı her 5 dakikada bir buraya gelir. Program açıksa, kullanıcı bilerek
        # kapattıysa ya da güncelleme sürüyorsa hiçbir şey yapılmaz (sessizce çıkılır).
        if user_closed_marker().exists() or updater.updating_recently():
            return
        if not _acquire_instance():
            return
        log.warning("Program kapalı bulundu; bekçi görevi yeniden başlattı")
    elif not _acquire_instance(wait_seconds=20 if "--oz-restart" in sys.argv else 0):
        log.info("Program zaten açık; ikinci kopya kapatıldı")
        _show_already_running()
        return
    else:
        try:
            user_closed_marker().unlink()   # elle açıldı: bekçi yeniden devrede
        except OSError:
            pass
    updater.clear_updating_mark()
    log.info("%s %s başlatıldı (veri klasörü: %s)", APP_NAME, __version__, paths.data_dir())
    if os.name == "nt":
        try:  # Görev çubuğunda Python simgesi yerine programın kendi kimliği görünsün.
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("OkulZili.App")
        except Exception:  # noqa: BLE001
            pass
    App().run()
