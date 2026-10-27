"""Ses Kütüphanesi penceresi: internetten (yt-dlp) ya da bilgisayardan zil sesi ekleme."""

import logging
import queue
import threading

import customtkinter as ctk
from tkinter import filedialog, messagebox

from .. import downloader, library, rotation, sounds
from ..config import BELL_NAMES, BELL_TYPES
from . import theme
from .widgets import Card, ask_safely, fit_to_screen

log = logging.getLogger(__name__)


def _fmt_duration(seconds) -> str:
    if not seconds:
        return "–"
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _fmt_long(seconds) -> str:
    seconds = int(seconds or 0)
    h, rem = divmod(seconds, 3600)
    m = rem // 60
    return f"{h} saat {m} dakika" if h else f"{m} dakika"


class LibraryWindow(ctk.CTkToplevel):
    """allow_assign: «Zile ata» düğmeleri gösterilsin mi (ayarlar penceresinden açılınca hayır,
    çünkü orada zil seçimi ayarlar penceresinin kendisinden yapılır)."""

    def __init__(self, master, app, allow_assign=True, on_close=None):
        super().__init__(master)
        self.app = app
        self.allow_assign = allow_assign
        self.on_close = on_close
        self.lib = library.get_library()
        self._jobs = queue.Queue()        # arka plan iş parçacığından arayüze iletilen işler
        self._cancel = None               # sürmekte olan indirmenin iptal işareti
        self._busy = False
        self._last_added = None
        self._section_request = None

        self.title("Okul Zili – Ses Kütüphanesi")
        fit_to_screen(self, 920, 760)
        self.minsize(760, 520)
        self.configure(fg_color=theme.WINDOW_BG)
        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", self._close)

        top = ctk.CTkFrame(self, fg_color=theme.CARD_BG, corner_radius=0)
        top.pack(fill="x")
        ctk.CTkLabel(top, text="🎵  Ses Kütüphanesi", font=theme.font(22, "bold")).pack(side="left", padx=20, pady=14)

        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=12, pady=8)
        body.grid_columnconfigure(0, weight=1)
        self._build_add(body)
        self._build_list(body)
        self._build_footer()
        self.refresh()
        self._poll()
        self.after(100, self.lift)

    # -- yapı ---------------------------------------------------------------------------------

    def _build_add(self, parent):
        card = Card(parent, "İnternetten ses ekle",
                    "YouTube veya başka bir sitedeki şarkının / sesin bağlantısını yapıştırıp «İndir»e basın. "
                    "Ses otomatik olarak kısaltılmış bir adla, zil için uygun biçimde kaydedilir.")
        card.grid(row=0, column=0, sticky="ew", padx=4, pady=6)
        b = card.body
        b.grid_columnconfigure(0, weight=1)
        b.grid_columnconfigure(9, weight=0)
        row = ctk.CTkFrame(b, fg_color="transparent")
        row.grid(row=0, column=0, sticky="ew")
        row.grid_columnconfigure(0, weight=1)
        self.url = ctk.CTkEntry(row, height=38, font=theme.font(14),
                                placeholder_text="https://www.youtube.com/watch?v=…")
        self.url.grid(row=0, column=0, sticky="ew")
        self.url.bind("<Return>", lambda e: self._start())
        self.paste_btn = ctk.CTkButton(row, text="Yapıştır", width=90, height=38, fg_color="transparent",
                                       border_width=1, text_color=theme.TEXT, command=self._paste)
        self.paste_btn.grid(row=0, column=1, padx=(8, 0))
        self.download_btn = ctk.CTkButton(row, text="⬇  İndir", width=120, height=38, font=theme.font(15, "bold"),
                                          command=self._start)
        self.download_btn.grid(row=0, column=2, padx=(8, 0))

        # İsteğe bağlı bölüm seçimi (yalnızca tek ses bağlantılarında)
        sec = ctk.CTkFrame(row, fg_color="transparent")
        sec.grid(row=1, column=0, columnspan=3, sticky="w", pady=(10, 0))
        self.section_var = ctk.BooleanVar(value=False)
        self.section_cb = ctk.CTkCheckBox(sec, text="Yalnızca bir bölümünü indir", variable=self.section_var,
                                          command=self._toggle_section)
        self.section_cb.pack(side="left")
        ctk.CTkLabel(sec, text="Başlangıç").pack(side="left", padx=(18, 6))
        self.start_e = ctk.CTkEntry(sec, width=90, justify="center", placeholder_text="5:30")
        self.start_e.pack(side="left")
        ctk.CTkLabel(sec, text="–  Bitiş").pack(side="left", padx=6)
        self.end_e = ctk.CTkEntry(sec, width=90, justify="center", placeholder_text="5:35")
        self.end_e.pack(side="left")
        self.section_hint = ctk.CTkLabel(sec, text="dakika:saniye  (tek şarkı bağlantılarında; listelerde olmaz)",
                                         text_color=theme.MUTED, font=theme.font(12))
        self.section_hint.pack(side="left", padx=(10, 0))
        self._toggle_section()

        self.progress = ctk.CTkProgressBar(b, height=10)
        self.status = ctk.CTkLabel(b, text="", anchor="w", justify="left", wraplength=780)
        self.cancel_btn = ctk.CTkButton(b, text="İptal", width=90, fg_color=theme.DANGER,
                                        hover_color=theme.DANGER_HOVER, command=self._request_cancel)
        self.assign_bar = ctk.CTkFrame(b, fg_color="transparent")

        row2 = ctk.CTkFrame(b, fg_color="transparent")
        row2.grid(row=5, column=0, sticky="w", pady=(12, 0))
        ctk.CTkLabel(row2, text="Ses dosyası bilgisayarınızda ya da USB bellekte mi?").pack(side="left")
        self.file_btn = ctk.CTkButton(row2, text="Bilgisayardan ekle…", width=160, fg_color="transparent",
                                      border_width=1, text_color=theme.TEXT, command=self._add_file)
        self.file_btn.pack(side="left", padx=10)

    def _build_list(self, parent):
        self.list_card = Card(parent, "Kütüphanedeki sesler")
        self.list_card.grid(row=1, column=0, sticky="ew", padx=4, pady=6)
        self.list_body = self.list_card.body
        self.list_body.grid_columnconfigure(1, weight=1)
        self.list_body.grid_columnconfigure(9, weight=0)

    def _build_footer(self):
        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.pack(fill="x", padx=20, pady=(0, 12))
        self.footer_lbl = ctk.CTkLabel(foot, text="", text_color=theme.MUTED, font=theme.font(12))
        self.footer_lbl.pack(side="left")
        ctk.CTkButton(foot, text="Kapat", width=110, command=self._close).pack(side="right")
        self.update_btn = ctk.CTkButton(foot, text="yt-dlp'yi güncelle", width=150, fg_color="transparent",
                                        border_width=1, text_color=theme.TEXT, command=self._update_ytdlp)
        self.update_btn.pack(side="right", padx=10)

    # -- liste --------------------------------------------------------------------------------

    def _bells_using(self, sound_id):
        cfg = self.app.cfg
        names = []
        for k in BELL_TYPES:
            bell = cfg["bells"][k]
            rot = bell.get("rotation") or {}
            if rot.get("enabled") and sound_id in (rot.get("pool") or []):
                period = rotation.PERIOD_THIS.get(rot.get("period"), "Bu dönemin").lower()
                now = " – " + period + " sesi" if rotation.effective_sound(bell) == sound_id else ""
                names.append(f"{BELL_NAMES[k]} (değişen ses{now})")
            elif bell.get("sound") == sound_id:
                names.append(BELL_NAMES[k])
        names += [e.get("label") or "Ek zil" for e in cfg.get("extra_bells", []) if e.get("sound") == sound_id]
        return names

    def refresh(self):
        for w in self.list_body.winfo_children():
            w.destroy()
        items = self.lib.items()
        self.list_card.title_label.configure(text=f"Kütüphanedeki sesler ({len(items)})")
        if not items:
            ctk.CTkLabel(self.list_body, text="Kütüphane boş. Yukarıdan bir bağlantı yapıştırarak ya da bilgisayardan "
                                              "dosya seçerek ilk zil sesinizi ekleyin.",
                         text_color=theme.MUTED, wraplength=760, justify="left").grid(row=0, column=0, columnspan=6,
                                                                                    sticky="w", pady=8)
        for r, item in enumerate(sorted(items, key=lambda i: i.get("added", ""), reverse=True)):
            sid = library.PREFIX + item["id"]
            new = item["id"] == self._last_added
            bg = theme.ROW_NEXT if new else (theme.ROW_ALT if r % 2 else "transparent")
            row = ctk.CTkFrame(self.list_body, fg_color=bg, corner_radius=8)
            row.grid(row=r, column=0, columnspan=10, sticky="ew", pady=1)
            row.grid_columnconfigure(1, weight=1)
            ctk.CTkButton(row, text="▶", width=36, height=30,
                          command=lambda s=sid: self.app.player.preview_sound(s, 15)).grid(row=0, column=0,
                                                                                          rowspan=2, padx=8, pady=6)
            ctk.CTkLabel(row, text=item["title"], anchor="w", font=theme.font(14, "bold")).grid(
                row=0, column=1, sticky="ew", pady=(6, 0))
            used = self._bells_using(sid)
            info = _fmt_duration(item.get("duration"))
            if used:
                info += "   ·   Kullanan: " + ", ".join(used)
            ctk.CTkLabel(row, text=info, anchor="w", text_color=theme.MUTED, font=theme.font(12)).grid(
                row=1, column=1, sticky="ew", pady=(0, 6))
            col = 2
            if self.allow_assign:
                menu = ctk.CTkOptionMenu(row, values=[BELL_NAMES[k] for k in BELL_TYPES], width=150,
                                         command=lambda name, s=sid, m=None: self._assign(name, s))
                menu.set("Zile ata…")
                menu.grid(row=0, column=col, rowspan=2, padx=4)
                col += 1
            ctk.CTkButton(row, text="Adını değiştir", width=110, fg_color="transparent", border_width=1,
                          text_color=theme.TEXT, command=lambda i=item: self._rename(i)).grid(
                row=0, column=col, rowspan=2, padx=4)
            ctk.CTkButton(row, text="Sil", width=56, fg_color="transparent", border_width=1,
                          border_color=theme.DANGER, text_color=theme.DANGER, hover_color=theme.ROW_ALT,
                          command=lambda i=item: self._delete(i)).grid(row=0, column=col + 1, rowspan=2, padx=(4, 10))
        mb = self.lib.total_bytes() / 1024 / 1024
        self.footer_lbl.configure(text=f"{len(items)} ses · {mb:.1f} MB · yt-dlp {downloader.ytdlp_version()}")

    def _assign(self, bell_name, sound_id):
        kind = next(k for k in BELL_TYPES if BELL_NAMES[k] == bell_name)
        bells = self.app.cfg["bells"]
        bells[kind]["sound"] = sound_id
        self.app.update_config(bells=bells)
        if self.app.window is not None:
            self.app.window.flash(f"✓  {bell_name} artık «{sounds.display_name(sound_id)}» çalacak")
        self._show_status(f"✓ {bell_name} artık «{sounds.display_name(sound_id)}» sesini çalacak.", theme.SUCCESS)
        self.assign_bar.grid_remove()
        self.refresh()

    def _rename(self, item):
        dlg = ctk.CTkInputDialog(title="Adını değiştir", text=f"Yeni ad:\n(şu anki: {item['title']})")
        name = dlg.get_input()
        if name and name.strip():
            self.lib.rename(item["id"], name.strip())
            self.refresh()
            if self.app.window is not None:
                self.app.window.refresh_all()

    def _delete(self, item):
        sid = library.PREFIX + item["id"]
        used = self._bells_using(sid)
        msg = f"«{item['title']}» kütüphaneden silinsin mi?"
        if used:
            msg += ("\n\nBu ses şu zillerde kullanılıyor: " + ", ".join(used) +
                    ".\nSilinirse bu ziller için yeni ses seçene kadar Windows uyarı sesi çalar.")
        if not messagebox.askyesno("Sesi sil", msg, icon="warning", parent=self):
            return
        self.app.player.stop_preview()
        self.lib.remove(item["id"])
        if used:
            cfg = self.app.cfg
            for k in BELL_TYPES:
                if cfg["bells"][k].get("sound") == sid:
                    cfg["bells"][k]["sound"] = ""
            for e in cfg.get("extra_bells", []):
                if e.get("sound") == sid:
                    e["sound"] = ""
            rotation.remove_from_pools(cfg, sid)
            self.app.update_config()
        self.refresh()

    # -- indirme ------------------------------------------------------------------------------

    def _toggle_section(self):
        state = "normal" if self.section_var.get() and not self._busy else "disabled"
        for e in (self.start_e, self.end_e):
            e.configure(state=state)
        if self.section_var.get() and not self._busy:
            self.start_e.focus_set()

    def _section_texts(self):
        if not self.section_var.get():
            return None
        return self.start_e.get(), self.end_e.get()

    def _paste(self):
        try:
            text = self.clipboard_get()
        except Exception:  # noqa: BLE001 - pano boş
            return
        self.url.delete(0, "end")
        self.url.insert(0, text.strip())

    def _set_busy(self, busy):
        self._busy = busy
        state = "disabled" if busy else "normal"
        for w in (self.url, self.download_btn, self.paste_btn, self.file_btn, self.update_btn, self.section_cb):
            w.configure(state=state)
        self._toggle_section()
        if busy:
            self.assign_bar.grid_remove()
            self.progress.grid(row=1, column=0, sticky="ew", pady=(12, 4))
            self.progress.set(0)
            self.cancel_btn.grid(row=2, column=0, sticky="e")
        else:
            self.progress.grid_remove()
            self.cancel_btn.grid_remove()

    def _show_status(self, text, color=None):
        self.status.configure(text=text, text_color=color or theme.TEXT)
        self.status.grid(row=3, column=0, sticky="ew", pady=(4, 0))

    def _progress(self, fraction, text):
        """Arka plan iş parçacığından çağrılır."""
        def apply():
            if fraction is not None:
                self.progress.set(max(0.0, min(1.0, fraction)))
            if text:
                self._show_status(text)
        self._jobs.put(apply)

    def _poll(self):
        try:
            while True:
                self._jobs.get_nowait()()
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(100, self._poll)

    def _run(self, work, done):
        """work() arka planda çalışır; sonucu ya da hatayı done(result, error) ile arayüze döner."""
        self._cancel = threading.Event()

        def target():
            try:
                result, error = work(self._cancel), None
            except downloader.Cancelled:
                result, error = None, "iptal"
            except downloader.DownloadError as exc:
                result, error = None, str(exc)
            except Exception as exc:  # noqa: BLE001
                log.exception("Kütüphane işlemi başarısız")
                result, error = None, f"Beklenmeyen bir hata oluştu: {exc}"
            self._jobs.put(lambda: done(result, error))
        downloader.run_in_thread(target)

    def _request_cancel(self):
        if self._cancel is not None:
            self._cancel.set()
            self._show_status("İptal ediliyor…")

    def _start(self):
        if self._busy:
            return
        url = self.url.get().strip()
        if not url:
            self._show_status("Önce bir bağlantı yapıştırın.", theme.DANGER)
            return
        texts = self._section_texts()
        if texts:
            try:  # biçim hatalarını indirmeye başlamadan göster
                downloader.parse_section(*texts)
            except downloader.DownloadError as exc:
                self._show_status(str(exc), theme.DANGER)
                return
        self._section_request = texts
        self._set_busy(True)
        self._show_status("Bağlantı kontrol ediliyor…")
        self.progress.configure(mode="indeterminate")
        self.progress.start()
        self._run(lambda cancel: downloader.probe(url, cancel), self._after_probe)

    def _after_probe(self, probe, error):
        self.progress.stop()
        self.progress.configure(mode="determinate")
        if error:
            self._finish_error(error)
            return
        texts = self._section_request
        if probe.is_playlist and texts:
            self._set_busy(False)
            self._show_status("Bölüm seçimi yalnızca tek şarkı / tek ses bağlantılarında kullanılabilir; bu bağlantı "
                              "bir oynatma listesi. Listeyi indirmek için «Yalnızca bir bölümünü indir» işaretini "
                              "kaldırın ya da şarkının kendi bağlantısını yapıştırın.", theme.DANGER)
            return
        if probe.is_playlist:
            self.progress.set(0)
            self._show_status("Bu bağlantı bir oynatma listesi – onayınız bekleniyor…")
            if not self._confirm_playlist(probe):
                self._set_busy(False)
                self._show_status("Oynatma listesi indirilmedi.", theme.MUTED)
                return
            self._download_many(probe)
            return
        section = None
        if texts:
            try:
                section = downloader.parse_section(*texts, duration=probe.duration)
            except downloader.DownloadError as exc:
                self._finish_error(str(exc))
                return
        if section is None and probe.duration and probe.duration > downloader.LONG_AUDIO_SECONDS:
            if not messagebox.askyesno(
                    "Uzun ses", f"«{library.short_title(probe.title)}» {_fmt_long(probe.duration)} uzunluğunda.\n\n"
                                f"Zil için genellikle kısa sesler kullanılır; uzun sesler indirmesi uzun sürer ve "
                                f"yer kaplar. Yine de indirilsin mi?", icon="warning", parent=self):
                self._set_busy(False)
                self._show_status("İndirme yapılmadı.", theme.MUTED)
                return
        part = f" ({downloader.fmt_time(section[0])}–{downloader.fmt_time(section[1])} bölümü)" if section else ""
        self._show_status(f"İndiriliyor: {library.short_title(probe.title)}{part}")
        self._run(lambda cancel: downloader.download(probe.url, probe.title, self._progress, cancel, section=section),
                  self._after_single)

    def _confirm_playlist(self, probe) -> bool:
        n = len(probe.entries)
        extra = ""
        if probe.total_count > n:
            extra = f"\n\nListede {probe.total_count} ses var; en fazla ilk {n} tanesi indirilir."
        first = ask_safely(
            self, "Oynatma listesi", "Bu bağlantı bir OYNATMA LİSTESİ",
            f"«{library.short_title(probe.title)}» listesindeki {n} sesin TAMAMI tek tek indirilecek.{extra}\n\n"
            "Yalnızca tek bir şarkı istiyorsanız «Vazgeç»e basın ve o şarkının kendi bağlantısını yapıştırın.",
            accept_text="Listeyi indir", accept_side="left")
        if not first:
            return False
        return ask_safely(
            self, "Oynatma listesi – ikinci onay", "Emin misiniz?",
            f"{n} ses indirilecek. Bu işlem uzun sürebilir ve bilgisayarda yer kaplar.\n\n"
            "Lütfen bu mesajı okuduğunuzdan emin olun. Düğme birkaç saniye sonra etkinleşecek.",
            accept_text=f"Evet, {n} sesi indir", countdown=5, accept_side="right")

    def _download_many(self, probe):
        entries = probe.entries

        def work(cancel):
            added, failed = [], []
            for i, (url, title, _) in enumerate(entries, start=1):
                if cancel.is_set():
                    raise downloader.Cancelled()
                self._progress((i - 1) / len(entries), f"{i} / {len(entries)} indiriliyor: {library.short_title(title)}")
                try:
                    added.append(downloader.download(url, title, None, cancel))
                except downloader.Cancelled:
                    raise
                except Exception as exc:  # noqa: BLE001 - listedeki tek bir ses hatası diğerlerini durdurmasın
                    log.warning("Listeden indirilemedi (%s): %s", title, exc)
                    failed.append(title)
                self._jobs.put(self.refresh)
            return added, failed

        def done(result, error):
            self._set_busy(False)
            self.refresh()
            if error == "iptal":
                self._show_status("İndirme iptal edildi. O ana kadar indirilen sesler kütüphanede.", theme.MUTED)
            elif error:
                self._show_status(error, theme.DANGER)
            else:
                added, failed = result
                text = f"✓ Listeden {len(added)} ses kütüphaneye eklendi."
                if failed:
                    text += f" {len(failed)} ses indirilemedi."
                self._show_status(text, theme.SUCCESS if not failed else theme.TEXT)
                self.url.delete(0, "end")
        self._run(work, done)

    def _after_single(self, item, error):
        self._set_busy(False)
        if error:
            self._finish_error(error)
            return
        self._added(item)
        self.url.delete(0, "end")
        if self.section_var.get():  # bir sonraki indirmede yanlışlıkla aynı bölüm kullanılmasın
            self.section_var.set(False)
            for e in (self.start_e, self.end_e):
                e.configure(state="normal")
                e.delete(0, "end")
            self._toggle_section()

    def _added(self, item):
        self._last_added = item["id"]
        self.refresh()
        self._show_status(f"✓ Kütüphaneye eklendi: {item['title']}", theme.SUCCESS)
        if self.allow_assign:
            self._offer_assign(library.PREFIX + item["id"])

    def _offer_assign(self, sid):
        for w in self.assign_bar.winfo_children():
            w.destroy()
        ctk.CTkLabel(self.assign_bar, text="Bu sesi bir zile atamak ister misiniz?").pack(side="left", padx=(0, 8))
        for k in BELL_TYPES:
            ctk.CTkButton(self.assign_bar, text=BELL_NAMES[k], width=120, fg_color=theme.BELL_COLORS[k],
                          hover_color=theme.BELL_HOVER[k],
                          command=lambda k=k: self._assign(BELL_NAMES[k], sid)).pack(side="left", padx=3)
        self.assign_bar.grid(row=4, column=0, sticky="w", pady=(8, 0))

    def _finish_error(self, error):
        self._set_busy(False)
        if error == "iptal":
            self._show_status("İndirme iptal edildi.", theme.MUTED)
        else:
            self._show_status(error, theme.DANGER)

    def _add_file(self):
        if self._busy:
            return
        path = filedialog.askopenfilename(parent=self, title="Ses dosyası seçin",
                                          filetypes=[("Ses dosyaları", " ".join(downloader.AUDIO_FILE_TYPES)),
                                                     ("Tüm dosyalar", "*.*")])
        if not path:
            return
        self._set_busy(True)
        self.progress.configure(mode="indeterminate")
        self.progress.start()
        self._show_status("Ses dosyası dönüştürülüyor…")

        def done(item, error):
            self.progress.stop()
            self.progress.configure(mode="determinate")
            self._set_busy(False)
            if error:
                self._finish_error(error)
            else:
                self._added(item)
        self._run(lambda cancel: downloader.import_file(path, cancel), done)

    def _update_ytdlp(self):
        if self._busy:
            return
        self._set_busy(True)
        self._show_status("yt-dlp'nin en son sürümü indiriliyor…")

        def done(version, error):
            self._set_busy(False)
            if error:
                self._show_status(error, theme.DANGER)
            else:
                self._show_status(f"✓ yt-dlp {version} indirildi. Programı kapatıp yeniden açtığınızda kullanılacak.",
                                  theme.SUCCESS)
        self._run(lambda cancel: downloader.update_ytdlp(lambda f, t: self._progress(f, t)), done)

    def _close(self):
        if self._busy and not messagebox.askyesno("İndirme sürüyor", "İndirme devam ediyor. İptal edip kapatılsın mı?",
                                                  parent=self):
            return
        if self._cancel is not None:
            self._cancel.set()
        self.app.player.stop_preview()
        self.destroy()
        if self.on_close:
            self.on_close()
