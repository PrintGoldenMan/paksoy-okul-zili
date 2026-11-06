"""toren_kaynak/ klasöründeki ses dosyalarından okul_zili/gomulu_sesler.py modülünü üretir.

Kullanım:  python tools/gomulu_sesler_olustur.py
toren_kaynak/ içine «istiklal.<uzantı>» ve «saygi.<uzantı>» adıyla herhangi bir ses dosyası konur
(mp3, m4a, webm, opus, ogg, wav, flac). Dosyalar yüksek kaliteli Opus'a (128 kb/sn, 48 kHz, stereo)
çevrilir; ses düzeyi eşitlenmez ve sessizlik kırpılmaz (saygı duruşunun sessiz dakikası korunur).
Sonuç modülün içine bayt (base64) olarak yazılır; program ilk kullanımda bunları veri klasörüne
çıkarır (sounds.py). İsteğe bağlı «<ad>.json» dosyası kaynağı belirtir: {"webpage_url": …, "title": …}.
"""

import base64
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "toren_kaynak"
OUT = ROOT / "okul_zili" / "gomulu_sesler.py"
NAMES = {"istiklal": "İstiklal Marşı", "saygi": "Saygı Duruşu + İstiklal Marşı"}
CHUNK = 4000
EXTS = (".opus", ".ogg", ".webm", ".m4a", ".mp3", ".wav", ".flac", ".aac")


def ffmpeg():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def find_source(key):
    for ext in EXTS:
        p = SRC / f"{key}{ext}"
        if p.exists():
            return p
    raise SystemExit(f"Bulunamadı: {SRC / key}.(mp3/m4a/opus/…)")


def to_opus(src, out):
    subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-vn", "-sn", "-dn",
                    "-map_metadata", "-1", "-ar", "48000", "-ac", "2", "-c:a", "libopus", "-b:a", "128k",
                    "-f", "opus", str(out)], check=True)


def duration(path):
    err = subprocess.run([ffmpeg(), "-hide_banner", "-i", str(path)],
                         capture_output=True, text=True).stderr
    h, m, s = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", err).groups()
    return round(int(h) * 3600 + int(m) * 60 + float(s), 2)


def main():
    lines = ['"""Programla gelen tören sesleri (Opus, base64 ile bayt olarak gömülü).',
             "",
             "Bu dosya tools/gomulu_sesler_olustur.py ile üretilir; elle düzenlemeyin.",
             '"""',
             "",
             "SESLER = {"]
    tmp = Path(tempfile.mkdtemp(prefix="gomulu_"))
    for key, name in NAMES.items():
        path = tmp / f"{key}.opus"
        to_opus(find_source(key), path)
        data = path.read_bytes()
        meta = json.loads((SRC / f"{key}.json").read_text(encoding="utf-8")) if (SRC / f"{key}.json").exists() else {}
        b64 = base64.b64encode(data).decode("ascii")
        lines.append(f"    {key!r}: {{")
        lines.append(f"        'ad': {name!r},")
        lines.append(f"        'sure': {duration(path)!r},")
        lines.append(f"        'kaynak': {meta.get('webpage_url', '')!r},")
        lines.append(f"        'baslik': {meta.get('title', '')!r},")
        lines.append(f"        'boyut': {len(data)},")
        lines.append(f"        'sha256': {hashlib.sha256(data).hexdigest()!r},")
        lines.append("        'veri': (")
        for i in range(0, len(b64), CHUNK):
            lines.append(f"            '{b64[i:i + CHUNK]}'")
        lines.append("        ),")
        lines.append("    },")
        print(f"{key}: {len(data) / 1024:.0f} KB, {duration(path)} sn")
    lines.append("}")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Yazıldı: {OUT} ({OUT.stat().st_size / 1024 / 1024:.1f} MB)")


if __name__ == "__main__":
    sys.exit(main())
