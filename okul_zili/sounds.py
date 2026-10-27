"""Programla birlikte gelen hazır zil sesleri.

Sesler ilk kullanımda matematiksel olarak üretilip WAV dosyası olarak kaydedilir,
böylece programla birlikte ayrıca ses dosyası dağıtmaya gerek kalmaz.
"""

import array
import math
import wave
from pathlib import Path

from . import paths

RATE = 22050
SYNTH_VERSION = 1

BUILTIN_SOUNDS = {
    "klasik": "Klasik Okul Zili",
    "dingdong": "Ding-Dong",
    "westminster": "Westminster Çan Melodisi",
    "melodi": "Neşeli Melodi",
    "elektronik": "Elektronik Zil",
    "gong": "Gong",
    "kampana": "Kampana (3 vuruş)",
    "bip": "Kısa Bip",
}
NO_SOUND = "none"
NO_SOUND_NAME = "(Zil sesi yok, yalnızca anons)"

# Nota frekansları
C4, D4, E4, F4, G4, A4, B4 = 261.63, 293.66, 329.63, 349.23, 392.00, 440.00, 493.88
C5, D5, E5, F5, G5, A5, B5, C6 = 523.25, 587.33, 659.25, 698.46, 783.99, 880.00, 987.77, 1046.50

# Çan benzeri (inharmonik) kısmi tonlar: (frekans oranı, genlik, sönümlenme hızı)
BELL_PARTIALS = [(0.5, 0.35, 1.2), (1.0, 1.0, 1.6), (1.19, 0.45, 2.2), (1.5, 0.3, 2.6),
                 (2.0, 0.35, 3.0), (2.74, 0.2, 4.0), (3.76, 0.1, 5.5)]
MARIMBA_PARTIALS = [(1.0, 1.0, 5.0), (3.93, 0.25, 14.0), (9.2, 0.05, 25.0)]
GONG_PARTIALS = [(1.0, 1.0, 0.6), (1.48, 0.6, 0.8), (2.11, 0.5, 1.0), (2.66, 0.35, 1.3),
                 (3.4, 0.2, 1.8), (4.7, 0.12, 2.4)]


def _buffer(seconds: float) -> list:
    return [0.0] * int(seconds * RATE)


def _strike(buf, at: float, freq: float, partials, amp=1.0, length=None):
    """Belirtilen anda sönümlenen bir vuruş (çan/marimba) ekler."""
    start = int(at * RATE)
    end = len(buf) if length is None else min(len(buf), start + int(length * RATE))
    two_pi = 2 * math.pi
    for ratio, p_amp, decay in partials:
        f = freq * ratio
        if f >= RATE / 2:
            continue
        w = two_pi * f / RATE
        a = amp * p_amp
        k = math.exp(-decay / RATE)
        env = a
        for i in range(start, end):
            buf[i] += env * math.sin(w * (i - start))
            env *= k
            if env < 1e-4:
                break


def _tone(buf, at: float, dur: float, freq: float, amp=0.5, harmonics=(1.0, 0.0, 0.3, 0.0, 0.15)):
    """Yumuşak giriş/çıkışlı sabit ton (bip ve elektronik ziller için)."""
    start, n = int(at * RATE), int(dur * RATE)
    fade = int(0.01 * RATE)
    for i in range(n):
        idx = start + i
        if idx >= len(buf):
            break
        t = i / RATE
        env = min(1.0, i / fade, (n - i) / fade)
        s = 0.0
        for h, h_amp in enumerate(harmonics, start=1):
            if h_amp:
                s += h_amp * math.sin(2 * math.pi * freq * h * t)
        buf[idx] += amp * env * s


def _classic_bell():
    """Elektrikli okul zili: tokmağın çana hızla vurmasıyla oluşan titreşimli ses."""
    dur = 4.0
    buf = _buffer(dur + 0.8)
    base = 1180.0
    partials = [(1.0, 1.0), (2.32, 0.5), (4.25, 0.3), (6.63, 0.15)]
    hammer_hz = 19.0
    n = int(dur * RATE)
    release = int(0.8 * RATE)
    for i in range(n + release):
        t = i / RATE
        # Tokmak vuruşları: her vuruşta parlak bir atak, ardından kısa sönüm.
        phase = (t * hammer_hz) % 1.0
        hit = 0.55 + 0.45 * math.exp(-phase * 6)
        env = 1.0 if i < n else math.exp(-(i - n) / RATE * 6)
        attack = min(1.0, i / (0.01 * RATE))
        s = 0.0
        for ratio, amp in partials:
            s += amp * math.sin(2 * math.pi * base * ratio * t + 0.3 * math.sin(2 * math.pi * 6 * t))
        buf[i] = s * hit * env * attack
    return buf


