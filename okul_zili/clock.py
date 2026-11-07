"""Programın kullandığı saat: bilgisayarın saati ya da (isteğe bağlı) internet saati.

«Saati internetten al» açıkken (ayar: use_network_time, varsayılan kapalı) zamanlayıcı, ana ekrandaki
saat ve tarih denetimleri bilgisayar saatine internetten ölçülen farkı ekleyerek çalışır. Böylece
bilgisayarın saati yanlış olsa da ziller doğru zamanda çalar. Fark system.ClockMonitor tarafından
ölçülür (SNTP, olmazsa web sunucusunun «Date» başlığı); internet yoksa son ölçülen fark kullanılır,
hiç ölçülemediyse bilgisayar saati.
"""

import datetime as dt
import logging
import threading
import time

log = logging.getLogger(__name__)

_lock = threading.Lock()
_enabled = False
_offset = None              # internet saati − bilgisayar saati (saniye); ölçülmediyse None
_last = None                # saat atlaması denetimi: (bilgisayar zamanı, _steady())
_on_jump = None             # bilgisayar saati elle değiştirilince çağrılır (yeniden ölçüm için)
_version = 0                # saat kaynağı değişince artar: zamanlayıcı geçmiş zilleri yeniden hesaplar
JUMP_SECONDS = 5.0
CHANGE_SECONDS = 1.0        # programın saati bundan çok kayarsa «saat kaynağı değişti» sayılır
_BOOTTIME = getattr(time, "CLOCK_BOOTTIME", None)


def _steady():
    """Geri alınamayan, uykuda da ilerleyen saat. Linux'ta monotonic uykuda durur (uyanınca saat
    atlamış gibi görünürdü); orada CLOCK_BOOTTIME kullanılır. Windows'ta monotonic uykuyu da sayar."""
    if _BOOTTIME is not None:
        try:
            return time.clock_gettime(_BOOTTIME)
        except OSError:
            pass
    return time.monotonic()


def _effective():
    """Bilgisayar saatine eklenen fark (kapalıysa ya da ölçülmediyse 0)."""
    return _offset if _enabled and _offset is not None else 0.0


def _changed(before):
    global _version
    if abs(_effective() - before) > CHANGE_SECONDS:
        _version += 1


def configure(enabled: bool, on_jump=None):
    global _enabled, _on_jump, _last
    with _lock:
        before = _effective()
        if bool(enabled) != _enabled:
            _last = None    # kapalıyken yapılan saat değişikliği «atlama» sayılmasın
        _enabled = bool(enabled)
        _changed(before)
    if on_jump is not None:
        _on_jump = on_jump


def set_offset(offset):
    """ClockMonitor her başarılı ölçümde çağırır."""
    global _offset
    with _lock:
        before = _effective()
        _offset = float(offset)
        _changed(before)


def version() -> int:
    """Programın saati sıçradıkça (internet saati ilk kez geldi, açıldı/kapandı) artan sayı."""
    return _version


def network_active() -> bool:
    """İnternet saati açık ve en az bir kez ölçülmüş mü?"""
    return _enabled and _offset is not None


def enabled() -> bool:
    return _enabled


def offset():
    return _offset


def _check_jump():
    """Bilgisayar saati elle ileri/geri alınırsa fark atlama kadar hemen düzeltilir (internet yokken de
    internet saati kesintisiz sürsün); ardından yeniden ölçüm istenir."""
    global _last, _offset
    wall, steady = time.time(), _steady()
    with _lock:
        last, _last = _last, (wall, steady)
        if last is None:
            return
        jump = (wall - last[0]) - (steady - last[1])
        if abs(jump) <= JUMP_SECONDS:
            return
        if _offset is not None:
            _offset -= jump
    log.info("Bilgisayar saati %+.0f saniye değiştirildi; internet saati yeniden ölçülecek", jump)
    if _on_jump is not None:
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
