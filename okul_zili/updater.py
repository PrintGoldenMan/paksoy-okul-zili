"""Programın kendisini güncellemesi (GitHub sürümleri).

Yeni bir sürüm varsa ana ekranda «Güncelleme var» düğmesi görünür. «Güncelle»ye basılınca:
  * Kurulumla yüklenmiş programda: yeni kurulum dosyası indirilir, program kapanır, kurulum sessizce
    çalışıp programı yeniden açar.
  * Taşınabilir (tek dosya) programda: yeni .exe indirilir, eskisinin yerine geçer ve açılır.
  * Linux'ta: yeni sürümün .tar.gz paketindeki program dosyası eskisinin yerine yazılır ve program yeniden açılır.
  * Kaynak koddan çalışırken: sürüm sayfası tarayıcıda açılır.
"""

import hashlib
import json
import logging
import os
import re
import shutil
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


IS_LINUX = sys.platform.startswith("linux")
IS_WINDOWS = os.name == "nt"


def install_kind() -> str:
    """"installer" (Program Files / kullanıcı klasörüne kurulmuş), "portable", "linux" ya da "source"."""
    if not getattr(sys, "frozen", False):
        return "source"
    if IS_LINUX:
        return "linux"
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
    import platform
    arch = "aarch64" if platform.machine().lower() in ("arm64", "aarch64") else "x86_64"
    linux = next((u for n, u in assets.items() if n.startswith(f"OkulZili-Linux-{arch}") and n.endswith(".tar.gz")),
                 None)
    return {"version": version, "page": data.get("html_url"), "notes": data.get("body") or "",
            "installer": installer, "portable": portable, "linux": linux}


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
    if total and done != total:
        # Bağlantı yarıda koptu: eksik dosya kurulmasın (taşınabilirde eski program silinir).
        raise OSError(f"İndirme yarıda kesildi ({done} / {total} bayt). Lütfen tekrar deneyin.")
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


def _bat_path(path) -> str:
    """Toplu iş dosyasında tırnak içinde kullanılacak yol: «%» ikilenir (değişken sanılmasın)."""
    return str(path).replace("%", "%%")


def update_script(commands) -> str:
    """Program kapandıktan sonra çalışacak toplu iş dosyası (.bat). UTF-8 yazılır; «chcp 65001»
    sayesinde Türkçe harfli yollar (ör. C:\\Users\\Öğretmen) doğru okunur."""
    return "\r\n".join([
        "@echo off",
        "chcp 65001 >nul",
        # Program kapanıp tek kopya kilidini bıraksın diye birkaç saniye beklenir
        # (timeout girişsiz çalışamazsa ping ile beklenir).
        "timeout /t 4 /nobreak >nul 2>&1 || ping -n 5 127.0.0.1 >nul",
        *commands, ""])


def _launch_script(tmp: Path, commands):
    bat = tmp / "guncelle.bat"
    bat.write_bytes(update_script(commands).encode("utf-8"))
    comspec = os.environ.get("ComSpec") or "cmd.exe"
    # Komut satırı olduğu gibi verilir (liste verilirse tırnaklar \" biçiminde bozulur); /s ile dıştaki
    # tırnaklar kaldırılır, dosya yolu tırnak içinde kalır.
    subprocess.Popen(f'"{comspec}" /d /s /c ""{bat}""', creationflags=NO_WINDOW, close_fds=True)


def prepare_and_launch(info, progress=None):
    """Güncellemeyi indirir ve program kapandıktan sonra çalışacak şekilde başlatır.
    True dönerse çağıran program hemen kapanmalıdır."""
    kind = install_kind()
    if kind == "linux":
        return _prepare_linux(info, progress)
    # Bu kurulum türünün dosyası sürümde yoksa sürüm sayfası açılır: kurulu programın yerine
    # taşınabilir .exe yazılmasın (Program Files'a indirip kurulu programı silerdi).
    if not IS_WINDOWS or kind not in ("installer", "portable") or not info.get(kind):
        webbrowser.open(info.get("page") or f"https://github.com/{REPO}/releases/latest")
        return False
    tmp = Path(tempfile.mkdtemp(prefix="okulzili_guncelleme_"))
    if kind == "installer":
        setup = tmp / f"OkulZili-Kurulum-{info['version']}.exe"
        _download(info["installer"], setup, progress)
        exe_dir = str(Path(sys.executable).parent).lower()
        scope = "/ALLUSERS" if "program files" in exe_dir else "/CURRENTUSER"
        args = f"/SILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS /RELAUNCH=1 {scope}"
        commands = [f'start "" "{_bat_path(setup)}" {args}']
    else:
        current = Path(sys.executable)
        new = current.with_name(f"OkulZili-Tasinabilir-{info['version']}.exe")
        part = new.with_suffix(".exe.part")
        _download(info["portable"], part, progress)
        part.replace(new)
        commands = ([f'del /f /q "{_bat_path(current)}"'] if new.resolve() != current.resolve() else []) \
            + [f'start "" "{_bat_path(new)}" --oz-restart']
    mark_updating()
    log.info("Güncelleme başlatılıyor: %s", info["version"])
    _launch_script(tmp, commands)
    return True


