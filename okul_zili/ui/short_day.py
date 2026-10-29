"""«Bugün kısaltılmış ders» penceresi: yalnızca bugün için ders süreleri kısaltılır."""

import datetime as dt

import customtkinter as ctk

from .. import schedule
from ..schedule import fmt_hm
from . import theme
from .widgets import Spin, center_over


class ShortDayDialog(ctk.CTkToplevel):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.title("Bugün kısaltılmış ders")
        self.resizable(False, False)
        self.configure(fg_color=theme.CARD_BG)
        self.transient(master)
        cfg = app.cfg
        today = dt.date.today()
        self.weekday = today.weekday()
        # Kısaltma her zaman normal ders saatlerinden hesaplanır (bugün zaten kısaltılmışsa bile).
        self.base = dict(cfg, short_day={"date": None})
        lessons = schedule.lessons_for_weekday(schedule.config_for_date(self.base, today), self.weekday)
        gaps = [lessons[i + 1][0] - lessons[i][1] for i in range(len(lessons) - 1)]
        normal_break = min(gaps) if gaps else cfg["timing"].get("break_minutes", 10)
        normal_lunch = max(gaps) if gaps and max(gaps) >= 30 else 0
        current = cfg.get("short_day") or {}
        active = current.get("date") == today.isoformat()

        ctk.CTkLabel(self, text="⏱  Bugün kısaltılmış ders", font=theme.font(19, "bold")).pack(
            anchor="w", padx=22, pady=(18, 2))
        ctk.CTkLabel(self, text="Yalnızca bugün geçerlidir; yarın ders saatleri kendiliğinden normale döner. İlk ders "
                                "aynı saatte başlar, ders sayısı değişmez.", wraplength=460, justify="left",
                     text_color=theme.MUTED).pack(anchor="w", padx=22)
        form = ctk.CTkFrame(self, fg_color="transparent")
        form.pack(anchor="w", padx=22, pady=(12, 4))
        self.lesson = Spin(form, current.get("lesson_minutes", 30) if active else 30, 10, 90, suffix="dakika")
        self.brk = Spin(form, current.get("break_minutes", normal_break) if active else normal_break, 0, 60,
                        suffix="dakika")
        lunch_value = current.get("lunch_minutes") if active and current.get("lunch_minutes") is not None \
            else normal_lunch
        self.lunch = Spin(form, lunch_value, 0, 120, suffix="dakika")
        rows = [("Ders süresi", self.lesson), ("Teneffüs süresi", self.brk)]
        if normal_lunch:
            rows.append(("Öğle arası süresi", self.lunch))
        for r, (label, w) in enumerate(rows):
            ctk.CTkLabel(form, text=label, width=140, anchor="w").grid(row=r, column=0, sticky="w", pady=4)
            w.grid(row=r, column=1, sticky="w", pady=4)
            for child in w.winfo_children():
                if isinstance(child, ctk.CTkButton):
                    child.configure(command=self._wrap(child.cget("command")))
                if isinstance(child, ctk.CTkEntry):
                    child.bind("<KeyRelease>", lambda e: self._update_preview())
        self.has_lunch = bool(normal_lunch)
        self.preview = ctk.CTkLabel(self, text="", justify="left", anchor="w", font=theme.font(13))
        self.preview.pack(anchor="w", padx=22, pady=(8, 4))
        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(fill="x", padx=22, pady=(10, 18))
        ctk.CTkButton(btns, text="Bugün uygula", width=140, fg_color=theme.SUCCESS, hover_color=theme.SUCCESS_HOVER,
                      font=theme.font(14, "bold"), command=self._apply).pack(side="right")
        ctk.CTkButton(btns, text="Vazgeç", width=100, fg_color="transparent", border_width=1, text_color=theme.TEXT,
                      command=self.destroy).pack(side="right", padx=8)
        if active:
            ctk.CTkButton(btns, text="Normale dön", width=120, fg_color="transparent", border_width=1,
                          border_color=theme.DANGER, text_color=theme.DANGER, command=self._clear).pack(side="left")
        self._update_preview()
        self.after(50, lambda: (center_over(self), self.lift(), self.grab_set()))

    def _wrap(self, fn):
        def run():
            fn()
            self._update_preview()
        return run

    def _values(self):
        lunch = self.lunch.get() if self.has_lunch else None
        return {"date": dt.date.today().isoformat(), "lesson_minutes": self.lesson.get(),
                "break_minutes": self.brk.get(), "lunch_minutes": lunch}

    def _update_preview(self):
        try:
            short = self._values()
        except ValueError:
            self.preview.configure(text="Süreleri kontrol edin.", text_color=theme.DANGER)
            return
        cfg = schedule.shortened_config(self.base, self.weekday, short)
        lines = []
        for _, name, lessons, _ in schedule.shifts_for_weekday(cfg, self.weekday):
            if not lessons:
                continue
            head = f"{name}: " if name else ""
            times = ", ".join(f"{fmt_hm(a)}" for a, _ in lessons[:4]) + (" …" if len(lessons) > 4 else "")
            lines.append(f"{head}Dersler {times} · son ders {fmt_hm(lessons[-1][1])}'da biter")
        self.preview.configure(text="\n".join(lines) or "Bugün ders yok.", text_color=theme.TEXT)

    def _apply(self):
        try:
            short = self._values()
        except ValueError:
            return
        self.app.update_config(short_day=short)
        if self.app.window is not None:
            self.app.window.flash(f"✓  Bugün kısaltılmış ders ({short['lesson_minutes']} dk)")
        self.destroy()

    def _clear(self):
        self.app.update_config(short_day=dict(self.app.cfg.get("short_day") or {}, date=None))
        if self.app.window is not None:
            self.app.window.flash("✓  Ders saatleri normale döndü")
        self.destroy()
