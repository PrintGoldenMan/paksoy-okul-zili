"""Ana pencere: saat, sonraki zil, elle çalma düğmeleri ve günün zil çizelgesi."""

import datetime as dt
import logging
import os
import queue
import threading
import time

import customtkinter as ctk
from tkinter import messagebox

from .. import APP_NAME, __version__, config, paths, rotation, schedule, sounds, system, updater
from ..config import BELL_NAMES, LEVEL_NAMES
from ..turkish import long_date
from . import theme
from .level_dialog import LevelDialog
from .widgets import Card, fit_to_screen

log = logging.getLogger(__name__)


class MainWindow(ctk.CTk):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.title(f"{APP_NAME} – {app.cfg['school_name']}")
        fit_to_screen(self, 1200, 760)
        self.minsize(900, 580)
        self.configure(fg_color=theme.WINDOW_BG)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._set_icon()
        self._schedule_signature = None
        self._row_widgets = []
        self._settings = None
        self._library = None
        self._row_toggles = False
        self._flash_until = 0.0
        self._flash_text = ""

        self.grid_columnconfigure(0, weight=1, uniform="c")
        self.grid_columnconfigure(1, weight=1, uniform="c")
        self.grid_rowconfigure(2, weight=1)

        self._build_header()
        self._build_banner()
        self._build_left()
        self._build_right()
        self._build_statusbar()
        self._layout(compact=False)
        self.ui_jobs = queue.Queue()
        self.after(200, self._poll_background)
        self.refresh_all()
        self._tick()

    # -- yapı --------------------------------------------------------------

    def _build_header(self):
        bar = ctk.CTkFrame(self, fg_color=theme.HEADER_BG, corner_radius=0, height=64)
        bar.grid(row=0, column=0, columnspan=2, sticky="ew")
        bar.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(bar, text="🔔", font=theme.font(28), text_color="#ffd166").grid(
            row=0, column=0, rowspan=2, padx=(18, 8), pady=8)
        self.school_lbl = ctk.CTkLabel(bar, text="", font=theme.font(19, "bold"), text_color="white", anchor="w")
        self.school_lbl.grid(row=0, column=1, sticky="sw", pady=(10, 0))
        ctk.CTkLabel(bar, text="Otomatik Okul Zili", font=theme.font(12), text_color="#b9c7da",
                     anchor="w").grid(row=1, column=1, sticky="nw", pady=(0, 10))
        self.level_btn = ctk.CTkButton(bar, text="", width=150, height=34, fg_color="#2c4f80",
                                       hover_color="#365e96", command=self.open_level_dialog)
        self.update_btn = ctk.CTkButton(bar, text="", width=190, height=34, font=theme.font(13, "bold"),
                                        fg_color=theme.SUCCESS, hover_color=theme.SUCCESS_HOVER,
                                        command=self.open_update)
        self.level_btn.grid(row=0, column=3, rowspan=2, padx=6)   # 2. sütun güncelleme düğmesine ayrılmış
        ctk.CTkButton(bar, text="🎵  Kütüphane", width=140, height=34, font=theme.font(14, "bold"),
                      fg_color="#2c4f80", hover_color="#365e96",
                      command=self.open_library).grid(row=0, column=4, rowspan=2, padx=6)
        ctk.CTkButton(bar, text="⚙  Ayarlar", width=130, height=34, font=theme.font(14, "bold"),
                      fg_color="#ffffff", text_color="#1f3b63", hover_color="#dfe7f2",
                      command=self.open_settings).grid(row=0, column=5, rowspan=2, padx=(6, 18))

    def _set_icon(self):
        try:
            if os.name == "nt":
                self.iconbitmap(default=str(paths.resource("assets/okul_zili.ico")))
            else:
                import tkinter
                self._icon_img = tkinter.PhotoImage(file=str(paths.resource("assets/okul_zili.png")))
                self.iconphoto(True, self._icon_img)
        except Exception:  # noqa: BLE001 - simge bulunamazsa varsayılan kalır
            log.debug("Simge yüklenemedi", exc_info=True)

    # -- küçük ekran düzeni ----------------------------------------------------

    def _check_size(self):
        """Pencere yüksekliğine göre sıkışık düzene geçer (saat her saniye bunu çağırır)."""
        try:
            scale = ctk.ScalingTracker.get_window_scaling(self)
        except Exception:  # noqa: BLE001
            scale = 1.0
        height = self.winfo_height()
        if height <= 1:
            return
        compact = height / scale < 700
        if compact != self._compact:
            self._layout(compact)

    def _layout(self, compact):
        """Kısa ekranlarda (ör. 1366x768 ve %125 ölçek) daha sıkışık düzen kullanılır."""
        self._compact = compact
        self.clock_lbl.configure(font=ctk.CTkFont(size=54 if compact else 76, weight="bold"))
        self.date_lbl.grid_configure(pady=(8 if compact else 16, 0))
        self.progress.grid_configure(pady=(4, 10) if compact else (8, 18))
        self.next_time.configure(font=theme.font(26 if compact else 34, "bold"))
        self.next_left.configure(font=theme.font(20 if compact else 26, "bold"))
        if compact:
            self.next_note.grid_remove()
        else:
            self.next_note.grid()
        short = {"ogrenci": "Öğrenci", "ogretmen": "Öğretmen", "cikis": "Çıkış"}
        for kind, b in zip(config.BELL_TYPES, self.ring_btns):
            b.configure(text=short[kind] if compact else BELL_NAMES[kind])
        c = self._ctrl_body
        for w in self.ring_btns + [self.announce_btn, self.stop_btn]:
            w.grid_forget()
        if compact:
            # 2 sütun: Öğrenci | Öğretmen / Çıkış | Sustur
            c.grid_columnconfigure((0, 1), weight=1, uniform="b")
            self.ring_btns[0].grid(row=0, column=0, sticky="ew", padx=(0, 3), pady=3)
            self.ring_btns[1].grid(row=0, column=1, sticky="ew", padx=(3, 0), pady=3)
            self.ring_btns[2].grid(row=1, column=0, sticky="ew", padx=(0, 3), pady=3)
            self.stop_btn.grid(row=1, column=1, sticky="ew", padx=(3, 0), pady=3)
            self.announce_btn.grid(row=2, column=0, columnspan=2, sticky="ew", pady=3)
        else:
            c.grid_columnconfigure(1, weight=0, uniform="")
            for i, b in enumerate(self.ring_btns):
                b.grid(row=i, column=0, columnspan=2, sticky="ew", pady=3)
            self.announce_btn.grid(row=3, column=0, columnspan=2, sticky="ew", pady=3)
            self.stop_btn.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(10, 3))
        self._apply_announce_visibility()

    def _apply_announce_visibility(self):
        cfg = self.app.cfg
        level = cfg.get("level") or "basit"
        if level in ("kolay", "basit") or not cfg["tts"].get("enabled"):
            self.announce_btn.grid_remove()
        else:
            self.announce_btn.grid()

    def _build_banner(self):
        """Ziller kapalıyken ekranın üstünde görünen kırmızı uyarı şeridi."""
        self.banner = ctk.CTkFrame(self, fg_color=theme.DANGER, corner_radius=0)
        self.banner.grid_columnconfigure(0, weight=1)
        self.banner_lbl = ctk.CTkLabel(self.banner, text="", text_color="white", font=theme.font(17, "bold"),
                                       anchor="w")
        self.banner_lbl.grid(row=0, column=0, sticky="ew", padx=20, pady=10)
        self.banner_btn = ctk.CTkButton(self.banner, text="", width=170, height=34, font=theme.font(14, "bold"),
                                        fg_color="white", text_color=("#9e2f23", "#9e2f23"), hover_color="#fbe3e0",
                                        command=self._banner_action)
        self.banner_btn.grid(row=0, column=1, padx=20)

    def _update_banner(self, cfg, now):
        danger = True
        if not cfg.get("auto_ring", True):
            text, btn, self._banner_kind = "⚠  ZİLLER KAPALI – otomatik zil çalmayacak", "Zilleri aç", "auto"
        elif cfg.get("skip_date") == now.date().isoformat():
            text, btn, self._banner_kind = ("⚠  BUGÜN ZİLLER KAPALI – yarın otomatik olarak açılır",
                                            "Bugün de çalsın", "skip")
        elif (cfg.get("short_day") or {}).get("date") == now.date().isoformat() and \
                schedule.is_school_day(cfg, now.date()):
            minutes = cfg["short_day"].get("lesson_minutes", 30)
            text, btn, danger, self._banner_kind = (f"⏱  Bugün kısaltılmış ders ({minutes} dakika) – yarın ders "
                                                    "saatleri normale döner", "Normale dön", False, "short")
        elif self._volume_problem(cfg):
            text, btn = self._volume_problem(cfg), "Ses ayarlarını aç"
            self._banner_kind = "volume"
        elif cfg.get("check_clock", True) and self.app.clock.offset is not None and abs(self.app.clock.offset) > 60:
            off = self.app.clock.offset
            amount = f"{abs(off) / 60:.0f} dakika" if abs(off) >= 90 else f"{abs(off):.0f} saniye"
            text = (f"⏰  Bilgisayarın saati {amount} {'geri' if off > 0 else 'ileri'} – ziller yanlış zamanda "
                    f"çalabilir")
            btn, danger, self._banner_kind = "Saati düzelt", False, "clock"
        else:
            missing = [BELL_NAMES[k] for k in config.BELL_TYPES
                       if sounds.is_missing(rotation.effective_sound(cfg["bells"][k]))]
            if missing:
                danger = False
                self._banner_kind = "sound"
                text = (f"🎵  Zil sesi seçilmedi: {', '.join(missing)} – şimdilik Windows uyarı sesi çalacak")
                btn = "Kütüphaneyi aç"
            else:
                text = None
        if text is None:
            if self.banner.winfo_ismapped():
                self.banner.grid_remove()
                self.clock_card.configure(border_width=0)
            return
        color = theme.DANGER if danger else theme.WARNING
        if self.banner_lbl.cget("text") != text:
            self.banner_lbl.configure(text=text, text_color="white" if danger else theme.WARNING_TEXT)
            self.banner_btn.configure(text=btn, text_color="#9e2f23" if danger else "#7a4b00")
            self.banner.configure(fg_color=color)
        if not self.banner.winfo_ismapped():
            self.banner.grid(row=1, column=0, columnspan=2, sticky="ew")
        self.clock_card.configure(border_width=3 if danger else 0, border_color=theme.DANGER)

    def _banner_action(self):
        kind = getattr(self, "_banner_kind", "")
        if kind == "sound":
            self.open_library()
            return
        if kind == "short":
            self.app.update_config(short_day=dict(self.app.cfg.get("short_day") or {}, date=None))
            self.flash("✓  Ders saatleri normale döndü")
            return
        if kind == "volume":
            system.open_sound_settings()
            return
        if kind == "clock":
            system.open_time_settings()
            self.app.clock.check_now()
            return
        if kind == "auto":
            self.app.update_config(auto_ring=True)
        else:
            self.app.update_config(skip_date=None)
        self.flash("✓  Ziller yeniden açıldı")

    def _build_left(self):
        left = ctk.CTkFrame(self, fg_color="transparent")
        left.grid(row=2, column=0, sticky="nsew", padx=(18, 9), pady=16)
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(1, weight=1)

        # Saat ve durum
        clock = self.clock_card = ctk.CTkFrame(left, fg_color=theme.CARD_BG, corner_radius=16)
        clock.grid(row=0, column=0, sticky="ew")
        clock.grid_columnconfigure(0, weight=1)
        self.date_lbl = ctk.CTkLabel(clock, text="", font=theme.font(16), text_color=theme.MUTED)
        self.date_lbl.grid(row=0, column=0, pady=(16, 0))
        self.clock_lbl = ctk.CTkLabel(clock, text="", font=ctk.CTkFont(size=76, weight="bold"))
        self.clock_lbl.grid(row=1, column=0)
        self.status_lbl = ctk.CTkLabel(clock, text="", font=theme.font(20, "bold"), text_color=theme.ACCENT)
        self.status_lbl.grid(row=2, column=0)
        self.status_detail = ctk.CTkLabel(clock, text="", text_color=theme.MUTED)
        self.status_detail.grid(row=3, column=0, pady=(0, 10))
        self.progress = ctk.CTkProgressBar(clock, height=10, progress_color=theme.ACCENT)
        self.progress.grid(row=4, column=0, sticky="ew", padx=40, pady=(8, 18))

        # Sonraki zil + elle çalma
        lower = ctk.CTkFrame(left, fg_color="transparent")
        lower.grid(row=1, column=0, sticky="nsew", pady=(14, 0))
        lower.grid_columnconfigure((0, 1), weight=1, uniform="l")
        lower.grid_rowconfigure(0, weight=1)

        nxt = Card(lower, "Sonraki Zil")
        nxt.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        b = nxt.body
        b.grid_columnconfigure(0, weight=1)
        b.grid_columnconfigure(9, weight=0)
        self.next_chip = ctk.CTkLabel(b, text="", corner_radius=8, text_color="white",
                                      font=theme.font(15, "bold"), height=32)
        self.next_chip.grid(row=0, column=0, sticky="ew", pady=(4, 6))
        self.next_time = ctk.CTkLabel(b, text="", font=theme.font(34, "bold"))
        self.next_time.grid(row=1, column=0)
        self.next_note = ctk.CTkLabel(b, text="", text_color=theme.MUTED, wraplength=230)
        self.next_note.grid(row=2, column=0)
        self.next_left = ctk.CTkLabel(b, text="", font=theme.font(26, "bold"), text_color=theme.ACCENT)
        self.next_left.grid(row=3, column=0, pady=(6, 0))

        ctrl = Card(lower, "Elle Zil Çal")
        ctrl.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        c = ctrl.body
        c.grid_columnconfigure(0, weight=1)
        c.grid_columnconfigure(9, weight=0)
        self.ring_btns = [
            ctk.CTkButton(c, text=BELL_NAMES[kind], height=38, font=theme.font(14, "bold"),
                          fg_color=theme.BELL_COLORS[kind], hover_color=theme.BELL_HOVER[kind],
                          command=lambda k=kind: self._ring_now(k))
            for kind in config.BELL_TYPES]
        self.announce_btn = ctk.CTkButton(c, text="📢  Anons Yap", height=38, font=theme.font(14, "bold"),
                                          command=self.open_announce)
        self.stop_btn = ctk.CTkButton(c, text="■  Sustur", height=38, font=theme.font(14, "bold"),
                                      fg_color=theme.DANGER, hover_color=theme.DANGER_HOVER,
                                      command=self.app.player.stop)
        self._ctrl_body = c
        self._compact = None

        # Anahtarlar
        sw = ctk.CTkFrame(left, fg_color=theme.CARD_BG, corner_radius=16)
        sw.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        top = ctk.CTkFrame(sw, fg_color="transparent")
        top.pack(fill="x", padx=4, pady=(10, 2))
        self.auto_var = ctk.BooleanVar()
        self.skip_var = ctk.BooleanVar()
        ctk.CTkSwitch(top, text="Ziller otomatik çalsın", variable=self.auto_var, font=theme.font(14, "bold"),
                      command=self._toggle_auto).pack(side="left", padx=14)
        ctk.CTkSwitch(top, text="Yalnızca bugün zilleri kapat", variable=self.skip_var,
                      command=self._toggle_skip).pack(side="left", padx=14)
        self.short_btn = ctk.CTkButton(sw, text="⏱  Bugün kısaltılmış ders", width=200, height=30,
                                       fg_color="transparent", border_width=1, text_color=theme.TEXT,
                                       hover_color=theme.ROW_ALT, command=self.open_short_day)
        self.short_btn.pack(anchor="w", padx=18, pady=(4, 10))

    def _build_right(self):
        card = Card(self, "Bugünkü Zil Çizelgesi")
        card.grid(row=2, column=1, sticky="nsew", padx=(9, 18), pady=16)
        self.day_info = ctk.CTkLabel(card.body, text="", text_color=theme.MUTED, anchor="w")
        self.day_info.grid(row=0, column=0, columnspan=2, sticky="ew")
        legend = ctk.CTkFrame(card.body, fg_color="transparent")
        legend.grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 6))
        for kind in ("ogrenci", "ogretmen", "cikis", "ek"):
            ctk.CTkLabel(legend, text="●", text_color=theme.BELL_COLORS[kind]).pack(side="left")
            ctk.CTkLabel(legend, text=BELL_NAMES[kind], font=theme.font(12)).pack(side="left", padx=(2, 10))
        self.list_frame = ctk.CTkScrollableFrame(card.body, fg_color="transparent")
        self.list_frame.grid(row=2, column=0, columnspan=2, sticky="nsew")
        self.list_frame.grid_columnconfigure(2, weight=1)
        card.body.grid_rowconfigure(2, weight=1)
        card.body.grid_columnconfigure(0, weight=1)
        card.body.grid_columnconfigure(9, weight=0)

    def _build_statusbar(self):
        self.statusbar = ctk.CTkLabel(self, text="", anchor="w", text_color=theme.MUTED, font=theme.font(12))
        self.statusbar.grid(row=3, column=0, columnspan=2, sticky="ew", padx=20, pady=(0, 8))

    # -- güncelleme ---------------------------------------------------------

    def refresh_all(self):
        cfg = self.app.cfg
        ctk.set_appearance_mode({"light": "light", "dark": "dark"}.get(cfg["theme"], "system"))
        self.title(f"{APP_NAME} – {cfg['school_name']}" if cfg.get("school_name") else APP_NAME)
        name = cfg.get("school_name") or APP_NAME
        self.school_lbl.configure(text=name if len(name) <= 60 else name[:58] + "…")
        level = cfg.get("level") or "basit"
        self.level_btn.configure(text=f"Düzey: {LEVEL_NAMES[level]}")
        self._row_toggles = config.LEVELS.index(level) >= config.LEVELS.index("gelismis")
        self._apply_announce_visibility()
        self.auto_var.set(cfg.get("auto_ring", True))
        self.skip_var.set(cfg.get("skip_date") == dt.date.today().isoformat())
        self._schedule_signature = None
        self._row_state = None
        self._tick(reschedule=False)

    def _rebuild_list(self, events):
        for w in self._row_widgets:
            w.destroy()
        self._row_widgets = []
        if not events:
            today = dt.date.today()
            holiday = schedule.holiday_name(self.app.cfg, today)
            text = f"🎉  Bugün tatil: {holiday}" if holiday else "Bugün okul günü değil"
            text += "\nZil çalmayacak."
            nxt = schedule.next_school_day(self.app.cfg, today)
            if nxt:
                text += f"\n\nSonraki okul günü:\n{long_date(nxt[0])}, ilk zil {nxt[1].time_str}"
            lbl = ctk.CTkLabel(self.list_frame, text=text, text_color=theme.MUTED, font=theme.font(16),
                               justify="center")
            lbl.grid(row=0, column=0, columnspan=4, pady=50, sticky="ew")
            self._row_widgets.append(lbl)
            return
        for i, e in enumerate(events):
            row = ctk.CTkFrame(self.list_frame, corner_radius=8, height=40,
                               fg_color=theme.ROW_ALT if i % 2 else "transparent")
            row.grid(row=i, column=0, columnspan=3, sticky="ew", pady=1)
            row.grid_columnconfigure(2, weight=1)
            t = ctk.CTkLabel(row, text=e.time_str, font=theme.font(15, "bold"), width=60)
            t.grid(row=0, column=0, padx=(8, 4), pady=6)
            chip = ctk.CTkLabel(row, text=e.label, width=120, corner_radius=6, text_color="white",
                                fg_color=theme.BELL_COLORS[e.kind], font=theme.font(12, "bold"))
            chip.grid(row=0, column=1, padx=4)
            note = ctk.CTkLabel(row, text=e.note, anchor="w", font=theme.font(12))
            note.grid(row=0, column=2, sticky="ew", padx=(8, 4))
            toggle = None
            if self._row_toggles and e.off != "Kapalı":
                # Yalnızca bugün için bu zili kapat / aç
                toggle = ctk.CTkButton(row, text="Aç" if e.off else "Kapat", width=58, height=26,
                                       font=theme.font(12), fg_color="transparent", border_width=1,
                                       text_color=theme.TEXT, hover_color=theme.ROW_NEXT,
                                       command=lambda e=e: self._toggle_bell_today(e))
                toggle.grid(row=0, column=3, padx=(4, 8))
            row._parts = (t, chip, note, i, toggle)
            row._event = e
            self._row_widgets.append(row)

    def _style_rows(self, next_event):
        sched = self.app.scheduler
        state = (next_event.key if next_event else None,
                 tuple(sched.was_fired(r._event) for r in self._row_widgets if hasattr(r, "_event")),
                 ctk.get_appearance_mode())
        if state == getattr(self, "_row_state", None):
            return
        self._row_state = state
        for row in self._row_widgets:
            if not hasattr(row, "_event"):
                continue
            t, chip, note, i, toggle = row._parts
            e = row._event
            done = sched.was_fired(e)
            if toggle is not None and done:
                toggle.grid_remove()   # çalmış zil için «Kapat» anlamsız
            is_next = next_event is not None and e.key == next_event.key
            row.configure(fg_color=theme.ROW_NEXT if is_next else (theme.ROW_ALT if i % 2 else "transparent"))
            color = theme.MUTED if done or e.off else theme.TEXT
            t.configure(text_color=color)
            if e.off:
                text = f"🔕 {e.off}"
            else:
                text = ("✓ " if done else "") + e.note
            note.configure(text_color=color, text=text)
            grey = done or e.off
            chip.configure(fg_color=theme.DONE_CHIP if grey else theme.BELL_COLORS[e.kind],
                           text_color=theme.DONE_CHIP_TEXT if grey else "white")
        self._scroll_to(next_event)

    def _scroll_to(self, event):
        """Listeyi, sonraki zil üstte birkaç satır geçmişle görünecek şekilde kaydırır."""
        rows = [r for r in self._row_widgets if hasattr(r, "_event")]
        if not rows or event is None:
            return
        idx = next((i for i, r in enumerate(rows) if r._event.key == event.key), 0)
        try:
            self.list_frame._parent_canvas.yview_moveto(max(0.0, (idx - 2) / len(rows)))
        except Exception:  # noqa: BLE001 - customtkinter iç yapısı değişirse kaydırma yapılmaz
            pass

    def _tick(self, reschedule=True):
        now = dt.datetime.now()
        if reschedule:
            # Önce bir sonraki güncellemeyi planla: bir hata olsa bile saat durmasın.
            self.after(1000 - now.microsecond // 1000 + 5, self._tick)
        try:
            self._update(now)
        except Exception:  # noqa: BLE001
            log.exception("Ana ekran güncellenemedi")

    def _volume_problem(self, cfg):
        if not cfg.get("check_volume", True):
            return None
        state = self.app.volume.state
        if not state:
            return None
        if not state.get("device"):
            return "🔇  Hoparlör / ses aygıtı bulunamadı – ziller DUYULMAZ"
        if state.get("muted"):
            return "🔇  Bilgisayarın sesi KAPALI (sessiz) – ziller DUYULMAZ"
        if state.get("level", 1) < 0.15:
            return f"🔈  Bilgisayarın ses düzeyi çok düşük (%{state['level'] * 100:.0f}) – ziller duyulmayabilir"
        return None

    def _update(self, now):
        self._check_size()
        self.app.check_rotation(now)
        self.app.check_calendar(now)
        if self.app.cfg.get("keep_awake", True) and schedule.is_school_day(self.app.cfg, now.date()):
            system.set_keep_awake(system.keep_awake_needed(self.app.scheduler.today_events(), now))
        else:
            system.set_keep_awake(False)
        latest = self.app.updates.latest
        if latest and not self.update_btn.winfo_ismapped():
            self.update_btn.configure(text=f"⬆  Güncelleme var ({latest['version']})")
            self.update_btn.grid(row=0, column=2, rowspan=2, padx=6)
        cfg = self.app.cfg
        self.clock_lbl.configure(text=now.strftime("%H:%M:%S"))
        self.date_lbl.configure(text=long_date(now.date()))

        title, detail, prog = schedule.current_status(cfg, now)
        self.status_lbl.configure(text=title)
        self.status_detail.configure(text=detail)
        if prog is None:
            self.progress.grid_remove()
        else:
            self.progress.grid()
            self.progress.set(prog)

        events = self.app.scheduler.today_events()
        sig = (now.date(), self._row_toggles, tuple(e.key + e.note + e.off for e in events))
        if sig != self._schedule_signature:
            self._schedule_signature = sig
            self._rebuild_list(events)
            self._row_state = None
            name = schedule.holiday_name(cfg, now.date())
            if name:
                self.day_info.configure(text=f"Tatil: {name}")
            elif events:
                shifts = schedule.shifts_for_weekday(schedule.config_for_date(cfg, now.date()), now.weekday())
                active = sum(1 for e in events if not e.off)
                if len(shifts) > 1:
                    text = " + ".join(f"{name} {len(rows)} ders" for _, name, rows, _ in shifts) + f" · {active} zil"
                else:
                    text = f"{len(shifts[0][2])} ders · {active} zil"
                if active != len(events):
                    text += f" ({len(events) - active} zil kapalı)"
                if self._row_toggles:
                    text += " · «Kapat» zili yalnızca bugün susturur"
                profile = schedule.profile_name_for_date(cfg, now.date())
                if profile:
                    text += f" · Program: {profile}"
                self.day_info.configure(text=text)
            else:
                self.day_info.configure(text="Okul günü değil")

        nxt = self.app.scheduler.next_event(now)
        self._style_rows(nxt)
        if nxt is None:
            self.next_chip.configure(text="Bugün başka zil yok", fg_color=theme.DONE_CHIP,
                                     text_color=theme.DONE_CHIP_TEXT)
            self.next_time.configure(text="—")
            self.next_note.configure(text="")
            self.next_left.configure(text="")
        else:
            self.next_chip.configure(text=nxt.label, fg_color=theme.BELL_COLORS[nxt.kind], text_color="white")
            self.next_time.configure(text=nxt.time_str)
            self.next_note.configure(text=nxt.note)
            secs = max(0, nxt.minute * 60 - (now.hour * 3600 + now.minute * 60 + now.second))
            h, rem = divmod(secs, 3600)
            m, s = divmod(rem, 60)
            self.next_left.configure(text=(f"{h} sa {m:02d} dk kaldı" if h else f"{m:02d}:{s:02d} kaldı"))

        self._update_statusbar(cfg, now)
        self._update_banner(cfg, now)

    def flash(self, text, seconds=4):
        """Durum çubuğunda kısa süreli bilgi gösterir (ör. «Ayarlar kaydedildi»)."""
        self._flash_text = text
        self._flash_until = time.monotonic() + seconds if text else 0.0
        self._update_statusbar(self.app.cfg, dt.datetime.now())

    def _update_statusbar(self, cfg, now):
        color = theme.MUTED
        if time.monotonic() < self._flash_until:
            text, color = self._flash_text, theme.SUCCESS
        elif self.app.player.playing:
            text = f"🔊  Çalıyor: {self.app.now_playing}"
        elif not self.app.player.available:
            text = "⚠  Ses sistemi başlatılamadı. Hoparlör/ses kartını kontrol edip programı yeniden açın."
        elif not cfg.get("auto_ring", True):
            text = "⚠  Otomatik zil KAPALI. Ziller çalmayacak."
        elif cfg.get("skip_date") == now.date().isoformat():
            text = "⚠  Ziller yalnızca bugün için kapalı. Yarın otomatik olarak açılır."
        else:
            text = f"✓  Program çalışıyor. Ziller otomatik çalacak.   ·   {APP_NAME} {__version__}"
        if text.startswith("⚠"):
            color = theme.DANGER
        if self.statusbar.cget("text") != text:
            self.statusbar.configure(text=text, text_color=color,
                                     font=theme.font(13, "bold" if color != theme.MUTED else "normal"))

    # -- olaylar ------------------------------------------------------------

    def _ring_now(self, kind):
        if messagebox.askyesno("Zil çal", f"{BELL_NAMES[kind]} şimdi bütün okulda çalınsın mı?", parent=self):
            self.app.ring_now(kind)

    def _toggle_auto(self):
        if not self.auto_var.get() and not messagebox.askyesno(
                "Zilleri kapat", "Otomatik ziller kapatılsın mı?\n\nYeniden açana kadar HİÇBİR zil çalmaz.",
                icon="warning", parent=self):
            self.auto_var.set(True)
            return
        self.app.update_config(auto_ring=bool(self.auto_var.get()))

    def _toggle_bell_today(self, event):
        today = dt.date.today().isoformat()
        skip = dict(self.app.cfg.get("skip_today") or {})
        ids = list(skip.get("ids", [])) if skip.get("date") == today else []
        if event.bell_id in ids:
            ids.remove(event.bell_id)
        else:
            ids.append(event.bell_id)
        self.app.update_config(skip_today={"date": today, "ids": ids})

    def _toggle_skip(self):
        if self.skip_var.get() and not messagebox.askyesno(
                "Bugün zilleri kapat", "Bugün kalan bütün ziller kapatılsın mı?\n\nYarın ziller otomatik "
                                       "olarak yeniden çalar.", icon="warning", parent=self):
            self.skip_var.set(False)
            return
        self.app.update_config(skip_date=dt.date.today().isoformat() if self.skip_var.get() else None)

    def open_setup_wizard(self):
        from .setup_wizard import SetupWizard

        def done():
            if not self.app.cfg.get("level"):
                self.open_level_dialog()
        SetupWizard(self, self.app, on_done=done)

    def open_level_dialog(self):
        LevelDialog(self, self.app.cfg.get("level"), on_select=lambda lv: self.app.update_config(level=lv))

    def open_short_day(self):
        from .short_day import ShortDayDialog
        if not schedule.is_school_day(self.app.cfg, dt.date.today()):
            messagebox.showinfo("Kısaltılmış ders", "Bugün okul günü değil.", parent=self)
            return
        ShortDayDialog(self, self.app)

    def open_library(self):
        from .library_window import LibraryWindow
        if self._library is not None and self._library.winfo_exists():
            self._library.lift()
            self._library.focus_force()
            return
        self._library = LibraryWindow(self, self.app)

    def open_settings(self):
        from .settings_window import SettingsWindow
        if self._settings is not None and self._settings.winfo_exists():
            self._settings.lift()
            self._settings.focus_force()
            return
        self._settings = SettingsWindow(self, self.app)

    def open_announce(self):
        dlg = ctk.CTkInputDialog(title="Anons Yap", text="Okunacak anons metnini yazın:")
        text = dlg.get_input()
        if text and text.strip():
            self.app.player.say(text.strip())

    # -- sistem tepsisi ----------------------------------------------------------

    def _poll_background(self):
        """Arka plan iş parçacıklarından (tepsi menüsü, güncelleme) gelen işleri ana iş parçacığında yapar."""
        try:
            while True:
                self.ui_jobs.get_nowait()()
        except queue.Empty:
            pass
        except Exception:  # noqa: BLE001
            log.exception("Arka plan işi başarısız")
        tray = self.app.tray
        if tray is not None:
            try:
                while True:
                    cmd = tray.commands.get_nowait()
                    if cmd == "show":
                        self.show_window()
                    elif cmd == "silence":
                        self.app.player.stop()
                    elif cmd == "quit":
                        self.show_window()
                        self._confirm_quit()
            except queue.Empty:
                pass
        self.after(200, self._poll_background)

    def show_window(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def _on_close(self):
        tray = self.app.tray
        if self.app.cfg.get("tray_on_close", True) and tray is not None and tray.available:
            # Pencere gizlenir; program ve ziller çalışmaya devam eder.
            self.withdraw()
            if not getattr(self, "_tray_hint_shown", False):
                tray.notify("Okul Zili arka planda çalışmaya devam ediyor; ziller çalacak. Kapatmak için saatin "
                            "yanındaki zil simgesine sağ tıklayıp «Programı kapat»ı seçin.")
                self._tray_hint_shown = True
            return
        self._confirm_quit()

    def _confirm_quit(self):
        if self.app.cfg.get("confirm_exit", True) and not messagebox.askyesno(
                "Programı kapat",
                "Program kapatılırsa ziller ÇALMAZ.\n\nYine de kapatmak istiyor musunuz?",
                icon="warning", parent=self):
            return
        self.app.quit()

    # -- güncelleme ----------------------------------------------------------------

    def open_update(self):
        latest = self.app.updates.latest
        if not latest:
            return
        nxt = self.app.scheduler.next_event()
        if nxt is not None:
            now = dt.datetime.now()
            secs = nxt.minute * 60 - (now.hour * 3600 + now.minute * 60 + now.second)
            if 0 <= secs < 180:
                messagebox.showinfo("Güncelleme", "Birkaç dakika içinde zil çalacak. Lütfen zil çaldıktan sonra "
                                                  "güncelleyin.", parent=self)
                return
        notes = (latest.get("notes") or "").strip()
        if len(notes) > 700:
            notes = notes[:700].rsplit("\n", 1)[0] + "\n…"
        if not messagebox.askyesno(
                "Yeni sürüm", f"Okul Zili {latest['version']} yayınlandı (şu anki: {__version__}).\n\n"
                              f"Güncelle'ye basarsanız yeni sürüm indirilir, program kapanıp kurulur ve kendiliğinden "
                              f"yeniden açılır (yaklaşık 1 dakika). Ayarlar ve sesler korunur.\n\n{notes}\n\n"
                              f"Şimdi güncellensin mi?", parent=self):
            return
        self.flash("⬇  Güncelleme indiriliyor…", seconds=120)
        self.update_btn.configure(state="disabled", text="⬇  İndiriliyor…")

        def work():
            try:
                launched = updater.prepare_and_launch(latest)
                self.ui_jobs.put(lambda: self.app.quit_for_update() if launched else self._update_done(None))
            except Exception as exc:  # noqa: BLE001
                log.exception("Güncelleme başarısız")
                self.ui_jobs.put(lambda err=exc: self._update_done(err))
        threading.Thread(target=work, daemon=True).start()

    def _update_done(self, error):
        self.update_btn.configure(state="normal", text=f"⬆  Güncelleme var ({self.app.updates.latest['version']})")
        if error:
            messagebox.showerror("Güncelleme", f"Güncelleme indirilemedi. İnternet bağlantısını kontrol edip "
                                               f"tekrar deneyin.\n\n({error})", parent=self)
        self.flash("")
