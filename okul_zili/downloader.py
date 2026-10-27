"""İnternetten (yt-dlp ile) ya da bilgisayardan ses ekleme.

Akış: bağlantı önce yoklanır (probe) → tek ses mi, oynatma listesi mi anlaşılır → ses en iyi
kalitede indirilir → ffmpeg ile Opus'a (96 kbit/s) dönüştürülür; baştaki sessizlik kırpılır ve
ses düzeyi eşitlenir → kısa adla kütüphaneye kaydedilir.

YouTube için yt-dlp bir JavaScript çalıştırıcısına (Deno) ihtiyaç duyar; bilgisayarda yoksa ilk
YouTube indirmesinde bir kez otomatik indirilir. yt-dlp de program içinden güncellenebilir.
"""

import importlib.abc
import io
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.request
import zipfile
import zipimport
from dataclasses import dataclass, field
from pathlib import Path

from . import library, paths

log = logging.getLogger(__name__)

MAX_PLAYLIST = 100            # bir listeden en fazla bu kadar ses indirilir
LONG_AUDIO_SECONDS = 15 * 60  # bundan uzun seslerde ayrıca onay istenir
OPUS_BITRATE = "96k"
AUDIO_FILE_TYPES = ("*.mp3", "*.wav", "*.ogg", "*.opus", "*.m4a", "*.aac", "*.flac", "*.wma", "*.webm",
                    "*.mp4", "*.mkv")
YTDLP_UPDATE_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp"
DENO_URL = "https://github.com/denoland/deno/releases/latest/download/{asset}"


class Cancelled(Exception):
    pass


class DownloadError(Exception):
    """Kullanıcıya gösterilecek Türkçe hata."""


def tools_dir() -> Path:
    return paths.sub_dir("araclar")


def _hidden_window_flags() -> dict:
    """Pencereli programda ffmpeg çalışırken siyah konsol penceresi açılmasın."""
    if os.name == "nt":
        return {"creationflags": 0x08000000}  # CREATE_NO_WINDOW
    return {}


# -- yt-dlp: güncellenmiş sürüm varsa onu kullan ------------------------------------------------

class _UpdatedYtDlpFinder(importlib.abc.MetaPathFinder):
    """Programla gelen yt-dlp yerine araclar/yt-dlp.zip içindeki güncel sürümü yükler.
    (Paketlenmiş programda yerleşik modüller sys.path'ten önce bulunduğu için gereklidir.)"""

    def __init__(self, zip_path: Path):
        self.zip_path = str(zip_path)

    def find_spec(self, fullname, path, target=None):
        if fullname != "yt_dlp" and not fullname.startswith("yt_dlp."):
            return None
        parent = fullname.rpartition(".")[0]
        location = os.path.join(self.zip_path, *parent.split(".")) if parent else self.zip_path
        try:
            return zipimport.zipimporter(location).find_spec(fullname)
        except zipimport.ZipImportError:
            return None


def _updated_zip() -> Path:
    return tools_dir() / "yt-dlp.zip"


def _install_finder():
    z = _updated_zip()
    if z.exists() and "yt_dlp" not in sys.modules and _valid_ytdlp_zip(z):
        sys.meta_path.insert(0, _UpdatedYtDlpFinder(z))
        log.info("Güncellenmiş yt-dlp kullanılıyor: %s", _zip_version(z))


def _valid_ytdlp_zip(z: Path) -> bool:
    try:
        with zipfile.ZipFile(z) as zf:
            names = set(zf.namelist())
        return "yt_dlp/__init__.py" in names and "yt_dlp/version.py" in names
    except (OSError, zipfile.BadZipFile):
        return False


def _zip_version(z: Path) -> str:
    try:
        with zipfile.ZipFile(z) as zf:
            text = zf.read("yt_dlp/version.py").decode("utf-8", "replace")
        m = re.search(r"__version__\s*=\s*['\"]([^'\"]+)", text)
        return m.group(1) if m else "?"
    except (OSError, KeyError, zipfile.BadZipFile):
        return "?"


