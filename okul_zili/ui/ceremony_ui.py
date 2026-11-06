"""Tören düğmelerinin arayüz tarafı: ses yoksa indirme, başlatmadan önce sorma, uyarılar."""

import logging
import queue
import threading

import customtkinter as ctk
from tkinter import messagebox

from .. import ceremony, clock, downloader, library, sounds
from ..downloader import fmt_time
from . import theme
from .widgets import center_over

log = logging.getLogger(__name__)


class CeremonyDownloadDialog(ctk.CTkToplevel):
    """Tören sesini internetten indirir; bitince on_done(kütüphane kaydı) çağrılır."""

    def __init__(self, master, key, url, on_done):
        super().__init__(master)
        self.title("Tören sesi indiriliyor")
        self.resizable(False, False)
        self.configure(fg_color=theme.CARD_BG)
        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", self._cancel_clicked)
        self._on_done = on_done
        self._cancel = threading.Event()
        self._jobs = queue.Queue()
        name = ceremony.name(key)
        ctk.CTkLabel(self, text=f"«{name}» indiriliyor", font=theme.font(17, "bold")).pack(
            anchor="w", padx=22, pady=(18, 2))
        ctk.CTkLabel(self, text=url, text_color=theme.MUTED, font=theme.font(12)).pack(anchor="w", padx=22)
        self.bar = ctk.CTkProgressBar(self, width=420, progress_color=theme.ACCENT)
        self.bar.set(0)
        self.bar.pack(padx=22, pady=(14, 4))
        self.status = ctk.CTkLabel(self, text="Bağlanılıyor…", text_color=theme.MUTED, anchor="w")
        self.status.pack(fill="x", padx=22)
        ctk.CTkLabel(self, text="İlk indirmede YouTube için gereken bir araç da indirildiğinden biraz uzun "
                                "sürebilir. Ses bir kez indirilir; sonra internet gerekmez.",
                     wraplength=420, justify="left", text_color=theme.MUTED, font=theme.font(12)).pack(
            anchor="w", padx=22, pady=(6, 0))
        self.cancel_btn = ctk.CTkButton(self, text="Vazgeç", width=110, fg_color="transparent", border_width=1,
                                        text_color=theme.TEXT, command=self._cancel_clicked)
        self.cancel_btn.pack(pady=(14, 18))
        self.after(50, lambda: (center_over(self), self.lift(), self.grab_set()))

        def work():
            try:
                item, error = ceremony.download(url, name, self._progress, self._cancel), None
            except downloader.Cancelled:
                item, error = None, None
            except downloader.DownloadError as exc:
                item, error = None, str(exc)
            except Exception as exc:  # noqa: BLE001
                log.exception("Tören sesi indirilemedi")
                item, error = None, f"Beklenmeyen bir hata oluştu: {exc}"
            self._jobs.put(lambda: self._finish(item, error))
        downloader.run_in_thread(work)
        self.after(100, self._poll)

    def _progress(self, fraction, text=None):
        def show():
            if fraction is not None:
                self.bar.set(max(0.0, min(1.0, fraction)))
            if text or fraction is not None:
                self.status.configure(text=text or f"İndiriliyor… %{fraction * 100:.0f}")
        self._jobs.put(show)

    def _poll(self):
        if not self.winfo_exists():
            return
        try:
            while True:
                self._jobs.get_nowait()()
        except queue.Empty:
            pass
        except Exception:  # noqa: BLE001
            log.exception("İndirme penceresi güncellenemedi")
        if self.winfo_exists():
            self.after(100, self._poll)

    def _cancel_clicked(self):
        self._cancel.set()
        self.status.configure(text="İptal ediliyor…")
        self.cancel_btn.configure(state="disabled")

    def _finish(self, item, error):
        master = self.master
        self.grab_release()
        self.destroy()
        if error:
            messagebox.showerror("İndirilemedi", f"{error}\n\nİnternet bağlantısını kontrol edip yeniden deneyin. "
                                                 "Olmazsa Kütüphane'den «Bilgisayardan ekle…» ile USB bellekteki "
                                                 "bir dosyayı ekleyip Ayarlar → Zil Sesleri → Tören Sesleri'nden "
                                                 "seçebilirsiniz.", parent=master)
        elif item:
            self._on_done(item)


