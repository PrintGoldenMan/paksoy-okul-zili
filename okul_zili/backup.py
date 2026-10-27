"""Tam yedek: ayarlar + ses kütüphanesi tek bir .zip dosyasında.

Yeni bir bilgisayara geçerken ya da bilgisayar sıfırlandığında her şey tek dosyadan geri yüklenir.
"""

import json
import logging
import shutil
import tempfile
import time
import zipfile
from pathlib import Path

from . import __version__, config, library

log = logging.getLogger(__name__)

SETTINGS_NAME = "ayarlar.json"
INFO_NAME = "yedek_bilgisi.json"
LIB_DIR = "kutuphane/"


def create_backup(cfg: dict, target_path) -> dict:
    """Yedeği oluşturur; {"sounds": n, "bytes": boyut} döndürür."""
    target = Path(target_path)
    tmp = target.with_name(target.name + ".part")
    items = library.get_library().items()
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(INFO_NAME, json.dumps({"program": "Okul Zili", "version": __version__,
                                           "created": time.strftime("%Y-%m-%d %H:%M"),
                                           "sounds": len(items)}, ensure_ascii=False, indent=2))
        zf.writestr(SETTINGS_NAME, json.dumps(cfg, ensure_ascii=False, indent=2))
        zf.writestr(LIB_DIR + "kutuphane.json",
                    json.dumps({"version": 1, "items": items}, ensure_ascii=False, indent=2))
        for item in items:
            src = library.library_dir() / item["file"]
            if src.exists():
                # Opus zaten sıkıştırılmış; yeniden sıkıştırmak boşuna zaman alır.
                zf.write(src, LIB_DIR + item["file"], compress_type=zipfile.ZIP_STORED)
    tmp.replace(target)
    log.info("Tam yedek alındı: %s (%d ses)", target, len(items))
    return {"sounds": len(items), "bytes": target.stat().st_size}


def read_backup_info(path) -> dict:
    with zipfile.ZipFile(path) as zf:
        names = set(zf.namelist())
        if SETTINGS_NAME not in names:
            raise ValueError("Bu dosya bir Okul Zili tam yedeği değil.")
        info = json.loads(zf.read(INFO_NAME)) if INFO_NAME in names else {}
    return info


def restore_backup(path) -> dict:
    """Yedeği geri yükler: kütüphane yedektekiyle değiştirilir, ayarlar döndürülür (uygulamak çağırana kalır)."""
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        if SETTINGS_NAME not in names:
            raise ValueError("Bu dosya bir Okul Zili tam yedeği değil.")
        with tempfile.TemporaryDirectory(prefix="okulzili_geri_") as tmp:
            for name in names:
                # Zip içindeki yolları denetle: klasör dışına dosya yazılmasın.
                if name.startswith("/") or ".." in Path(name).parts:
                    raise ValueError(f"Yedek dosyasında geçersiz yol: {name}")
            zf.extractall(tmp)
            cfg = config.import_from(Path(tmp) / SETTINGS_NAME)
            src_lib = Path(tmp) / LIB_DIR
            if (src_lib / "kutuphane.json").exists():
                dest = library.library_dir()
                for f in src_lib.iterdir():
                    if f.suffix == ".opus":
                        shutil.copyfile(f, dest / f.name)
                shutil.copyfile(src_lib / "kutuphane.json", dest / "kutuphane.json")
                library._library = None   # yeni listeyle yeniden yüklensin
    log.info("Tam yedek geri yüklendi: %s", path)
    return cfg