_install_finder()


def ytdlp_version() -> str:
    try:
        import yt_dlp
        return yt_dlp.version.__version__
    except Exception:  # noqa: BLE001
        return "yüklü değil"


def update_ytdlp(progress=None) -> str:
    """yt-dlp'nin en son sürümünü indirir. Etkin olması için program yeniden başlatılmalıdır."""
    data = _fetch(YTDLP_UPDATE_URL, progress)
    tmp = tools_dir() / "yt-dlp.zip.part"
    tmp.write_bytes(data)
    if not _valid_ytdlp_zip(tmp):
        tmp.unlink(missing_ok=True)
        raise DownloadError("İndirilen yt-dlp dosyası geçersiz. Daha sonra tekrar deneyin.")
    tmp.replace(_updated_zip())
    version = _zip_version(_updated_zip())
    log.info("yt-dlp güncellendi: %s", version)
    return version


# -- ffmpeg ve JavaScript çalıştırıcısı -----------------------------------------------------------

def ffmpeg_exe() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001
        found = shutil.which("ffmpeg")
        if found:
            return found
        raise DownloadError("Ses dönüştürücü (ffmpeg) bulunamadı. Programı yeniden kurmayı deneyin.")


def _deno_path() -> Path:
    return tools_dir() / ("deno.exe" if os.name == "nt" else "deno")


def js_runtimes() -> dict:
    """yt-dlp için kullanılabilir JavaScript çalıştırıcısı (YouTube için gerekli)."""
    if _deno_path().exists():
        return {"deno": {"path": str(_deno_path())}}
    if shutil.which("deno"):
        return {"deno": {}}
    if shutil.which("node"):
        return {"node": {}}
    return {}


def _deno_asset() -> str:
    import platform
    machine = platform.machine().lower()
    arch = "aarch64" if machine in ("arm64", "aarch64") else "x86_64"
    if os.name == "nt":
        return f"deno-{arch}-pc-windows-msvc.zip"
    if sys.platform == "darwin":
        return f"deno-{arch}-apple-darwin.zip"
    return f"deno-{arch}-unknown-linux-gnu.zip"


def ensure_js_runtime(progress=None, cancel=None):
    if js_runtimes():
        return
    if progress:
        progress(None, "YouTube desteği hazırlanıyor (yalnızca ilk seferde, yaklaşık 40 MB)…")
    data = _fetch(DENO_URL.format(asset=_deno_asset()), progress, cancel)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        name = next(n for n in zf.namelist() if n.split("/")[-1] in ("deno", "deno.exe"))
        target = _deno_path()
        tmp = target.with_suffix(".part")
        tmp.write_bytes(zf.read(name))
    tmp.chmod(0o755)
    tmp.replace(target)
    log.info("Deno indirildi: %s", target)


def _fetch(url, progress=None, cancel=None) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "OkulZili"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            total = int(resp.headers.get("Content-Length") or 0)
            buf = io.BytesIO()
            while True:
                if cancel is not None and cancel.is_set():
                    raise Cancelled()
                chunk = resp.read(256 * 1024)
                if not chunk:
                    break
                buf.write(chunk)
                if progress and total:
                    progress(buf.tell() / total, None)
            return buf.getvalue()
    except Cancelled:
        raise
    except Exception as exc:  # noqa: BLE001
        raise DownloadError(f"İndirme başarısız oldu. İnternet bağlantısını kontrol edin.\n({exc})")


# -- yoklama ------------------------------------------------------------------------------------

@dataclass
class Probe:
    url: str
    is_playlist: bool
    title: str
    duration: float = None           # tek ses için
    entries: list = field(default_factory=list)   # liste için [(bağlantı, başlık, süre)]
    total_count: int = 0             # listedeki toplam ses sayısı (sınırdan önce)