_dialog = None


def open_download(master, key, url, on_done):
    """İndirme penceresini açar; zaten açıksa öne getirir (çift tıklamayla iki kez indirilmesin)."""
    global _dialog
    if _dialog is not None and _dialog.winfo_exists():
        _dialog.lift()
        return _dialog
    _dialog = CeremonyDownloadDialog(master, key, url, on_done)
    return _dialog


def ensure_sound(master, app, key, on_ready):
    """Tören sesi hazırsa on_ready() çağrılır; değilse kütüphanede aranır ya da indirmesi önerilir."""
    cfg = app.cfg
    if ceremony.is_ready(cfg, key):
        on_ready()
        return

    def use(item):
        # İndirme uzun sürebilir; bu arada ayarlar değişmiş olabilir: güncel ayarlar okunur.
        cer = app.cfg["ceremony"]
        items = dict(cer["items"])
        items[key] = dict(items.get(key) or {}, sound=library.PREFIX + item["id"])
        app.update_config(ceremony=dict(cer, items=items))
        on_ready()

    found = ceremony.find_in_library(ceremony.url_of(cfg, key))
    if found:
        use(found)
        return
    name = ceremony.name(key)
    if messagebox.askyesno(name, f"«{name}» henüz indirilmedi.\n\nŞimdi internetten indirilsin mi? "
                                 "(Bir kez indirilir; sonra internet gerekmez.)", parent=master):
        open_download(master, key, ceremony.url_of(cfg, key), use)


def confirm_start(master, app, key) -> bool:
    """Başlatmadan önce uyarılar ve onay. True dönerse tören başlatılabilir."""
    cfg = app.cfg
    name = ceremony.name(key)
    state = app.volume.state if cfg.get("check_volume", True) else None
    if state and (not state.get("device") or state.get("muted") or state.get("level", 1) < 0.15):
        problem = ("hoparlör / ses aygıtı bulunamadı" if not state.get("device") else
                   "bilgisayarın sesi KAPALI" if state.get("muted") else
                   f"bilgisayarın ses düzeyi çok düşük (%{state['level'] * 100:.0f})")
        # Bu soru başlatma onayı yerine de geçer (iki kez sorulmaz).
        return messagebox.askyesno(name, f"Dikkat: {problem}. Marş duyulmayabilir.\n\n«{name}» yine de "
                                         "başlatılsın mı?", icon="warning", parent=master)
    if not cfg["ceremony"].get("confirm", True):
        return True
    lines = [f"«{name}» şimdi bütün okulda çalınsın mı?"]
    length = ceremony.length_seconds(cfg, key)
    if length:
        start, end = sounds.part(ceremony.sound_of(cfg, key))
        length = max(1.0, min(end or length, length) - start)
    if length:
        lines.append(f"Süresi: yaklaşık {fmt_time(length)}.")
    upcoming = _bells_during(app, length or 4 * 60)
    if upcoming:
        e = upcoming[-1]
        lines.append(f"\n{e.time_str} {e.label} tören sırasında gelecek; tören bitince birkaç saniye sonra "
                     "çalacak.")
    else:
        lines.append("\nTören bitene kadar ziller çalmaz; zamanı gelen zil törenden sonra çalar.")
    return messagebox.askyesno(name, "\n".join(lines), parent=master)


def _bells_during(app, seconds):
    now = clock.now()
    sec = now.hour * 3600 + now.minute * 60 + now.second
    out = []
    for e in app.scheduler.today_events():
        if e.off or app.scheduler.was_fired(e):
            continue
        if sec <= e.minute * 60 <= sec + seconds + 5:
            out.append(e)
    return out
