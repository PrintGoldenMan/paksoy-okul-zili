"""İlk açılış kurulum sihirbazı: okulun adı, türü, tekli/ikili öğretim, ders saatleri ve son ayarlar."""

import datetime as dt

import customtkinter as ctk
from tkinter import messagebox

from .. import autostart, meb_takvim, schedule, templates
from ..schedule import fmt_hm, parse_hm
from . import theme
from .widgets import Spin, fit_to_screen, labeled_row, time_entry

STEPS = ["Okul", "Ders saatleri", "Son adım"]
SHIFTS = {"tekli": "Tekli öğretim (tek grup)", "ikili": "İkili öğretim (sabahçı / öğlenci)"}


class SetupWizard(ctk.CTkToplevel):
    def __init__(self, master, app, on_done=None):
        super().__init__(master)
        self.app = app
        self.on_done = on_done
        self.title("Okul Zili – Kurulum")
        fit_to_screen(self, 760, 640)
        self.minsize(640, 520)
        self.configure(fg_color=theme.WINDOW_BG)
        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", self._close)
        cfg = app.cfg
        self.data = {"school_name": cfg.get("school_name", ""), "school_type": cfg.get("school_type", "lise"),
                     "shift": "ikili" if cfg["second_shift"].get("enabled") else "tekli"}
        self.step = 0

        head = ctk.CTkFrame(self, fg_color=theme.HEADER_BG, corner_radius=0)
        head.pack(fill="x")
        ctk.CTkLabel(head, text="🔔  Okul Zili'ne hoş geldiniz", font=theme.font(20, "bold"),
                     text_color="white").pack(anchor="w", padx=22, pady=(14, 0))
        self.step_lbl = ctk.CTkLabel(head, text="", text_color="#b9c7da")
        self.step_lbl.pack(anchor="w", padx=22, pady=(0, 12))

        self.body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=12, pady=8)
        self.body.grid_columnconfigure(0, weight=1)

        nav = ctk.CTkFrame(self, fg_color="transparent")
        nav.pack(fill="x", padx=20, pady=(0, 14))
        self.back_btn = ctk.CTkButton(nav, text="◀  Geri", width=110, fg_color="transparent", border_width=1,
                                      text_color=theme.TEXT, command=self._back)
        self.back_btn.pack(side="left")
        self.next_btn = ctk.CTkButton(nav, text="İleri  ▶", width=150, height=38, font=theme.font(15, "bold"),
                                      command=self._next)
        self.next_btn.pack(side="right")
        self._show()
        self.after(100, lambda: (self.lift(), self.focus_force()))

    # -- sayfalar -------------------------------------------------------------------------

    def _clear(self):
        for w in self.body.winfo_children():
            w.destroy()
        self._collect = lambda: None

    def _show(self):
        self._clear()
        self.step_lbl.configure(text=f"Adım {self.step + 1} / {len(STEPS)}: {STEPS[self.step]}")
        self.back_btn.configure(state="normal" if self.step else "disabled")
        self.next_btn.configure(text="Kurulumu bitir  ✓" if self.step == len(STEPS) - 1 else "İleri  ▶",
                                fg_color=theme.SUCCESS if self.step == len(STEPS) - 1 else theme.ACCENT)
        [self._page_school, self._page_times, self._page_finish][self.step]()

    def _card(self, title, subtitle=None):
        from .widgets import Card
        c = Card(self.body, title, subtitle)
        c.grid(row=len(self.body.grid_slaves()), column=0, sticky="ew", padx=4, pady=6)
        return c.body

    def _page_school(self):
        b = self._card("Okulunuzun adı", "Ana ekranın üstünde görünür.")
        name = ctk.CTkEntry(b, width=460, height=36, font=theme.font(15),
                            placeholder_text="ör. Atatürk Ortaokulu")
        if self.data["school_name"]:
            name.insert(0, self.data["school_name"])
        name.grid(row=0, column=0, sticky="w")
        b = self._card("Okul türü", "Ders saatleri bu türe göre önceden doldurulur; sonraki adımda değiştirebilirsiniz.")
        kind = ctk.CTkSegmentedButton(b, values=list(templates.SCHOOL_TYPES.values()), font=theme.font(14, "bold"),
                                      height=36)
        kind.set(templates.SCHOOL_TYPES[self.data["school_type"]])
        kind.grid(row=0, column=0, sticky="w")
        b = self._card("Öğretim şekli")
        shift = ctk.CTkSegmentedButton(b, values=list(SHIFTS.values()), font=theme.font(14, "bold"), height=36)
        shift.set(SHIFTS[self.data["shift"]])
        shift.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(b, text="İkili öğretimde sabah ve öğleden sonra iki ayrı grup okur; iki grubun zilleri aynı gün "
                             "art arda çalar.", text_color=theme.MUTED, font=theme.font(12), wraplength=600,
                     justify="left").grid(row=1, column=0, sticky="w", pady=(6, 0))
        b = self._card("Başka bir okuldan ders saatleri dosyası mı aldınız?",
                       "«.okulzili-saatler» dosyasını yüklerseniz ders saatleri adımı atlanır.")
        imported = ctk.CTkLabel(b, text="", text_color=theme.SUCCESS, anchor="w")

        def load_file():
            from tkinter import filedialog
            import json
            path = filedialog.askopenfilename(parent=self, title="Ders saatleri dosyası",
                                              filetypes=[("Okul Zili ders saatleri", "*.okulzili-saatler *.json")])
            if not path:
                return
            try:
                with open(path, encoding="utf-8-sig") as fh:
                    data = json.load(fh)
                if not isinstance(data, dict) or "okul_zili_ders_saatleri" not in data:
                    raise ValueError("Bu dosya bir Okul Zili ders saatleri dosyası değil.")
            except Exception as exc:  # noqa: BLE001
                messagebox.showerror("Yüklenemedi", f"Dosya okunamadı:\n{exc}", parent=self)
                return
            self.data["imported"] = data
            imported.configure(text=f"✓ «{data.get('school_name') or 'dosyadaki okul'}» ders saatleri yüklendi")
        ctk.CTkButton(b, text="Ders saatleri dosyası yükle…", width=220, fg_color="transparent", border_width=1,
                      text_color=theme.TEXT, command=load_file).grid(row=0, column=0, sticky="w")
        imported.grid(row=1, column=0, sticky="w", pady=(6, 0))
        if self.data.get("imported"):
            imported.configure(text="✓ Ders saatleri dosyası yüklendi")
        self.after(50, name.focus_set)

        def collect():
            if not name.get().strip():
                raise ValueError("Lütfen okulunuzun adını yazın.")
            new_type = next(k for k, v in templates.SCHOOL_TYPES.items() if v == kind.get())
            new_shift = next(k for k, v in SHIFTS.items() if v == shift.get())
            if (new_type, new_shift) != (self.data["school_type"], self.data["shift"]) or "timing" not in self.data:
                self.data["timing"], self.data["timing2"] = templates.timing_for(new_type, new_shift == "ikili")
            self.data.update(school_name=name.get().strip(), school_type=new_type, shift=new_shift)
        self._collect = collect

    def _timing_form(self, parent, timing, title):
        b = parent
        ctk.CTkLabel(b, text=title, font=theme.font(14, "bold")).grid(row=0, column=0, columnspan=3, sticky="w",
                                                                       pady=(0, 6))
        first = time_entry(b, timing["first_lesson"])
        count = Spin(b, timing["lesson_count"], 1, 12, suffix="ders")
        length = Spin(b, timing["lesson_minutes"], 10, 90, suffix="dakika")
        brk = Spin(b, timing["break_minutes"], 0, 60, suffix="dakika")
        lunch_after = Spin(b, timing["lunch_after"], 0, 12, suffix="dersten sonra")
        lunch = Spin(b, timing["lunch_minutes"], 0, 120, suffix="dakika")
        rows = [("İlk ders başlangıcı", first, None), ("Ders sayısı", count, None), ("Ders süresi", length, None),
                ("Teneffüs süresi", brk, None), ("Öğle arası kaçıncı", lunch_after, "0 = yok"),
                ("Öğle arası süresi", lunch, None)]
        for r, (label, w, hint) in enumerate(rows, start=1):
            labeled_row(b, r, label, w, hint)

        def read():
            try:
                return {"first_lesson": fmt_hm(parse_hm(first.get())), "lesson_count": count.get(),
                        "lesson_minutes": length.get(), "break_minutes": brk.get(),
                        "lunch_after": lunch_after.get(), "lunch_minutes": lunch.get()}
            except ValueError as exc:
                raise ValueError(f"{title}: {exc or 'saati SS:DD biçiminde yazın (ör. 08:30)'}")
        return read

    def _page_times(self):
        double = self.data["shift"] == "ikili"
        b = self._card("Ders saatleri", f"{templates.SCHOOL_TYPES[self.data['school_type']]} için örnek değerler "
                                        "dolduruldu. Okulunuzun saatlerine göre düzeltin.")
        read1 = self._timing_form(b, self.data["timing"], "Sabahçılar" if double else "Ders ve teneffüs süreleri")
        read2 = None
        if double:
            b2 = self._card("Öğlencilerin ders saatleri")
            read2 = self._timing_form(b2, self.data["timing2"], "Öğlenciler")
        preview = ctk.CTkLabel(self._card("Özet"), text="", justify="left", anchor="w")
        preview.grid(row=0, column=0, sticky="w")

        def update_preview():
            try:
                t1 = read1()
                t2 = read2() if read2 else None
            except ValueError as exc:
                preview.configure(text=str(exc), text_color=theme.DANGER)
                return
            lines = []
            for name, t in (("Sabahçı" if double else "", t1), ("Öğlenci", t2)):
                if not t:
                    continue
                lessons = schedule.auto_lessons(t)
                head = f"{name}: " if name else ""
                lines.append(f"{head}{len(lessons)} ders, {fmt_hm(lessons[0][0])}'da başlar, "
                             f"{fmt_hm(lessons[-1][1])}'da biter")
            preview.configure(text="\n".join(lines), text_color=theme.TEXT)
        ctk.CTkButton(preview.master, text="Özeti güncelle", width=130, fg_color="transparent", border_width=1,
                      text_color=theme.TEXT, command=update_preview).grid(row=0, column=1, padx=10, sticky="e")
        update_preview()

        def collect():
            t1 = read1()
            t2 = read2() if read2 else None
            if t2:
                end1 = schedule.auto_lessons(t1)[-1][1]
                if schedule.auto_lessons(t2)[0][0] < end1:
                    raise ValueError(f"Öğlencilerin ilk dersi, sabahçıların son dersi bitmeden ({fmt_hm(end1)}) "
                                     "başlıyor. Öğlenci ilk ders saatini sonraya alın.")
            self.data["timing"], self.data["timing2"] = t1, t2 or self.data.get("timing2")
        self._collect = collect

    def _page_finish(self):
        today = dt.date.today()
        cal = meb_takvim.calendar_for(today)
        b = self._card("Son adım", "Bu ayarları daha sonra Ayarlar'dan değiştirebilirsiniz.")
        self.meb_var = ctk.BooleanVar(value=cal is not None)
        meb = ctk.CTkCheckBox(b, text=f"MEB çalışma takvimini ekle ({meb_takvim.school_year(today)}: ara tatiller, "
                                      "yarıyıl, bayramlar, yaz tatili) – her yıl kendiliğinden güncellenir",
                              variable=self.meb_var)
        meb.grid(row=0, column=0, sticky="w", pady=4)
        if cal is None:
            meb.configure(state="disabled")
        self.autostart_var = ctk.BooleanVar(value=autostart.supported())
        auto = ctk.CTkCheckBox(b, text="Bilgisayar açılınca Okul Zili otomatik başlasın (önerilir)",
                               variable=self.autostart_var)
        auto.grid(row=1, column=0, sticky="w", pady=4)
        if not autostart.supported():
            auto.configure(state="disabled")
        self._card("Zil sesleri", "Program kendi zil sesiyle gelmez. Kurulumdan sonra ana ekrandaki "
                                      "«🎵 Kütüphane» düğmesiyle YouTube'dan ya da bilgisayardan zil sesi ekleyin. "
                                      "Ses seçilene kadar ziller Windows uyarı sesiyle çalar.")
        self._card("Ayar düzeyi", "Kurulumdan sonra ayarların ne kadar ayrıntılı görüneceğini seçeceksiniz.")

    # -- gezinme --------------------------------------------------------------------------

    def _next(self):
        try:
            self._collect()
        except ValueError as exc:
            messagebox.showerror("Eksik bilgi", str(exc), parent=self)
            return
        if self.step < len(STEPS) - 1:
            self.step += 1
            if self.step == 1 and self.data.get("imported"):
                self.step = 2   # ders saatleri dosyadan geldi
            self._show()
            return
        self._finish()

    def _back(self):
        try:
            self._collect()
        except ValueError:
            pass
        if self.step:
            self.step -= 1
            if self.step == 1 and self.data.get("imported"):
                self.step = 0
            self._show()

    def _finish(self):
        cfg = self.app.cfg
        cfg.update(school_name=self.data["school_name"], school_type=self.data["school_type"],
                   schedule_mode="auto", day_overrides={}, setup_done=True)
        if self.data.get("imported"):
            from .. import config
            from .settings_window import SettingsWindow
            data = self.data["imported"]
            merged = config._sanitize(config._merge(cfg, {k: data[k] for k in SettingsWindow.TIMETABLE_KEYS
                                                          if k in data}))
            cfg.update({k: merged[k] for k in SettingsWindow.TIMETABLE_KEYS})
            cfg["school_name"] = self.data["school_name"]
        else:
            cfg["timing"].update(self.data["timing"])
            second = cfg["second_shift"]
            second["enabled"] = self.data["shift"] == "ikili"
            if second["enabled"]:
                second.update(schedule_mode="auto")
                second["timing"].update(self.data["timing2"])
        if self.meb_var.get():
            cfg["meb_auto"] = True
            meb_takvim.apply_calendar(cfg, meb_takvim.school_year(dt.date.today()))
        cfg["autostart"] = bool(self.autostart_var.get())
        self.app.apply_config(cfg)
        self.destroy()
        if self.on_done:
            self.on_done()

    def _close(self):
        if messagebox.askyesno("Kurulum", "Kurulum yarıda bırakılsın mı?\n\nŞimdilik örnek ders saatleriyle "
                                          "çalışılır; program bir sonraki açılışta kurulumu yeniden sorar.",
                               parent=self):
            self.destroy()
            if self.on_done:
                self.on_done()