class _QuietLogger:
    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        if "Falling back on generic" not in msg:
            log.warning("yt-dlp: %s", msg)

    def error(self, msg):
        log.error("yt-dlp: %s", msg)


def _is_youtube(url: str) -> bool:
    return bool(re.search(r"(^|[./])(youtube\.com|youtu\.be|youtube-nocookie\.com)(/|$|:)", url, re.I))


def _base_opts() -> dict:
    opts = {"quiet": True, "no_warnings": True, "noprogress": True, "logger": _QuietLogger(),
            "socket_timeout": 30, "retries": 3, "noplaylist": True}
    runtimes = js_runtimes()
    if runtimes:
        opts["js_runtimes"] = runtimes
    return opts


def _friendly_error(exc) -> DownloadError:
    text = str(exc)
    low = text.lower()
    if "unsupported url" in low:
        msg = "Bu bağlantıdan ses indirilemiyor. Bağlantının doğru olduğundan emin olun."
    elif "private" in low or "sign in" in low or "login" in low:
        msg = "Bu içerik gizli ya da giriş gerektiriyor; indirilemiyor."
    elif "404" in low or "not found" in low:
        msg = "Bu bağlantıda bir sayfa bulunamadı. Bağlantıyı kontrol edin."
    elif "unavailable" in low or "not available" in low or "removed" in low:
        msg = "Bu içerik artık yayında değil ya da bu ülkede açılamıyor."
    elif "urlopen" in low or "timed out" in low or "network" in low or "resolve" in low:
        msg = "İnternete bağlanılamadı. Bağlantıyı kontrol edip tekrar deneyin."
    else:
        msg = ("İndirme başarısız oldu. Site değişmiş olabilir; Kütüphane penceresinden "
               "«yt-dlp'yi güncelle» düğmesine basıp tekrar deneyin.")
    detail = re.sub(r"\x1b\[[0-9;]*m", "", text)[:300]
    return DownloadError(f"{msg}\n\n(Ayrıntı: {detail})")


def probe(url: str, cancel=None) -> Probe:
    """Bağlantının tek ses mi oynatma listesi mi olduğunu öğrenir (indirmeden).

    Hem şarkı hem liste içeren YouTube bağlantılarında (watch?v=…&list=…) yalnızca şarkı alınır."""
    url = url.strip()
    if not re.match(r"^https?://", url, re.I):
        raise DownloadError("Lütfen «https://» ile başlayan tam bir bağlantı yapıştırın.")
    import yt_dlp
    opts = dict(_base_opts(), skip_download=True, extract_flat="in_playlist")
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:  # noqa: BLE001
        raise _friendly_error(exc)
    if cancel is not None and cancel.is_set():
        raise Cancelled()
    if info.get("_type") in ("playlist", "multi_video"):
        entries = []
        total = 0
        for e in info.get("entries") or []:
            if not e:
                continue
            total += 1
            if len(entries) < MAX_PLAYLIST:
                entries.append((e.get("url") or e.get("webpage_url") or e.get("id"), e.get("title") or "",
                                e.get("duration")))
        if not entries:
            raise DownloadError("Bu listede indirilebilecek ses bulunamadı.")
        return Probe(url, True, info.get("title") or "Oynatma listesi", entries=entries,
                     total_count=total or info.get("playlist_count") or len(entries))
    return Probe(url, False, info.get("title") or "Adsız ses", duration=info.get("duration"))


# -- bölüm (başlangıç–bitiş) ------------------------------------------------------------------------

_TIME_PART = re.compile(r"^\d+(\.\d+)?$")


