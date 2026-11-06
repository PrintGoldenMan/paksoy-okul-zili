"""İşletim sistemiyle ilgili yardımcılar (Windows ve Linux).

  * Okul saatlerinde bilgisayarın uyku moduna geçmesini engelleme
    (Windows: SetThreadExecutionState, Linux: systemd-inhibit)
  * Ses düzeyi / sessiz durumu denetimi (Windows: pycaw, Linux: wpctl ya da pactl)
  * İnternet saatiyle karşılaştırma (bilgisayar saati kaymış mı?)
  * Program beklenmedik şekilde kapanırsa yeniden başlatan «bekçi»
    (Windows: Görev Zamanlayıcı, Linux: systemd kullanıcı zamanlayıcısı)
"""

import datetime as dt
import email.utils
import logging
import os
import shutil
import socket
import struct
import subprocess
import sys
import threading
import time
import urllib.request

log = logging.getLogger(__name__)

IS_WINDOWS = os.name == "nt"
IS_LINUX = sys.platform.startswith("linux")
NO_WINDOW = {"creationflags": 0x08000000} if IS_WINDOWS else {}   # CREATE_NO_WINDOW


# -- uyku modunu engelleme ----------------------------------------------------------------------

_ES_CONTINUOUS = 0x80000000
_ES_SYSTEM_REQUIRED = 0x00000001
_awake = None
_inhibitor = None   # Linux: uykuyu engelleyen systemd-inhibit süreci


def set_keep_awake(on: bool) -> None:
    """Açıkken bilgisayar boşta kaldığı için uykuya geçmez (ekran yine kapanabilir).
    Aynı iş parçacığından (ana pencere) çağrılmalıdır."""
    global _awake
    if on == _awake:
        return
    if IS_LINUX:
        _awake = on
        _linux_keep_awake(on)
        return
    if not IS_WINDOWS:
        _awake = on
        return
    try:
        import ctypes
        flags = _ES_CONTINUOUS | (_ES_SYSTEM_REQUIRED if on else 0)
        ctypes.windll.kernel32.SetThreadExecutionState(flags)
        _awake = on
        log.info("Uyku engeli %s", "açıldı (okul saatleri)" if on else "kaldırıldı")
    except Exception as exc:  # noqa: BLE001
        log.warning("Uyku engeli ayarlanamadı: %s", exc)


def _linux_keep_awake(on):
    """systemd-inhibit, içindeki komut çalıştığı sürece uykuyu ve boşta kalma işlemini engeller.
    Komut «cat»tir ve girdisi bu programa bağlı bir borudur: program kapanınca (çökse bile) boru kapanır,
    cat biter ve engel kendiliğinden kalkar; geride uykuyu engelleyen bir süreç kalmaz."""
    global _inhibitor
    if _inhibitor is not None:
        try:
            _inhibitor.stdin.close()
            _inhibitor.wait(timeout=5)
        except Exception:  # noqa: BLE001
            try:
                _inhibitor.kill()
            except Exception:  # noqa: BLE001
                pass
        _inhibitor = None
    if not on:
        log.info("Uyku engeli kaldırıldı")
        return
    exe = shutil.which("systemd-inhibit")
    if not exe:
        log.info("systemd-inhibit bulunamadı; uyku engellenemiyor")
        return
    try:
        _inhibitor = subprocess.Popen([exe, "--what=sleep:idle", "--who=Okul Zili", "--mode=block",
                                       "--why=Okul saatleri: ziller çalmalı", "cat"],
                                      stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                      stderr=subprocess.DEVNULL)
        log.info("Uyku engeli açıldı (okul saatleri)")
    except OSError as exc:
        log.warning("Uyku engeli ayarlanamadı: %s", exc)


def keep_awake_needed(events, now: dt.datetime, before_min=30, after_min=5) -> bool:
    """İlk zilden 30 dk önce ile son zilden 5 dk sonra arasında True."""
    active = [e for e in events if not e.off]
    if not active:
        return False
    m = now.hour * 60 + now.minute
    return active[0].minute - before_min <= m <= active[-1].minute + after_min


