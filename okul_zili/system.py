"""İşletim sistemiyle ilgili yardımcılar (çoğu yalnızca Windows'ta etkindir).

  * Okul saatlerinde bilgisayarın uyku moduna geçmesini engelleme
  * Windows ses düzeyi / sessiz durumu denetimi
  * İnternet saatiyle karşılaştırma (bilgisayar saati kaymış mı?)
  * Program beklenmedik şekilde kapanırsa yeniden başlatan «bekçi» zamanlanmış görevi
"""

import datetime as dt
import email.utils
import logging
import os
import socket
import struct
import subprocess
import sys
import threading
import time
import urllib.request

log = logging.getLogger(__name__)

IS_WINDOWS = os.name == "nt"
NO_WINDOW = {"creationflags": 0x08000000} if IS_WINDOWS else {}   # CREATE_NO_WINDOW


# -- uyku modunu engelleme ----------------------------------------------------------------------

_ES_CONTINUOUS = 0x80000000
_ES_SYSTEM_REQUIRED = 0x00000001
_awake = None


def set_keep_awake(on: bool) -> None:
    """Açıkken Windows boşta kaldığı için uykuya geçmez (ekran yine kapanabilir).
    Aynı iş parçacığından (ana pencere) çağrılmalıdır."""
    global _awake
    if on == _awake or not IS_WINDOWS:
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
        if IS_WINDOWS:
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


def open_sound_settings():
    if IS_WINDOWS:
        os.startfile("ms-settings:sound")  # noqa: S606


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


def open_time_settings():
    if IS_WINDOWS:
        os.startfile("ms-settings:dateandtime")  # noqa: S606


# -- bekçi: kapanırsa yeniden başlat --------------------------------------------------------------

WATCHDOG_TASK = "OkulZili Bekci"


def watchdog_supported() -> bool:
    return IS_WINDOWS and getattr(sys, "frozen", False)


def _schtasks(*args) -> subprocess.CompletedProcess:
    return subprocess.run(["schtasks", *args], capture_output=True, text=True, timeout=30, **NO_WINDOW)


def watchdog_installed() -> bool:
    if not watchdog_supported():
        return False
    try:
        return _schtasks("/Query", "/TN", WATCHDOG_TASK).returncode == 0
    except Exception:  # noqa: BLE001
        return False


def set_watchdog(enabled: bool) -> None:
    """Windows Görev Zamanlayıcı'ya 5 dakikada bir programı denetleyen görev ekler/kaldırır.
    Program açıksa görev hiçbir şey yapmaz; kullanıcı programı bilerek kapattıysa da açmaz."""
    if not watchdog_supported():
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
