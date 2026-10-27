"""Programın hazır zil seslerini WAV dosyası olarak «sesler» klasörüne yazar.

Kullanım:  python tools/sesleri_disari_aktar.py [hedef_klasör]
Sesler programın içinde (okul_zili/sounds.py) matematiksel olarak üretilir; bu betik
aynı sesleri başka bir zil sisteminde ya da bilgisayarda kullanmak için dışa aktarır.
"""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from okul_zili import sounds  # noqa: E402

FILE_NAMES = {
    "klasik": "01_klasik_okul_zili.wav",
    "dingdong": "02_ding_dong.wav",
    "westminster": "03_westminster_can_melodisi.wav",
    "melodi": "04_neseli_melodi.wav",
    "elektronik": "05_elektronik_zil.wav",
    "gong": "06_gong.wav",
    "kampana": "07_kampana_3_vurus.wav",
    "bip": "08_kisa_bip.wav",
}


def main():
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "sesler"
    target.mkdir(parents=True, exist_ok=True)
    for key, file_name in FILE_NAMES.items():
        src = sounds.builtin_path(key)
        dst = target / file_name
        shutil.copyfile(src, dst)
        print(f"{dst.name:38} {sounds.length_seconds('builtin:' + key):4.1f} sn  ({sounds.BUILTIN_SOUNDS[key]})")


if __name__ == "__main__":
    main()
