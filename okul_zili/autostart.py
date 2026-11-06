"""Bilgisayar açılınca programı otomatik başlatma.

  * Windows: kayıt defterindeki «Run» anahtarı
  * Linux: ~/.config/autostart/okulzili.desktop (XDG; LXQt/Lubuntu, GNOME, KDE, XFCE hepsi okur)
"""

import logging
import os
import sys
from pathlib import Path

log = logging.getLogger(__name__)
_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_NAME = "OkulZili"
IS_LINUX = sys.platform.startswith("linux")


def supported() -> bool:
    return os.name == "nt" or IS_LINUX


def _command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    exe = pythonw if pythonw.exists() else Path(sys.executable)
    main = Path(__file__).resolve().parent.parent / "main.py"
    return f'"{exe}" "{main}"'


def _desktop_file() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return Path(base) / "autostart" / "okulzili.desktop"


def desktop_exec(args) -> str:
    """Desktop Entry «Exec» değeri (spesifikasyondaki tırnak ve kaçış kurallarıyla)."""
    def quote(arg):
        if arg and all(c.isalnum() or c in "/._-+=:," for c in arg):
            return arg
        for ch in ("\\", '"', "`", "$"):
            arg = arg.replace(ch, "\\" + ch)
        return f'"{arg}"'
    # Dize değeri olarak ters eğik çizgiler bir kez daha kaçırılır; % alan kodlarıyla karışmasın.
    return " ".join(quote(a) for a in args).replace("\\", "\\\\").replace("%", "%%")


def _linux_exec() -> str:
    from .app import launch_args
    return desktop_exec(launch_args())


def is_enabled() -> bool:
    if IS_LINUX:
        f = _desktop_file()
        try:
            return f.exists() and "Hidden=true" not in f.read_text(encoding="utf-8")
        except OSError:
            return False
    if not supported():
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _KEY) as k:
            winreg.QueryValueEx(k, _NAME)
            return True
    except OSError:
        return False


def set_enabled(enabled: bool) -> None:
    if IS_LINUX:
        f = _desktop_file()
        try:
            if enabled:
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text("\n".join([
                    "[Desktop Entry]", "Type=Application", "Name=Okul Zili",
                    "Comment=Okullar için otomatik zil programı", f"Exec={_linux_exec()}",
                    "Icon=okulzili", "Terminal=false", "X-GNOME-Autostart-enabled=true",
                    "X-GNOME-Autostart-Delay=5", ""]), encoding="utf-8")
            else:
                f.unlink(missing_ok=True)
        except OSError as exc:
            log.error("Otomatik başlatma ayarlanamadı: %s", exc)
        return
    if not supported():
        return
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _KEY, 0, winreg.KEY_SET_VALUE) as k:
            if enabled:
                winreg.SetValueEx(k, _NAME, 0, winreg.REG_SZ, _command())
            else:
                try:
                    winreg.DeleteValue(k, _NAME)
                except FileNotFoundError:
                    pass
    except OSError as exc:
        log.error("Otomatik başlatma ayarlanamadı: %s", exc)
