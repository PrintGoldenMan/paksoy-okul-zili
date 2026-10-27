"""Programın veri klasörleri (ayarlar, sesler, anons önbelleği, kayıtlar)."""

import os
import sys
from pathlib import Path


def data_dir() -> Path:
    # Taşınabilir kullanım: programın yanında "tasinabilir.txt" varsa veriler oraya yazılır.
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
    if (base / "tasinabilir.txt").exists():
        root = base / "veriler"
    elif os.name == "nt" and os.environ.get("APPDATA"):
        root = Path(os.environ["APPDATA"]) / "OkulZili"
    else:
        root = Path.home() / ".okul_zili"
    root.mkdir(parents=True, exist_ok=True)
    return root


def sub_dir(name: str) -> Path:
    d = data_dir() / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_file() -> Path:
    return data_dir() / "ayarlar.json"


def builtin_sound_dir() -> Path:
    return sub_dir("hazir_sesler")


def tts_cache_dir() -> Path:
    return sub_dir("anons_onbellek")


def log_file() -> Path:
    return data_dir() / "kayit.log"