def _expected_sha256(sums: bytes, name: str):
    """SHA256SUMS içeriğinden (sha256sum çıktısı: «<özet>  <ad>») dosyanın beklenen özeti; yoksa None."""
    for line in sums.decode("utf-8", "replace").splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and parts[1].lstrip("*") == name and re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
            return parts[0].lower()
    return None


def _prepare_linux(info, progress=None):
    """Linux: paketteki «okulzili» dosyası çalışan programın yerine yazılır (Linux, çalışan dosyanın yerine
    yenisinin konmasına izin verir) ve program yeni sürümle yeniden açılır."""
    import tarfile
    current = Path(sys.executable).resolve()
    if not info.get("linux") or not os.access(current.parent, os.W_OK):
        # Program yazılamayan bir yere kurulmuş (ör. /opt): sürüm sayfası açılır.
        webbrowser.open(info.get("page") or f"https://github.com/{REPO}/releases/latest")
        return False
    tmp = Path(tempfile.mkdtemp(prefix="okulzili_guncelleme_"))
    new = current.with_name(current.name + ".yeni")
    try:
        archive = tmp / "paket.tar.gz"
        _download(info["linux"], archive, progress)
        with tarfile.open(archive, "r:gz") as tar:
            files = [m for m in tar.getmembers() if m.isfile()]
            member = next((m for m in files if Path(m.name).name == "okulzili"), None)
            if member is None:
                raise OSError("Güncelleme paketinde program dosyası bulunamadı")
            digest = hashlib.sha256()
            with tar.extractfile(member) as src, open(new, "wb") as dst:
                for chunk in iter(lambda: src.read(1024 * 1024), b""):
                    digest.update(chunk)
                    dst.write(chunk)
            sums = next((m for m in files if Path(m.name).name == "SHA256SUMS"
                         and Path(m.name).parent == Path(member.name).parent), None)
            expected = _expected_sha256(tar.extractfile(sums).read(), "okulzili") if sums is not None else None
        if new.stat().st_size < 1_000_000:
            raise OSError("İndirilen program dosyası eksik görünüyor")
        if expected is not None and digest.hexdigest() != expected:
            raise OSError("Güncelleme paketindeki program dosyası bozuk (SHA256 tutmuyor). Lütfen tekrar deneyin.")
        new.chmod(0o755)
        new.replace(current)
    except BaseException:
        new.unlink(missing_ok=True)
        raise
    finally:
        # İndirilen paket (onlarca MB) geçici klasörde kalmasın.
        shutil.rmtree(tmp, ignore_errors=True)
    mark_updating()
    log.info("Güncelleme kuruldu, program yeniden açılıyor: %s", info["version"])
    # Yeni süreç, bu program kapanıp tek kopya kilidini bırakana kadar bekler (--oz-restart).
    subprocess.Popen([str(current), "--oz-restart"], start_new_session=True, close_fds=True)
    return True


def clear_updating_mark():
    try:
        (paths.data_dir() / "guncelleniyor").unlink()
    except OSError:
        pass


def note_installed_version():
    """Linux: kur.sh kurulu sürümü programı çalıştırmadan yanındaki .okulzili.surum dosyasından okur;
    program kendini güncellediyse dosya da güncellensin (yalnızca kur.sh ile kurulmuşsa: dosya varsa)."""
    if install_kind() != "linux":
        return
    note = Path(sys.executable).with_name(".okulzili.surum")
    try:
        if note.is_file() and note.read_text(encoding="utf-8").strip() != __version__:
            note.write_text(__version__ + "\n", encoding="utf-8")
    except OSError:
        pass

