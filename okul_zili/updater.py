"""Programın kendisini güncellemesi (GitHub sürümleri).

Yeni bir sürüm varsa ana ekranda «Güncelleme var» düğmesi görünür. «Güncelle»ye basılınca:
  * Kurulumla yüklenmiş programda: yeni kurulum dosyası indirilir, program kapanır, kurulum sessizce
    çalışıp programı yeniden açar.
  * Taşınabilir (tek dosya) programda: yeni .exe indirilir, eskisinin yerine geçer ve açılır.
  * Kaynak koddan çalışırken: sürüm sayfası tarayıcıda açılır.
"""

import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

from . import GITHUB_REPO, __version__, paths

log = logging.getLogger(__name__)

REPO = GITHUB_REPO
LATEST_API = f"https://api.github.com/repos/{REPO}/releases/latest"
NO_WINDOW = 0x08000000


def version_tuple(v: str):
    return tuple(int(x) for x in re.findall(r"\d+", v or "")[:4]) or (0,)


def install_kind() -> str:
    """"installer" (Program Files / kullanıcı klasörüne kurulmuş), "portable" ya da "source"."""
    if not getattr(sys, "frozen", False):
        return "source"
    exe = Path(sys.executable)
    if any(exe.parent.glob("unins*.exe")):
        return "installer"
    return "portable"


def check_latest(timeout=15):
    """En son sürüm bilgisi; bu sürümden yeni değilse ya da internet yoksa None."""
    req = urllib.request.Request(LATEST_API, headers={"User-Agent": "OkulZili",
                                                      "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.load(resp)
    tag = data.get("tag_name") or ""
    version = tag.lstrip("vV")
    if version_tuple(version) <= version_tuple(__version__):
        return None
    assets = {a.get("name", ""): a.get("browser_download_url") for a in data.get("assets", [])}
    installer = next((u for n, u in assets.items() if n.startswith("OkulZili-Kurulum") and n.endswith(".exe")), None)
    portable = next((u for n, u in assets.items() if n.startswith("OkulZili-Tasinabilir") and n.endswith(".exe")),
                    None)
    return {"version": version, "page": data.get("html_url"), "notes": data.get("body") or "",
            "installer": installer, "portable": portable}


class UpdateChecker:
    """Açılıştan bir dakika sonra ve 12 saatte bir yeni sürüm olup olmadığına bakar."""

    def __init__(self, enabled_getter, interval_hours=12, first_delay=60):
        self.latest = None
        self._enabled = enabled_getter
        self._interval = interval_hours * 3600
        self._first_delay = first_delay
        self._wake = threading.Event()
        threading.Thread(target=self._run, name="guncelleme-denetimi", daemon=True).start()

    def check_now(self):
        self._wake.set()

    def _run(self):
        self._wake.wait(self._first_delay)
        while True:
            self._wake.clear()
            if self._enabled():
                try:
                    self.latest = check_latest()
                    if self.latest:
                        log.info("Yeni sürüm var: %s", self.latest["version"])
                except Exception as exc:  # noqa: BLE001 - internet yoksa sessizce sonra denenir
                    log.debug("Güncelleme denetlenemedi: %s", exc)
            self._wake.wait(self._interval)


def _download(url, target: Path, progress=None):
    req = urllib.request.Request(url, headers={"User-Agent": "OkulZili"})
    with urllib.request.urlopen(req, timeout=60) as resp, open(target, "wb") as f:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = resp.read(256 * 1024)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if progress and total:
                progress(done / total)
    if target.stat().st_size < 1_000_000:
        raise OSError("İndirilen dosya eksik görünüyor")


def mark_updating():
    """Güncelleme sırasında bekçi görevi eski sürümü yeniden açmasın."""
    (paths.data_dir() / "guncelleniyor").write_text(str(time.time()), encoding="utf-8")


def updating_recently(seconds=900) -> bool:
    f = paths.data_dir() / "guncelleniyor"
    try:
        return time.time() - float(f.read_text(encoding="utf-8")) < seconds
    except (OSError, ValueError):
        return False


def prepare_and_launch(info, progress=None):
    """Güncellemeyi indirir ve program kapandıktan sonra çalışacak şekilde başlatır.
    True dönerse çağıran program hemen kapanmalıdır."""
    kind = install_kind()
    if os.name != "nt" or kind == "source" or not (info.get("installer") or info.get("portable")):
        webbrowser.open(info.get("page") or f"https://github.com/{REPO}/releases/latest")
        return False
    tmp = Path(tempfile.mkdtemp(prefix="okulzili_guncelleme_"))
    if kind == "installer" and info.get("installer"):
        setup = tmp / f"OkulZili-Kurulum-{info['version']}.exe"
        _download(info["installer"], setup, progress)
        exe_dir = str(Path(sys.executable).parent).lower()
        scope = "/ALLUSERS" if "program files" in exe_dir else "/CURRENTUSER"
        args = f"/SILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS /RELAUNCH=1 {scope}"
        # Program kapanıp tek kopya kilidini bıraktıktan sonra kurulum başlasın diye birkaç saniye beklenir.
        command = f'timeout /t 4 /nobreak >nul & start "" "{setup}" {args}'
    else:
        if not info.get("portable"):
            webbrowser.open(info.get("page"))
            return False
        current = Path(sys.executable)
        new = current.with_name(f"OkulZili-Tasinabilir-{info['version']}.exe")
        part = new.with_suffix(".exe.part")
        _download(info["portable"], part, progress)
        part.replace(new)
        command = ('timeout /t 4 /nobreak >nul & '
                   + (f'del /f /q "{current}" & ' if new.resolve() != current.resolve() else "")
                   + f'start "" "{new}" --oz-restart')
    mark_updating()
    log.info("Güncelleme başlatılıyor: %s", info["version"])
    subprocess.Popen(["cmd", "/c", command], creationflags=NO_WINDOW, close_fds=True)
    return True


def clear_updating_mark():
    try:
        (paths.data_dir() / "guncelleniyor").unlink()
    except OSError:
        pass

