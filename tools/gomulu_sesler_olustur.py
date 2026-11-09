"""toren_kaynak/ klasöründeki ses dosyalarından okul_zili/gomulu_sesler.py modülünü üretir
(tören sesleri ve programla gelen zil sesi «zil.<uzantı>»).

Kullanım:  python tools/gomulu_sesler_olustur.py
toren_kaynak/ içine «istiklal.<uzantı>» ve «saygi.<uzantı>» adıyla herhangi bir ses dosyası konur
(mp3, m4a, webm, opus, ogg, wav, flac). Dosyalar yüksek kaliteli Opus'a (160 kb/sn, 48 kHz, stereo)
çevrilir. Ses düzeyi eşitlenmez; yalnızca en baştaki ve en sondaki sessizlik kırpılır (düğmeye basınca ses
hemen başlasın), aradaki sessiz bölümlere (ör. saygı duruşu) dokunulmaz.
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
NAMES = {"istiklal": "İstiklal Marşı", "saygi": "Saygı Duruşu + İstiklal Marşı", "zil": "Zil Sesi (Für Elise)"}
# Yalnızca baştaki bölüm saklanacak sesler (saniye) ve zilin kendiliğinden durduğu yer («bitis», saniye):
# Für Elise'in açılış cümlesi uzun tutulan La notasıyla biter; zil orada yumuşakça susar.
EN_FAZLA = {"zil": 15.0}
# Bitiş, kaynak kaydın zaman çizelgesindedir (açılış cümlesinin La notası 10,54 sn'de söner; 10,7 sn'de
# yeni cümle başlar). Baştan kırpılan kısım düşülerek gömülü sesteki «bitis» hesaplanır.
BITIS_KAYNAKTA = {"zil": 10.54}
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


# Baştaki ve sondaki sessizlik: baştan kırp, ters çevir, (sondaki) baştan kırp, geri çevir.
# Kısa bir sessizlik payı bırakılır; aradaki sessizliklere dokunulmaz.
EDGE_TRIM = ("silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.2,areverse,"
             "silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.5,areverse")


def first_note(src, threshold_db=-42.0, hold=0.06, window=0.02):
    """İlk notanın başladığı saniye: ses düzeyinin «hold» süre boyunca eşiği aştığı ilk yer. Kayıttaki taban
    gürültüsü (hışırtı, ~-50 dBFS) ve kısa tıklamalar sayılmaz."""
    import array
    import math
    rate = 16000
    raw = subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-t", "10", "-i", str(src), "-ac", "1",
                          "-ar", str(rate), "-f", "s16le", "-"], capture_output=True, check=True).stdout
    pcm = array.array("h")
    pcm.frombytes(raw[:len(raw) // 2 * 2])
    n = int(rate * window)
    levels = []
    for i in range(0, len(pcm) - n, n):
        rms = math.sqrt(sum(x * x for x in pcm[i:i + n]) / n) or 1e-9
        levels.append(20 * math.log10(rms / 32768))
    need = max(1, round(hold / window))
    for i in range(len(levels) - need):
        if all(v > threshold_db for v in levels[i:i + need]):
            return max(0.0, (i - 1) * window)   # notanın hemen önünden (20 ms pay)
    return 0.0


def to_opus(src, out, limit=None, start=0.0):
    if limit:
        # İlk notadan başlanır (baştaki sessizlik ve hışırtı atılır); kesim yeri tıklamasın diye 15 ms'lik
        # açılış; ilk «limit» saniye alınır, sonu yumuşakça kısılır.
        seek = ["-ss", f"{start:.3f}"]
        af = f"afade=t=in:d=0.015,atrim=0:{limit},afade=t=out:st={limit - 0.5}:d=0.5"
    else:
        seek, af = [], EDGE_TRIM
    subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", *seek, "-i", str(src), "-vn", "-sn",
                    "-dn", "-map_metadata", "-1", "-af", af, "-ar", "48000", "-ac", "2", "-c:a", "libopus",
                    "-b:a", "160k", "-f", "opus", str(out)], check=True)


def existing():
    """Kaynağı artık depoda olmayan sesler mevcut modülden olduğu gibi korunur."""
    try:
        sys.path.insert(0, str(ROOT))
        from okul_zili import gomulu_sesler
        return gomulu_sesler.SESLER
    except ImportError:
        return {}


def has_source(key):
    return any((SRC / f"{key}{ext}").exists() for ext in EXTS)


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
    old = existing()
    for key, name in NAMES.items():
        if not has_source(key) and key in old:
            info = old[key]
            b64 = "".join(info["veri"])
            fields = {k: v for k, v in info.items() if k != "veri"}
            print(f"{key}: kaynak yok, mevcut ses korundu")
        else:
            path = tmp / f"{key}.opus"
            src = find_source(key)
            start = first_note(src) if key in EN_FAZLA else 0.0
            to_opus(src, path, EN_FAZLA.get(key), start)
            data = path.read_bytes()
            meta_file = SRC / f"{key}.json"
            meta = json.loads(meta_file.read_text(encoding="utf-8")) if meta_file.exists() else {}
            b64 = base64.b64encode(data).decode("ascii")
            fields = {"ad": name, "sure": duration(path), "kaynak": meta.get("webpage_url", ""),
                      "baslik": meta.get("title", ""), "boyut": len(data),
                      "sha256": hashlib.sha256(data).hexdigest()}
            if key in BITIS_KAYNAKTA:
                fields["bitis"] = round(BITIS_KAYNAKTA[key] - start, 2)
                print(f"{key}: ilk nota {start:.2f} sn'de; baştan kırpıldı, zil {fields['bitis']} sn çalar")
            print(f"{key}: {len(data) / 1024:.0f} KB, {fields['sure']} sn")
        lines.append(f"    {key!r}: {{")
        for field, value in fields.items():
            lines.append(f"        {field!r}: {value!r},")
        lines.append("        'veri': (")
        for i in range(0, len(b64), CHUNK):
            lines.append(f"            '{b64[i:i + CHUNK]}'")
        lines.append("        ),")
        lines.append("    },")
    lines.append("}")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Yazıldı: {OUT} ({OUT.stat().st_size / 1024 / 1024:.1f} MB)")


if __name__ == "__main__":
    sys.exit(main())