def parse_time(text: str) -> float:
    """«5:30», «5.30», «1:05:30», «330» ya da «5:30,5» → saniye.

    Türkiye'de saat «5.30» diye de yazıldığından iki nokta yoksa nokta ayraç sayılır;
    saniyenin kesirli kısmı virgülle yazılır («5:30,5»)."""
    raw = (text or "").strip()
    if not raw:
        raise DownloadError("Başlangıç ve bitiş zamanını yazın (ör. 5:30).")
    if ":" not in raw:
        raw = raw.replace(".", ":")
    raw = raw.replace(",", ".")
    parts = [p.strip() for p in raw.split(":")]
    try:
        # Yalnızca rakam (ve son parçada kesir) kabul edilir: «inf», «nan», «-5», «1e3» reddedilir.
        if len(parts) > 3 or not all(_TIME_PART.match(p) for p in parts) or any("." in p for p in parts[:-1]):
            raise ValueError
        nums = [float(p) for p in parts]
    except ValueError:
        raise DownloadError(f"«{text}» geçerli bir zaman değil. Dakika:saniye biçiminde yazın (ör. 5:30 ya da 1:05:30).")
    if any(n < 0 for n in nums) or any(n >= 60 for n in nums[1:]):
        raise DownloadError(f"«{text}» geçerli bir zaman değil. Saniye ve dakika 0–59 arasında olmalı.")
    seconds = 0.0
    for n in nums:
        seconds = seconds * 60 + n
    return seconds


def fmt_time(seconds: float) -> str:
    tenths = int(round(max(0.0, float(seconds)) * 10))   # önce yuvarla: 59,99 → «1:00»
    whole, frac = divmod(tenths, 10)
    h, rem = divmod(whole, 3600)
    m, s = divmod(rem, 60)
    text = f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
    if frac:
        text += f",{frac}"
    return text


def parse_section(start_text: str, end_text: str, duration=None):
    """(başlangıç, bitiş) saniye çiftini doğrular. duration biliniyorsa ona göre denetler."""
    start, end = parse_time(start_text), parse_time(end_text)
    if end <= start:
        raise DownloadError("Bitiş zamanı başlangıçtan sonra olmalı.")
    if end - start < 0.5:
        raise DownloadError("Seçilen bölüm çok kısa; en az yarım saniye olmalı.")
    if duration:
        if start >= duration:
            raise DownloadError(f"Bu ses {fmt_time(duration)} uzunluğunda; başlangıç ({fmt_time(start)}) "
                                "bundan önce olmalı.")
        end = min(end, float(duration))
    return start, end


# -- indirme ve dönüştürme ----------------------------------------------------------------------

def download(url: str, title_hint: str = "", progress=None, cancel=None, section=None) -> dict:
    """Tek bir sesi indirip kütüphaneye ekler; eklenen kaydı döndürür.

    section=(başlangıç, bitiş) verilirse yalnızca o bölüm kaydedilir. Site izin veriyorsa yt-dlp
    yalnızca o bölümü indirir (uzun videolarda çok daha hızlı); olmazsa tamamı indirilip kesilir."""
    import yt_dlp
    if _is_youtube(url):
        ensure_js_runtime(progress, cancel)
    if section:
        try:
            return _download(yt_dlp, url, title_hint, progress, cancel, section, partial=True)
        except Cancelled:
            raise
        except DownloadError as exc:
            log.warning("Bölüm indirilemedi, tamamı indirilip kesilecek: %s", str(exc).splitlines()[0])
    return _download(yt_dlp, url, title_hint, progress, cancel, section, partial=False)


