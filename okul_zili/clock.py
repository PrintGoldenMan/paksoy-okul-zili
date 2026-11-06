"""Programın kullandığı saat: bilgisayarın saati ya da (isteğe bağlı) internet saati.

«Saati internetten al» açıkken (ayar: use_network_time, varsayılan kapalı) zamanlayıcı, ana ekrandaki
saat ve tarih denetimleri bilgisayar saatine internetten ölçülen farkı ekleyerek çalışır. Böylece
bilgisayarın saati yanlış olsa da ziller doğru zamanda çalar. Fark system.ClockMonitor tarafından
ölçülür (SNTP, olmazsa web sunucusunun «Date» başlığı); internet yoksa son ölçülen fark kullanılır,
hiç ölçülemediyse bilgisayar saati.
"""

import datetime as dt
import threading
import time

_lock = threading.Lock()
_enabled = False
_offset = None              # internet saati − bilgisayar saati (saniye); ölçülmediyse None
_last = None                # saat atlaması denetimi: (bilgisayar zamanı, monotonic)
_on_jump = None             # bilgisayar saati elle değiştirilince çağrılır (yeniden ölçüm için)
JUMP_SECONDS = 5.0


def configure(enabled: bool, on_jump=None):
    global _enabled, _on_jump
    _enabled = bool(enabled)
    if on_jump is not None:
        _on_jump = on_jump


def set_offset(offset):
    """ClockMonitor her başarılı ölçümde çağırır."""
    global _offset
    with _lock:
        _offset = float(offset)


def network_active() -> bool:
    """İnternet saati açık ve en az bir kez ölçülmüş mü?"""
    return _enabled and _offset is not None


def enabled() -> bool:
    return _enabled


def offset():
    return _offset


def _check_jump():
    """Bilgisayar saati elle ileri/geri alınırsa fark eskir: hemen yeniden ölçülsün."""
    global _last
    wall, mono = time.time(), time.monotonic()
    last, _last = _last, (wall, mono)
    if last is not None and abs((wall - last[0]) - (mono - last[1])) > JUMP_SECONDS and _on_jump is not None:
        try:
            _on_jump()
        except Exception:  # noqa: BLE001
            pass


def now() -> dt.datetime:
    if not _enabled:
        return dt.datetime.now()
    _check_jump()
    off = _offset
    return dt.datetime.now() if off is None else dt.datetime.now() + dt.timedelta(seconds=off)


def today() -> dt.date:
    return now().date()
