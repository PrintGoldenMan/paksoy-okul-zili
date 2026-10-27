"""Türkçe sesli anons (metin okuma).

İki motor desteklenir:
  * "edge"    : Microsoft Edge doğal sesleri (Emel / Ahmet). İnternet gerekir, ancak
                üretilen anonslar önbelleğe kaydedildiği için bir kez üretildikten sonra
                internet olmadan da çalar.
  * "offline" : Windows'ta yüklü sesler (pyttsx3). İnternet gerekmez; bilgisayarda Türkçe
                ses paketi yoksa Türkçe telaffuz düzgün olmayabilir.
"""

import asyncio
import hashlib
import logging
import os
import threading
import time

from . import paths

log = logging.getLogger(__name__)

EDGE_VOICES = {
    "tr-TR-EmelNeural": "Emel (Kadın)",
    "tr-TR-AhmetNeural": "Ahmet (Erkek)",
}
ENGINES = {"edge": "Doğal ses (internet ile üretilir, önbelleğe alınır)",
           "offline": "Windows sesleri (internetsiz)"}

_lock = threading.Lock()
# Doğal ses (internet) başarısız olursa bu süre boyunca yeniden denenmez.
EDGE_RETRY_SECONDS = 300
_edge_failed_at = -EDGE_RETRY_SECONDS


def _cache_path(text: str, tts_cfg: dict, ext: str):
    voice = tts_cfg.get("voice") if tts_cfg.get("engine") == "edge" else tts_cfg.get("offline_voice", "")
    key = f"{tts_cfg.get('engine')}|{voice}|{tts_cfg.get('rate')}|{text}"
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:20]
    return paths.tts_cache_dir() / f"{digest}.{ext}"


def _edge(text: str, tts_cfg: dict, out):
    import edge_tts  # isteğe bağlı bağımlılık

    rate = int(tts_cfg.get("rate", 0))
    voice = tts_cfg.get("voice") or "tr-TR-EmelNeural"
    if voice not in EDGE_VOICES:
        voice = "tr-TR-EmelNeural"
    tmp = out.with_suffix(".part")

    async def run():
        proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or None
        comm = edge_tts.Communicate(text, voice, rate=f"{rate:+d}%", proxy=proxy)
        await asyncio.wait_for(comm.save(str(tmp)), timeout=12)

    asyncio.run(run())
    if not tmp.exists() or tmp.stat().st_size == 0:
        raise RuntimeError("Anons sesi alınamadı")
    tmp.replace(out)


def offline_voices() -> list:
    """[(kimlik, ad)] - Türkçe sesler başta olacak şekilde."""
    try:
        import pyttsx3
        engine = pyttsx3.init()
        voices = [(v.id, v.name) for v in engine.getProperty("voices")]
        engine.stop()
    except Exception as exc:  # noqa: BLE001 - sürücü hataları çeşitli olabilir
        log.warning("Windows sesleri okunamadı: %s", exc)
        return []
    voices.sort(key=lambda v: 0 if _is_turkish(*v) else 1)
    return voices


def _is_turkish(vid: str, name: str) -> bool:
    s = f"{vid} {name}".lower()
    return "turkish" in s or "tr-tr" in s or "tr_tr" in s or "türk" in s or "tolga" in s


def _offline(text: str, tts_cfg: dict, out):
    import pyttsx3

    engine = pyttsx3.init()
    voice = tts_cfg.get("offline_voice")
    if not voice:
        for v in engine.getProperty("voices"):
            if _is_turkish(v.id, v.name):
                voice = v.id
                break
    if voice:
        engine.setProperty("voice", voice)
    base = engine.getProperty("rate") or 200
    engine.setProperty("rate", int(base * (1 + int(tts_cfg.get("rate", 0)) / 100)))
    tmp = out.with_suffix(".part.wav")
    engine.save_to_file(text, str(tmp))
    engine.runAndWait()
    engine.stop()
    if not tmp.exists() or tmp.stat().st_size == 0:
        raise RuntimeError("Windows sesi ile anons üretilemedi")
    tmp.replace(out)


def synthesize(text: str, tts_cfg: dict):
    """Anonsu ses dosyasına dönüştürür ve yolunu döndürür (başarısızsa None).

    Doğal ses başarısız olursa (ör. internet yok) Windows seslerine geçilir.
    """
    text = (text or "").strip()
    if not text:
        return None
    global _edge_failed_at
    engine = tts_cfg.get("engine", "edge")
    order = ["edge", "offline"] if engine == "edge" else ["offline", "edge"]
    targets = [(eng, _cache_path(text, dict(tts_cfg, engine=eng), "mp3" if eng == "edge" else "wav"))
               for eng in order]
    # Önce kayıtlı anonslara bak: internet yokken zil sırasında beklenmesin.
    for _, out in targets:
        if out.exists() and out.stat().st_size > 0:
            return out
    with _lock:
        for eng, out in targets:
            if out.exists() and out.stat().st_size > 0:
                return out
            if eng == "edge" and time.monotonic() - _edge_failed_at < EDGE_RETRY_SECONDS:
                continue  # internet kısa süre önce yoktu; her anonsta yeniden bekleme
            try:
                (_edge if eng == "edge" else _offline)(text, dict(tts_cfg, engine=eng), out)
                log.info("Anons üretildi (%s): %s", eng, text)
                return out
            except Exception as exc:  # noqa: BLE001
                if eng == "edge":
                    _edge_failed_at = time.monotonic()
                log.warning("Anons üretilemedi (%s): %s", eng, exc)
    return None


def prepare_async(texts, tts_cfg: dict) -> None:
    """Günün anonslarını önceden üretir; böylece zil vaktinde gecikme olmaz."""
    texts = [t for t in dict.fromkeys(texts) if t]
    if not texts:
        return

    def work():
        for t in texts:
            synthesize(t, tts_cfg)

    threading.Thread(target=work, name="anons-hazirlik", daemon=True).start()


def clear_cache() -> int:
    n = 0
    for f in paths.tts_cache_dir().iterdir():
        try:
            f.unlink()
            n += 1
        except OSError:
            pass
    return n
