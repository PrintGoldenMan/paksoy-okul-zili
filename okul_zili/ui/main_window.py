"""Ana pencere: saat, sonraki zil, elle çalma düğmeleri ve günün zil çizelgesi."""

import datetime as dt
import logging

import customtkinter as ctk
from tkinter import messagebox

from .. import APP_NAME, __version__, config, schedule
from ..config import BELL_NAMES, LEVEL_NAMES
from ..turkish import long_date
from . import theme
from .level_dialog import LevelDialog
from .widgets import Card

log = logging.getLogger(__name__)


class MainWindow(ctk.CTk):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.title(f"{APP_NAME} – {app.cfg['school_name']}")
        self.geometry("1180x740")
        self.minsize(980, 640)
        self.configure(fg_color=theme.WINDOW_BG)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._schedule_signature = None
        self._row_widgets = []
        self._settings = None
        self._row_toggles = False

        self.grid_columnconfigure(0, weight=5, uniform="c")
        self.grid_columnconfigure(1, weight=4, uniform="c")
        self.grid_rowconfigure(1, weight=1)

        self._build_header()
        self._build_left()
        self._build_right()
        self._build_statusbar()
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
        self.level_btn.grid(row=0, column=2, rowspan=2, padx=6)
        ctk.CTkButton(bar, text="⚙  Ayarlar", width=130, height=34, font=theme.font(14, "bold"),
                      fg_color="#ffffff", text_color="#1f3b63", hover_color="#dfe7f2",
                      command=self.open_settings).grid(row=0, column=3, rowspan=2, padx=(6, 18))

    def _build_left(self):
        left = ctk.CTkFrame(self, fg_color="transparent")
        left.grid(row=1, column=0, sticky="nsew", padx=(18, 9), pady=16)
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(1, weight=1)

        # Saat ve durum
        clock = ctk.CTkFrame(left, fg_color=theme.CARD_BG, corner_radius=16)
        clock.grid(row=0, column=0, sticky="ew")
        clock.grid_columnconfigure(0, weight=1)
        self.date_lbl = ctk.CTkLabel(clock, text="", font=theme.font(16), text_color=theme.MUTED)
        self.date_lbl.grid(row=0, column=0, pady=(16, 0))
        self.clock_lbl = ctk.CTkLabel(clock, text="", font=ctk.CTkFont(size=76, weight="bold"))
        self.clock_lbl.grid(row=1, column=0)
        self.status_lbl = ctk.CTkLabel(clock, text="", font=theme.font(20, "bold"), text_color=theme.ACCENT)
        self.status_lbl.grid(row=2, column=0)
        self.status_detail = ctk.CTkLabel(clock, text="", text_color=theme.MUTED)
        self.status_detail.grid(row=3, column=0)
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
        self.next_left = ctk.CTkLabel(b, text="", font=theme.font(18, "bold"), text_color=theme.ACCENT)
        self.next_left.grid(row=3, column=0, pady=(6, 0))

        ctrl = Card(lower, "Elle Zil Çal")
        ctrl.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        c = ctrl.body
        c.grid_columnconfigure(0, weight=1)
        c.grid_columnconfigure(9, weight=0)
        for i, kind in enumerate(config.BELL_TYPES):
            ctk.CTkButton(c, text=BELL_NAMES[kind], height=38, font=theme.font(14, "bold"),
                          fg_color=theme.BELL_COLORS[kind], hover_color=theme.BELL_HOVER[kind],
                          command=lambda k=kind: self.app.ring_now(k)).grid(row=i, column=0, sticky="ew", pady=3)
        self.announce_btn = ctk.CTkButton(c, text="📢  Anons Yap", height=38, font=theme.font(14, "bold"),
                                          command=self.open_announce)
        self.announce_btn.grid(row=3, column=0, sticky="ew", pady=3)
        self.stop_btn = ctk.CTkButton(c, text="■  Sustur", height=38, font=theme.font(14, "bold"),
                                      fg_color=theme.DANGER, hover_color=theme.DANGER_HOVER,
                                      command=self.app.player.stop)
        self.stop_btn.grid(row=4, column=0, sticky="ew", pady=(10, 3))

        # Anahtarlar
        sw = ctk.CTkFrame(left, fg_color=theme.CARD_BG, corner_radius=16)
        sw.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        self.auto_var = ctk.BooleanVar()
        self.skip_var = ctk.BooleanVar()
        ctk.CTkSwitch(sw, text="Ziller otomatik çalsın", variable=self.auto_var, font=theme.font(14, "bold"),
                      command=self._toggle_auto).pack(side="left", padx=18, pady=14)
        ctk.CTkSwitch(sw, text="Yalnızca bugün zilleri kapat", variable=self.skip_var,
                      command=self._toggle_skip).pack(side="left", padx=18, pady=14)

    def _build_right(self):
        card = Card(self, "Bugünkü Zil Çizelgesi")
        card.grid(row=1, column=1, sticky="nsew", padx=(9, 18), pady=16)
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
        self.statusbar.grid(row=2, column=0, columnspan=2, sticky="ew", padx=20, pady=(0, 8))

    # -- güncelleme ---------------------------------------------------------

    def refresh_all(self):
        cfg = self.app.cfg
        ctk.set_appearance_mode({"light": "light", "dark": "dark"}.get(cfg["theme"], "system"))
        self.title(f"{APP_NAME} – {cfg['school_name']}")
        self.school_lbl.configure(text=cfg["school_name"])
        level = cfg.get("level") or "basit"
        self.level_btn.configure(text=f"Düzey: {LEVEL_NAMES[level]}")
        self._row_toggles = config.LEVELS.index(level) >= config.LEVELS.index("gelismis")
        if level in ("kolay", "basit") or not cfg["tts"].get("enabled"):
            self.announce_btn.grid_remove()
        else:
            self.announce_btn.grid()
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
            lbl = ctk.CTkLabel(self.list_frame, text="Bugün çalacak zil yok.", text_color=theme.MUTED,
                               font=theme.font(15))
            lbl.grid(row=0, column=0, columnspan=3, pady=40)
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
            if self._row_toggles and e.off != "Kapalı":
                # Yalnızca bugün için bu zili kapat / aç
                ctk.CTkButton(row, text="Aç" if e.off else "Kapat", width=58, height=26,
                              font=theme.font(11), fg_color="transparent", border_width=1,
                              text_color=theme.TEXT, hover_color=theme.ROW_NEXT,
                              command=lambda e=e: self._toggle_bell_today(e)).grid(row=0, column=3, padx=(4, 8))
            row._parts = (t, chip, note, i)
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
            t, chip, note, i = row._parts
            e = row._event
            done = sched.was_fired(e)
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
            chip.configure(fg_color=("#b9c0c9", "#4a515a") if grey else theme.BELL_COLORS[e.kind])

    def _tick(self, reschedule=True):
        now = dt.datetime.now()
        if reschedule:
            # Önce bir sonraki güncellemeyi planla: bir hata olsa bile saat durmasın.
            self.after(1000 - now.microsecond // 1000 + 5, self._tick)
        try:
            self._update(now)
        except Exception:  # noqa: BLE001
            log.exception("Ana ekran güncellenemedi")

    def _update(self, now):
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
                lessons = schedule.lessons_for_weekday(schedule.config_for_date(cfg, now.date()), now.weekday())
                active = sum(1 for e in events if not e.off)
                text = f"{len(lessons)} ders · {active} zil"
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
            self.next_chip.configure(text="Bugün başka zil yok", fg_color=("#9aa3ae", "#4a515a"))
            self.next_time.configure(text="—")
            self.next_note.configure(text="")
            self.next_left.configure(text="")
        else:
            self.next_chip.configure(text=nxt.label, fg_color=theme.BELL_COLORS[nxt.kind])
            self.next_time.configure(text=nxt.time_str)
            self.next_note.configure(text=nxt.note)
            secs = max(0, nxt.minute * 60 - (now.hour * 3600 + now.minute * 60 + now.second))
            h, rem = divmod(secs, 3600)
            m, s = divmod(rem, 60)
            self.next_left.configure(text=(f"{h} sa {m:02d} dk kaldı" if h else f"{m:02d}:{s:02d} kaldı"))

        self._update_statusbar(cfg, now)

    def _update_statusbar(self, cfg, now):
        if self.app.player.playing:
            text = f"🔊  Çalıyor: {self.app.now_playing}"
        elif not self.app.player.available:
            text = "⚠  Ses sistemi başlatılamadı. Hoparlör/ses kartını kontrol edip programı yeniden açın."
        elif not cfg.get("auto_ring", True):
            text = "⚠  Otomatik zil KAPALI. Ziller çalmayacak."
        elif cfg.get("skip_date") == now.date().isoformat():
            text = "⚠  Ziller yalnızca bugün için kapalı. Yarın otomatik olarak açılır."
        else:
            text = f"✓  Program çalışıyor. Ziller otomatik çalacak.   ·   {APP_NAME} {__version__}"
        if self.statusbar.cget("text") != text:
            self.statusbar.configure(text=text)

    # -- olaylar ------------------------------------------------------------

    def _toggle_auto(self):
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
        self.app.update_config(skip_date=dt.date.today().isoformat() if self.skip_var.get() else None)

    def open_level_dialog(self):
        LevelDialog(self, self.app.cfg.get("level"), on_select=lambda lv: self.app.update_config(level=lv))

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

    def _on_close(self):
        if self.app.cfg.get("confirm_exit", True) and not messagebox.askyesno(
                "Programı kapat",
                "Program kapatılırsa ziller ÇALMAZ.\n\nYine de kapatmak istiyor musunuz?",
                icon="warning", parent=self):
            return
        log.info("Program kapatıldı")
        self.app.player.stop()
        self.destroy()