def _download(yt_dlp, url, title_hint, progress, cancel, section, partial):

    def hook(d):
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        if progress and d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            if total:
                progress(0.85 * d.get("downloaded_bytes", 0) / total, None)

    with tempfile.TemporaryDirectory(prefix="okulzili_") as tmp:
        # Geçici dosya adı yalnızca kimlikten oluşur: uzun başlıklar Windows yol sınırına takılmaz.
        opts = dict(_base_opts(), format="bestaudio/best", outtmpl=os.path.join(tmp, "%(id).40B.%(ext)s"),
                    progress_hooks=[hook], windowsfilenames=True, trim_file_name=40)
        if partial:
            from yt_dlp.utils import download_range_func
            opts.update(download_ranges=download_range_func(None, [section]), ffmpeg_location=ffmpeg_exe())
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
        except Cancelled:
            raise
        except Exception as exc:  # noqa: BLE001
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            raise _friendly_error(exc)
        if info.get("_type") in ("playlist", "multi_video"):
            raise DownloadError("Bu bağlantı bir oynatma listesi; tek ses olarak indirilemez.")
        downloads = info.get("requested_downloads") or []
        src = downloads[0].get("filepath") if downloads else None
        if not src or not os.path.exists(src):
            raise DownloadError("İndirilen dosya bulunamadı.")
        title = info.get("title") or title_hint or "Adsız ses"
        cut = None
        if section:
            title = f"{title} ({fmt_time(section[0])}–{fmt_time(section[1])})"
            # İndirilen dosya yalnızca bölümse kesmeye gerek yok; tamamıysa burada kesilir.
            got = _duration(Path(src))
            wanted = section[1] - section[0]
            if not partial or got is None or got > wanted + 3:
                cut = section
        if progress:
            progress(0.88, "Ses dönüştürülüyor…")
        return _convert_and_add(src, title, source=info.get("webpage_url") or url, cancel=cancel, cut=cut,
                                trim_silence=section is None)


def import_file(path: str, cancel=None) -> dict:
    """Bilgisayardaki bir ses dosyasını kütüphaneye ekler."""
    title = Path(path).stem.replace("_", " ")
    return _convert_and_add(path, title, source=f"Bilgisayardan: {Path(path).name}", cancel=cancel)


def _convert_and_add(src: str, title: str, source: str, cancel=None, cut=None, trim_silence=True) -> dict:
    lib = library.get_library()
    item_id, target = lib.new_target(title)
    tmp = target.with_name(target.stem + ".part.opus")
    # Ses düzeyini eşitle (şarkılar aynı yükseklikte). Bölüm seçilmediyse baştaki sessizliği de kırp
    # (zil hemen duyulsun); bölüm seçildiyse tam seçilen saniyeden başlasın.
    filters = "loudnorm=I=-14:TP=-1.5:LRA=11"
    if trim_silence:
        filters = "silenceremove=start_periods=1:start_threshold=-50dB," + filters
    seek = ["-ss", f"{cut[0]:.3f}", "-to", f"{cut[1]:.3f}"] if cut else []
    cmd = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", *seek, "-i", src, "-vn", "-sn", "-dn",
           "-af", filters, "-ar", "48000", "-ac", "2", "-c:a", "libopus", "-b:a", OPUS_BITRATE, "-f", "opus", str(tmp)]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, **_hidden_window_flags())
    while True:
        try:
            _, err = proc.communicate(timeout=0.5)
            break
        except subprocess.TimeoutExpired:
            if cancel is not None and cancel.is_set():
                proc.kill()
                proc.wait()
                tmp.unlink(missing_ok=True)
                raise Cancelled()
    if proc.returncode != 0 or not tmp.exists() or tmp.stat().st_size == 0:
        tmp.unlink(missing_ok=True)
        detail = (err or b"").decode("utf-8", "replace").strip()[-300:]
        raise DownloadError(f"Ses dosyası dönüştürülemedi; dosya bozuk ya da desteklenmiyor olabilir.\n({detail})")
    tmp.replace(target)
    return lib.add(item_id, target, title, duration=_duration(target), source=source)


def _duration(path: Path):
    """Ses süresi (saniye): ffmpeg çıktısındaki «Duration» satırından okunur."""
    try:
        out = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", str(path)], capture_output=True,
                             timeout=30, **_hidden_window_flags()).stderr.decode("utf-8", "replace")
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", out)
        if m:
            h, mnt, s = m.groups()
            return int(h) * 3600 + int(mnt) * 60 + float(s)
    except (OSError, subprocess.SubprocessError, DownloadError):
        pass
    return None


def run_in_thread(fn, *args, **kwargs):
    t = threading.Thread(target=fn, args=args, kwargs=kwargs, name="kutuphane-indirme", daemon=True)
    t.start()
    return t