def _dingdong():
    buf = _buffer(5.0)
    for rep in range(2):
        _strike(buf, rep * 2.2, E5, BELL_PARTIALS, 1.0)
        _strike(buf, rep * 2.2 + 0.7, C5, BELL_PARTIALS, 1.0)
    return buf


def _westminster():
    notes = [E5, C5, D5, G4, G4, D5, E5, C5]
    buf = _buffer(len(notes) * 0.6 + 2.5)
    for i, f in enumerate(notes):
        gap = 0.25 if i == 4 else 0.0
        _strike(buf, i * 0.6 + gap, f, BELL_PARTIALS, 0.9)
    return buf


def _melody():
    notes = [(C5, 0.0), (E5, 0.18), (G5, 0.36), (C6, 0.54), (G5, 0.9), (C6, 1.08),
             (E5, 1.6), (G5, 1.78), (C6, 1.96)]
    buf = _buffer(3.2)
    for f, t in notes:
        _strike(buf, t, f, MARIMBA_PARTIALS, 1.0, length=1.2)
    return buf


def _electronic():
    buf = _buffer(3.0)
    t = 0.0
    while t < 2.8:
        _tone(buf, t, 0.17, 880.0, 0.45)
        _tone(buf, t + 0.18, 0.17, 659.25, 0.45)
        t += 0.36
    return buf


def _gong():
    buf = _buffer(6.5)
    _strike(buf, 0.0, 130.0, GONG_PARTIALS, 1.0)
    return buf


def _kampana():
    buf = _buffer(5.0)
    for i in range(3):
        _strike(buf, i * 1.1, A4, BELL_PARTIALS, 1.0)
    return buf


def _beep():
    buf = _buffer(1.3)
    for i in range(3):
        _tone(buf, i * 0.4, 0.25, 1000.0, 0.6, harmonics=(1.0,))
    return buf


_GENERATORS = {
    "klasik": _classic_bell, "dingdong": _dingdong, "westminster": _westminster,
    "melodi": _melody, "elektronik": _electronic, "gong": _gong, "kampana": _kampana,
    "bip": _beep,
}


def _write_wav(buf: list, path: Path) -> None:
    peak = max(1e-9, max(abs(x) for x in buf))
    scale = 0.85 * 32767 / peak
    fade = int(0.02 * RATE)
    n = len(buf)
    data = array.array("h", (
        int(buf[i] * scale * (min(1.0, (n - i) / fade))) for i in range(n)
    ))
    tmp = path.with_suffix(".tmp")
    with wave.open(str(tmp), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(data.tobytes())
    tmp.replace(path)


def builtin_path(name: str) -> Path:
    """Hazır sesin dosya yolunu döndürür; dosya yoksa üretir."""
    if name not in _GENERATORS:
        name = "klasik"
    path = paths.builtin_sound_dir() / f"{name}_v{SYNTH_VERSION}.wav"
    if not path.exists():
        _write_wav(_GENERATORS[name](), path)
    return path


def ensure_all() -> None:
    for name in _GENERATORS:
        builtin_path(name)


def resolve(sound_id: str):
    """'builtin:klasik' / 'file:C:/...' / 'none' -> dosya yolu veya None."""
    if not sound_id or sound_id == NO_SOUND:
        return None
    if sound_id.startswith("builtin:"):
        return builtin_path(sound_id.split(":", 1)[1])
    if sound_id.startswith("file:"):
        p = Path(sound_id.split(":", 1)[1])
        return p if p.exists() else builtin_path("klasik")
    return builtin_path("klasik")


def length_seconds(sound_id: str):
    """Ses dosyasının kendi uzunluğu (saniye); bilinmiyorsa None."""
    path = resolve(sound_id)
    if path is None:
        return None
    try:
        if str(path).lower().endswith(".wav"):
            with wave.open(str(path)) as w:
                return w.getnframes() / float(w.getframerate())
        import pygame
        return pygame.mixer.Sound(str(path)).get_length()
    except Exception:  # noqa: BLE001 - okunamayan dosya
        return None


def display_name(sound_id: str) -> str:
    if not sound_id or sound_id == NO_SOUND:
        return NO_SOUND_NAME
    if sound_id.startswith("builtin:"):
        return BUILTIN_SOUNDS.get(sound_id.split(":", 1)[1], "Klasik Okul Zili")
    if sound_id.startswith("file:"):
        return "Dosya: " + Path(sound_id.split(":", 1)[1]).name
    return sound_id