# -- Windows ses düzeyi -------------------------------------------------------------------------

class VolumeMonitor:
    """Windows'un ana ses düzeyini arka planda 20 saniyede bir okur.
    state: None (bilinmiyor / Windows değil), ya da {"muted": bool, "level": 0..1, "device": bool}"""

    def __init__(self, interval=20):
        self.interval = interval
        self.state = None
        if IS_WINDOWS or IS_LINUX:
            threading.Thread(target=self._run, name="ses-duzeyi", daemon=True).start()

    def _run(self):
        try:
            import comtypes
            comtypes.CoInitialize()
        except Exception:  # noqa: BLE001
            pass
        while True:
            self.state = read_system_volume()
            time.sleep(self.interval)


def read_system_volume():
    if IS_LINUX:
        return _read_linux_volume()
    try:
        from pycaw.pycaw import AudioUtilities
        speakers = AudioUtilities.GetSpeakers()
    except Exception as exc:  # noqa: BLE001 - pycaw yok ya da ses aygıtı yok
        log.debug("Ses aygıtı okunamadı: %s", exc)
        return {"muted": False, "level": 0.0, "device": False} if IS_WINDOWS else None
    try:
        volume = getattr(speakers, "EndpointVolume", None)
        if volume is None:   # eski pycaw sürümleri
            from ctypes import POINTER, cast
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import IAudioEndpointVolume
            iface = speakers.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = cast(iface, POINTER(IAudioEndpointVolume))
        return {"muted": bool(volume.GetMute()), "level": float(volume.GetMasterVolumeLevelScalar()),
                "device": True}
    except Exception as exc:  # noqa: BLE001
        log.debug("Ses düzeyi okunamadı: %s", exc)
        return None


def _run_quiet(cmd, timeout=5):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)


def _read_linux_volume():
    """PipeWire (wpctl) ya da PulseAudio (pactl) ile varsayılan çıkışın düzeyi.
    Araç yoksa ya da ses sunucusuna bağlanılamazsa None (bilinmiyor: uyarı gösterilmez)."""
    import re
    try:
        if shutil.which("wpctl"):
            r = _run_quiet(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"])
            out = (r.stdout + r.stderr).strip()
            m = re.search(r"Volume:\s*([\d.]+)", out)
            if r.returncode == 0 and m:
                return {"muted": "[MUTED]" in out, "level": float(m.group(1)), "device": True}
            if "not found" in out.lower() or "no default" in out.lower():
                return {"muted": False, "level": 0.0, "device": False}
        if shutil.which("pactl"):
            mute = _run_quiet(["pactl", "get-sink-mute", "@DEFAULT_SINK@"])
            vol = _run_quiet(["pactl", "get-sink-volume", "@DEFAULT_SINK@"])
            if mute.returncode == 0 and vol.returncode == 0:
                levels = [int(x) for x in re.findall(r"(\d+)%", vol.stdout)]
                return {"muted": "yes" in mute.stdout.lower(), "device": True,
                        "level": (sum(levels) / len(levels) / 100) if levels else 1.0}
            if "no such entity" in (mute.stderr + vol.stderr).lower():
                return {"muted": False, "level": 0.0, "device": False}
    except Exception as exc:  # noqa: BLE001
        log.debug("Ses düzeyi okunamadı: %s", exc)
    return None


def _launch_first(*commands) -> bool:
    """Bulunan ilk programı açar (Linux masaüstleri farklı ayar programları kullanır)."""
    for cmd in commands:
        if shutil.which(cmd[0]):
            try:
                subprocess.Popen(cmd, start_new_session=True, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
            except OSError:
                continue
    return False


def open_sound_settings() -> bool:
    if IS_WINDOWS:
        os.startfile("ms-settings:sound")  # noqa: S606
        return True
    return _launch_first(["pavucontrol-qt"], ["pavucontrol"], ["lxqt-config-sound"],
                         ["gnome-control-center", "sound"], ["xfce4-mixer"])


# -- internet saati -----------------------------------------------------------------------------

NTP_SERVERS = ("time.windows.com", "tr.pool.ntp.org", "pool.ntp.org")
HTTP_TIME_URLS = ("https://www.google.com", "https://www.microsoft.com")


def _sntp_offset(server, timeout=3.0):
    """SNTP ile (sunucu saati − bilgisayar saati) farkını saniye olarak döndürür."""
    packet = b"\x1b" + 47 * b"\0"
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(timeout)
        t0 = time.time()
        s.sendto(packet, (server, 123))
        data, _ = s.recvfrom(48)
        t3 = time.time()
    secs, frac = struct.unpack("!II", data[40:48])
    server_time = secs - 2208988800 + frac / 2 ** 32
    return server_time - (t0 + t3) / 2


def _http_offset(url, timeout=5.0):
    """NTP kapalıysa (okul ağlarında sık) web sunucusunun «Date» başlığından farkı hesaplar (±1 sn)."""
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "OkulZili"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        date = resp.headers.get("Date")
    t1 = time.time()
    if not date:
        raise ValueError("Date başlığı yok")
    return email.utils.parsedate_to_datetime(date).timestamp() - (t0 + t1) / 2


def internet_clock_offset():
    """İnternet saatiyle fark (saniye; + ise bilgisayar geride). İnternet yoksa None."""
    for server in NTP_SERVERS:
        try:
            return _sntp_offset(server)
        except Exception:  # noqa: BLE001
            continue
    for url in HTTP_TIME_URLS:
        try:
            return _http_offset(url)
        except Exception:  # noqa: BLE001
            continue
    return None


class ClockMonitor:
    """Bilgisayar saatini birkaç saatte bir internet saatiyle karşılaştırır (internet varsa)."""

    def __init__(self, interval_hours=3, first_delay=20):
        self.offset = None          # en son ölçülen fark (saniye) ya da None
        self.checked_at = None
        self._interval = interval_hours * 3600
        self._first_delay = first_delay
        self._wake = threading.Event()
        threading.Thread(target=self._run, name="saat-denetimi", daemon=True).start()

    def check_now(self):
        self._wake.set()

    def _run(self):
        self._wake.wait(self._first_delay)
        while True:
            self._wake.clear()
            offset = internet_clock_offset()
            if offset is not None:
                self.offset = offset
                self.checked_at = time.time()
                if abs(offset) > 60:
                    log.warning("Bilgisayar saati internet saatinden %.0f saniye farklı", offset)
            self._wake.wait(self._interval if offset is not None else 900)


def open_time_settings() -> bool:
    """False dönerse ayar programı açılamadı; kullanıcıya elle nasıl düzelteceği söylenmeli."""
    if IS_WINDOWS:
        os.startfile("ms-settings:dateandtime")  # noqa: S606
        return True
    return _launch_first(["lxqt-admin-time"], ["gnome-control-center", "datetime"], ["time-admin"],
                         ["kcmshell6", "kcm_clock"], ["kcmshell5", "clock"])


def open_path(path) -> None:
    """Klasörü ya da dosyayı sistemin dosya yöneticisi / programıyla açar."""
    if IS_WINDOWS:
        os.startfile(str(path))  # noqa: S606
    else:
        _launch_first(["open" if sys.platform == "darwin" else "xdg-open", str(path)])


# -- bekçi: kapanırsa yeniden başlat --------------------------------------------------------------

WATCHDOG_TASK = "OkulZili Bekci"


def watchdog_supported() -> bool:
    """Yalnızca paketlenmiş programda (kaynak koddan çalışırken bilgisayara görev eklenmez)."""
    if not getattr(sys, "frozen", False):
        return False
    return IS_WINDOWS or (IS_LINUX and shutil.which("systemctl") is not None)


# Linux: ~/.config/systemd/user altında 5 dakikada bir çalışan kullanıcı zamanlayıcısı
_UNIT = "okulzili-bekci"


def _systemd_user_dir():
    from pathlib import Path
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return Path(base) / "systemd" / "user"


def _systemctl(*args):
    return _run_quiet(["systemctl", "--user", *args], timeout=30)


def _linux_watchdog_installed() -> bool:
    try:
        return _systemctl("is-enabled", f"{_UNIT}.timer").stdout.strip() == "enabled"
    except Exception:  # noqa: BLE001
        return False


def _linux_set_watchdog(enabled: bool):
    import shlex
    d = _systemd_user_dir()
    service, timer = d / f"{_UNIT}.service", d / f"{_UNIT}.timer"
    if not enabled:
        _systemctl("disable", "--now", f"{_UNIT}.timer")
        for f in (service, timer):
            f.unlink(missing_ok=True)
        _systemctl("daemon-reload")
        log.info("Bekçi zamanlayıcısı kaldırıldı")
        return
    d.mkdir(parents=True, exist_ok=True)
    # Grafik oturumun değişkenleri: bekçi programı açtığında pencere doğru ekranda görünsün.
    env = [f'Environment="{k}={os.environ[k]}"' for k in ("DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY",
                                                            "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS")
           if os.environ.get(k)]
    service.write_text("\n".join([
        "[Unit]", "Description=Okul Zili bekçisi (kapandıysa yeniden açar)", "",
        # Bekçi programı ayrı bir süreç olarak açıp çıkar; KillMode=process açılan programı öldürmez.
        "[Service]", "Type=oneshot", "KillMode=process", "TimeoutStartSec=60", *env,
        f"ExecStart={shlex.join([sys.executable, '--oz-watchdog'])}", ""]), encoding="utf-8")
    timer.write_text("\n".join([
        "[Unit]", "Description=Okul Zili bekçisi: 5 dakikada bir", "",
        "[Timer]", "OnBootSec=2min", "OnUnitActiveSec=5min", "", "[Install]", "WantedBy=timers.target", ""]),
        encoding="utf-8")
    _systemctl("daemon-reload")
    r = _systemctl("enable", "--now", f"{_UNIT}.timer")
    if r.returncode != 0:
        log.warning("Bekçi zamanlayıcısı kurulamadı: %s", (r.stderr or r.stdout).strip())
    else:
        log.info("Bekçi zamanlayıcısı kuruldu")


def _schtasks(*args) -> subprocess.CompletedProcess:
    return subprocess.run(["schtasks", *args], capture_output=True, text=True, timeout=30, **NO_WINDOW)


def watchdog_installed() -> bool:
    if not watchdog_supported():
        return False
    if IS_LINUX:
        return _linux_watchdog_installed()
    try:
        return _schtasks("/Query", "/TN", WATCHDOG_TASK).returncode == 0
    except Exception:  # noqa: BLE001
        return False


def set_watchdog(enabled: bool) -> None:
    """Windows Görev Zamanlayıcı'ya 5 dakikada bir programı denetleyen görev ekler/kaldırır.
    Program açıksa görev hiçbir şey yapmaz; kullanıcı programı bilerek kapattıysa da açmaz."""
    if not watchdog_supported():
        return
    if IS_LINUX:
        try:
            _linux_set_watchdog(enabled)
        except Exception as exc:  # noqa: BLE001
            log.warning("Bekçi zamanlayıcısı ayarlanamadı: %s", exc)
        return
    try:
        if enabled:
            command = f'"{sys.executable}" --oz-watchdog'
            r = _schtasks("/Create", "/TN", WATCHDOG_TASK, "/TR", command, "/SC", "MINUTE", "/MO", "5", "/F")
        else:
            if not watchdog_installed():
                return
            r = _schtasks("/Delete", "/TN", WATCHDOG_TASK, "/F")
        if r.returncode != 0:
            log.warning("Bekçi görevi ayarlanamadı: %s", (r.stderr or r.stdout).strip())
        else:
            log.info("Bekçi görevi %s", "kuruldu" if enabled else "kaldırıldı")
    except Exception as exc:  # noqa: BLE001
        log.warning("Bekçi görevi ayarlanamadı: %s", exc)
