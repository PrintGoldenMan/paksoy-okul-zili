"""Ayarlar penceresi.

Görünen sekmeler ve seçenekler seçilen ayar düzeyine göre değişir:
  Basit    : Genel, Ders Saatleri (süreler), Zil Sesleri (kütüphaneden)
  Gelişmiş : + ders saatlerini tek tek girme, kendi ses dosyaları, okul günleri,
             tatiller, Türkçe sesli anonslar
  Uzman    : + güne özel ders saatleri, ek ziller, zil tekrarı/ses düzeyi,
             anons motoru ve hızı, yedekleme, kayıtlar
Düzey yalnızca neyin görüneceğini belirler; yapılmış ayarlar düzey değişse de geçerlidir.
"""

import copy
import datetime as dt
import json
import os
import subprocess
import sys

import customtkinter as ctk
from tkinter import filedialog, messagebox

from .. import autostart, config, library, paths, rotation, schedule, sounds, tts
from ..config import (BELL_NAMES, BELL_TYPES, DEFAULT_RING_SECONDS, LEVEL_DESCRIPTIONS, LEVEL_NAMES, LEVELS,
                      MAX_RING_SECONDS, MIN_RING_SECONDS, ring_seconds)
from ..schedule import fmt_hm, parse_hm
from ..turkish import DAYS, capitalize_first, ordinal_word
from . import theme
from .widgets import Card, Spin, fit_to_screen, labeled_row, time_entry

LEVEL_RANK = {lv: i for i, lv in enumerate(LEVELS)}
SHORT_DAYS = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]
THEMES = {"system": "Sistem ile aynı", "light": "Açık", "dark": "Koyu"}
OPEN_LIBRARY = "🎵 Kütüphaneyi aç / yeni ses ekle…"


class SoundPicker(ctk.CTkFrame):
    """Kütüphaneden zil sesi seçimi ve dinleme düğmesi."""

    def __init__(self, master, player, sound_id, open_library=None, duration_spin=None):
        super().__init__(master, fg_color="transparent")
        self.player = player
        self.duration_spin = duration_spin
        self.open_library = open_library
        self.sound_id = sound_id or ""
        self.menu = ctk.CTkOptionMenu(self, width=280, command=self._on_select, dynamic_resizing=False)
        self.menu.pack(side="left")
        ctk.CTkButton(self, text="▶ Dinle", width=80, command=self._preview).pack(side="left", padx=(8, 0))
        self.length_lbl = ctk.CTkLabel(self, text="", text_color=theme.MUTED, font=theme.font(12))
        self.length_lbl.pack(side="left", padx=(8, 0))
        self.refresh()

    def _choices(self):
        """[(kimlik, menüde görünen ad)] – aynı adlı sesler numaralandırılır."""
        opts, seen = [], {}
        for item in library.get_library().items():
            name = item["title"]
            seen[name] = seen.get(name, 0) + 1
            if seen[name] > 1:
                name = f"{name} ({seen[name]})"
            opts.append((library.PREFIX + item["id"], name))
        opts.append((sounds.NO_SOUND, sounds.NO_SOUND_NAME))
        if sounds.is_missing(self.sound_id):
            opts.insert(0, (self.sound_id, sounds.display_name(self.sound_id)))
        return opts

    def refresh(self):
        opts = self._choices()
        values = [name for _, name in opts] + ([OPEN_LIBRARY] if self.open_library else [])
        self.menu.configure(values=values)
        self.menu.set(next((n for sid, n in opts if sid == self.sound_id), sounds.display_name(self.sound_id)))
        missing = sounds.is_missing(self.sound_id)
        self.menu.configure(fg_color=theme.WARNING if missing else theme.ACCENT,
                            text_color=theme.WARNING_TEXT if missing else "white")
        self._show_length()

    def _show_length(self):
        n = sounds.length_seconds(self.sound_id)
        text = f"(ses {n:.1f} sn)".replace(".", ",") if n else ""
        self.length_lbl.configure(text=text)

    def _on_select(self, name):
        if name == OPEN_LIBRARY:
            self.refresh()
            self.open_library()
            return
        for sid, n in self._choices():
            if n == name:
                self.sound_id = sid
                self.refresh()
                return

    def preview_duration(self):
        if self.duration_spin is not None:
            try:
                return self.duration_spin.get()
            except ValueError:
                return None
        return None

    def _preview(self):
        self.player.preview_sound(self.sound_id, self.preview_duration())

    def set_locked(self, locked):
        """Değişen ses açıkken tek ses seçimi kullanılmaz; kutu kilitlenir."""
        self.menu.configure(state="disabled" if locked else "normal")
        if locked:
            self.length_lbl.configure(text="(değişen ses açık – aşağıdaki seçim kullanılır)")
        else:
            self._show_length()

    def get(self):
        return self.sound_id


class RotationPanel(ctk.CTkFrame):
    """Değişen zil sesi: kütüphaneden seçilen seslerden her gün/hafta/ay rastgele biri çalar."""

    def __init__(self, master, player, bell, picker, open_library):
        super().__init__(master, fg_color="transparent")
        self.player = player
        self.picker = picker
        self.open_library = open_library
        self.rot = copy.deepcopy(bell.get("rotation") or rotation.DEFAULT)
        self._orig_period = self.rot.get("period", "week")
        self.enabled = ctk.BooleanVar(value=bool(self.rot.get("enabled")))
        ctk.CTkSwitch(self, text="🔀  Ses düzenli olarak değişsin (seçtiğiniz seslerden rastgele)",
                      variable=self.enabled, command=self._toggle, font=theme.font(13, "bold")).pack(anchor="w")
        self.body = ctk.CTkFrame(self, fg_color=theme.ROW_ALT, corner_radius=10)
        top = ctk.CTkFrame(self.body, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(10, 4))
        ctk.CTkLabel(top, text="Ne sıklıkla değişsin:").pack(side="left")
        self.period = ctk.CTkSegmentedButton(top, values=list(rotation.PERIODS.values()), command=self._period_changed)
        self.period.set(rotation.PERIODS.get(self.rot.get("period"), "Her hafta"))
        self.period.pack(side="left", padx=8)
        ctk.CTkLabel(self.body, text="Hangi sesler arasından seçilsin? (en az 1; her yeni dönemde bir öncekinden "
                                     "farklı biri seçilir)", text_color=theme.MUTED, font=theme.font(12)).pack(
            anchor="w", padx=12)
        self.list = ctk.CTkFrame(self.body, fg_color="transparent")
        self.list.pack(fill="x", padx=12, pady=4)
        cur = ctk.CTkFrame(self.body, fg_color="transparent")
        cur.pack(fill="x", padx=12, pady=(4, 10))
        self.current_lbl = ctk.CTkLabel(cur, text="", anchor="w")
        self.current_lbl.pack(side="left")
        ctk.CTkButton(cur, text="Şimdi değiştir", width=110, fg_color="transparent", border_width=1,
                      text_color=theme.TEXT, command=self._change_now).pack(side="right")
        ctk.CTkButton(cur, text="▶ Dinle", width=80, command=self._preview).pack(side="right", padx=8)
        self.vars = {}
        self.refresh()
        self._toggle()

    def refresh(self):
        """Kütüphane değişince ses listesini yeniden çizer (işaretler korunur)."""
        checked = set(self.selected()) if self.vars else set(self.rot.get("pool") or [])
        for w in self.list.winfo_children():
            w.destroy()
        self.vars = {}
        items = library.get_library().items()
        if not items:
            ctk.CTkLabel(self.list, text="Kütüphane boş.", text_color=theme.MUTED).pack(side="left")
            ctk.CTkButton(self.list, text="🎵 Kütüphaneyi aç", width=140, command=self.open_library).pack(
                side="left", padx=8)
        for i, item in enumerate(items):
            sid = library.PREFIX + item["id"]
            var = ctk.BooleanVar(value=sid in checked)
            ctk.CTkCheckBox(self.list, text=item["title"], variable=var, command=self._update_current,
                            width=330).grid(row=i // 2, column=i % 2, sticky="w", pady=2, padx=(0, 10))
            self.vars[sid] = var
        self._update_current()
        if hasattr(self, "enabled"):
            self.picker.set_locked(self.enabled.get())

    def selected(self):
        return [sid for sid, v in self.vars.items() if v.get()]

    def _period_key_now(self):
        period = next(k for k, v in rotation.PERIODS.items() if v == self.period.get())
        return period, rotation.period_key(period, dt.date.today())

    def _period_changed(self, _value):
        self._update_current()

    def _toggle(self):
        on = self.enabled.get()
        if on:
            self.body.pack(fill="x", pady=(6, 0))
        else:
            self.body.pack_forget()
        self.picker.set_locked(on)
        self._update_current()

    def _current(self):
        pool = self.selected()
        cur = self.rot.get("current", "")
        return cur if cur in pool else (pool[0] if pool else "")

    def _update_current(self):
        period, _ = self._period_key_now()
        pool = self.selected()
        if not pool:
            self.current_lbl.configure(text="⚠ En az bir ses seçin.", text_color=theme.DANGER)
            return
        text = f"{rotation.PERIOD_THIS[period]} sesi: {sounds.display_name(self._current())}"
        if self.rot.get("current") not in pool:
            text += "   (kaydedince seçilir)"
        self.current_lbl.configure(text=text, text_color=theme.TEXT)

    def _change_now(self):
        pool = self.selected()
        if not pool:
            return
        self.rot["current"] = rotation.pick(pool, exclude=self._current())
        self.rot["key"] = self._period_key_now()[1]
        self._update_current()
        self.current_lbl.configure(text=self.current_lbl.cget("text") + "   (Kaydet'e basınca geçerli olur)")

    def _preview(self):
        sid = self._current()
        if sid:
            self.player.preview_sound(sid, self.picker.preview_duration())

    def get(self, bell_name):
        period, key = self._period_key_now()
        pool = self.selected()
        if self.enabled.get() and not pool:
            raise ValueError(f"{bell_name}: «Ses düzenli olarak değişsin» açık, ancak hiç ses seçilmedi. "
                             "En az bir ses işaretleyin ya da bu özelliği kapatın.")
        rot = dict(self.rot, enabled=bool(self.enabled.get()), period=period, pool=pool)
        if period != self._orig_period and rot.get("current") in pool:
            rot["key"] = key   # sıklık değişince şu anki ses yeni dönemin sesi olarak kalsın
        return rot


class LessonTable(ctk.CTkFrame):
    """Ders başlangıç/bitiş saatlerini tek tek düzenleme tablosu."""

    def __init__(self, master, lessons, fill_source=None):
        super().__init__(master, fg_color="transparent")
        self.fill_source = fill_source
        self.rows = []
        self.table = ctk.CTkFrame(self, fg_color="transparent")
        self.table.pack(fill="x")
        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(fill="x", pady=(8, 0))
        ctk.CTkButton(btns, text="+ Ders ekle", width=110, command=self._add_after_last).pack(side="left")
        if fill_source:
            ctk.CTkButton(btns, text="Otomatik saatlerle doldur", width=190, fg_color="transparent",
                          border_width=1, text_color=theme.TEXT,
                          command=lambda: self.set_lessons(fill_source())).pack(side="left", padx=8)
        self.set_lessons(lessons)

    def set_lessons(self, lessons):
        for r in self.rows:
            r[0].destroy()
        self.rows = []
        for start, end in lessons:
            self._add(start, end)
        self._renumber()

    def _add(self, start="", end=""):
        row = ctk.CTkFrame(self.table, fg_color="transparent")
        row.pack(fill="x", pady=2)
        lbl = ctk.CTkLabel(row, text="", width=70, anchor="w", font=theme.font(13, "bold"))
        lbl.pack(side="left")
        s = time_entry(row, start)
        s.pack(side="left")
        ctk.CTkLabel(row, text="–").pack(side="left", padx=6)
        e = time_entry(row, end)
        e.pack(side="left")
        item = (row, lbl, s, e)
        ctk.CTkButton(row, text="✕", width=30, fg_color="transparent", text_color=theme.DANGER,
                      hover_color=theme.ROW_ALT, command=lambda: self._remove(item)).pack(side="left", padx=8)
        self.rows.append(item)

    def _add_after_last(self):
        if self.rows:
            try:
                last_end = parse_hm(self.rows[-1][3].get())
                self._add(fmt_hm(last_end + 10), fmt_hm(last_end + 50))
            except ValueError:
                self._add()
        else:
            self._add("08:30", "09:10")
        self._renumber()

    def _remove(self, item):
        item[0].destroy()
        self.rows.remove(item)
        self._renumber()

    def _renumber(self):
        for i, (_, lbl, _, _) in enumerate(self.rows, start=1):
            lbl.configure(text=f"{i}. ders")

    def get(self, what="Ders saatleri"):
        out = []
        for i, (_, _, s, e) in enumerate(self.rows, start=1):
            try:
                a, b = parse_hm(s.get()), parse_hm(e.get())
            except ValueError:
                raise ValueError(f"{what}: {i}. dersin saati hatalı. Saatleri SS:DD biçiminde yazın (ör. 08:30).")
            if b <= a:
                raise ValueError(f"{what}: {i}. dersin bitişi başlangıcından sonra olmalı.")
            out.append((a, b))
        out.sort()
        for (a1, b1), (a2, _) in zip(out, out[1:]):
            if a2 < b1:
                raise ValueError(f"{what}: {fmt_hm(a1)} ve {fmt_hm(a2)} dersleri çakışıyor.")
        if not out:
            raise ValueError(f"{what}: en az bir ders olmalı.")
        return [[fmt_hm(a), fmt_hm(b)] for a, b in out]


class SettingsWindow(ctk.CTkToplevel):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.cfg = copy.deepcopy(app.cfg)
        self.level = self.cfg.get("level") or "basit"
        self.title("Okul Zili – Ayarlar")
        fit_to_screen(self, 1040, 800)
        self.minsize(820, 520)
        self.configure(fg_color=theme.WINDOW_BG)
        self.transient(master)
        self._collectors = []
        self.tabs = None

        top = ctk.CTkFrame(self, fg_color=theme.CARD_BG, corner_radius=0)
        top.pack(fill="x")
        ctk.CTkLabel(top, text="Ayarlar", font=theme.font(22, "bold")).pack(side="left", padx=20, pady=14)
        lv = ctk.CTkFrame(top, fg_color="transparent")
        lv.pack(side="right", padx=20)
        ctk.CTkLabel(lv, text="Ayar düzeyi:", font=theme.font(13, "bold")).pack(side="left", padx=(0, 8))
        self.level_seg = ctk.CTkSegmentedButton(
            lv, values=[f"{LEVEL_NAMES[x]}" for x in LEVELS], command=self._on_level,
            font=theme.font(13, "bold"), height=34)
        self.level_seg.pack(side="left")
        self.level_seg.set(LEVEL_NAMES[self.level])
        self.level_desc = ctk.CTkLabel(self, text="", text_color=theme.MUTED, anchor="w", justify="left",
                                       wraplength=900)
        self.level_desc.pack(fill="x", padx=22, pady=(8, 0))

        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", padx=18, pady=12)
        ctk.CTkButton(bottom, text="Kaydet", width=140, height=40, font=theme.font(15, "bold"),
                      fg_color=theme.SUCCESS, hover_color=theme.SUCCESS_HOVER, text_color="white",
                      command=self._save).pack(side="right")
        ctk.CTkButton(bottom, text="Vazgeç", width=110, height=40, fg_color="transparent", border_width=1,
                      text_color=theme.TEXT, command=self._cancel).pack(side="right", padx=10)
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        self._build_tabs()
        self._baseline = self._snapshot()
        self.after(100, self.lift)

    # -- düzen --------------------------------------------------------------

    def _at_least(self, level):
        return LEVEL_RANK[self.level] >= LEVEL_RANK[level]

    def _build_tabs(self, keep=None):
        if self.tabs is not None:
            self.tabs.destroy()
        self._collectors = []
        self._pickers = []
        self.level_desc.configure(text=f"{LEVEL_NAMES[self.level]}: {LEVEL_DESCRIPTIONS[self.level]}")
        self.tabs = ctk.CTkTabview(self, fg_color=theme.WINDOW_BG, segmented_button_selected_color=theme.ACCENT)
        self.tabs.pack(fill="both", expand=True, padx=12)
        self.tabs._segmented_button.configure(font=theme.font(13, "bold"), height=34)
        if self.level == "kolay":
            pages = [("Temel Ayarlar", self._tab_easy)]
        else:
            pages = [("Genel", self._tab_general), ("Ders Saatleri", self._tab_times),
                     ("Zil Sesleri", self._tab_sounds)]
        if self._at_least("gelismis"):
            pages += [("Günler ve Tatiller", self._tab_days), ("Sesli Anons", self._tab_tts)]
        if self._at_least("uzman"):
            pages += [("Güne Özel", self._tab_overrides), ("Ek Ziller", self._tab_extra)]
        if self._at_least("profesyonel"):
            pages += [("Zil Listesi", self._tab_bell_list), ("Programlar", self._tab_profiles)]
        if self._at_least("uzman"):
            pages += [("Sistem", self._tab_system)]
        for name, builder in pages:
            tab = self.tabs.add(name)
            frame = ctk.CTkScrollableFrame(tab, fg_color="transparent")
            frame.pack(fill="both", expand=True)
            frame.grid_columnconfigure(0, weight=1)
            builder(frame)
        if keep and keep in [p[0] for p in pages]:
            self.tabs.set(keep)

    def _open_library(self):
        """Kütüphaneyi açar; kapanınca ses seçim kutuları yeni seslerle güncellenir."""
        from .library_window import LibraryWindow
        win = getattr(self, "_library_win", None)
        if win is not None and win.winfo_exists():
            win.lift()
            return
        self._library_win = LibraryWindow(self, self.app, allow_assign=False, on_close=self._refresh_pickers)

    def _refresh_pickers(self):
        if not self.winfo_exists():
            return
        for picker in getattr(self, "_pickers", []):
            if picker.winfo_exists():
                picker.refresh()

    def _rebuild(self):
        """Mevcut girişleri kaydedip sekmeleri yeniden çizer."""
        if not self._collect():
            return False
        self._build_tabs(keep=self.tabs.get())
        return True

    def _collect(self, show_errors=True):
        try:
            for fn in self._collectors:
                fn()
        except ValueError as exc:
            if show_errors:
                messagebox.showerror("Hatalı ayar", str(exc), parent=self)
            return False
        return True

    def _snapshot(self):
        """Ekrandaki ayarların karşılaştırma için kopyası (kaydedilmemiş değişiklik var mı?)."""
        if not self._collect(show_errors=False):
            return None
        return json.dumps(self.cfg, sort_keys=True, ensure_ascii=False)

    def _on_level(self, name):
        new = next(k for k, v in LEVEL_NAMES.items() if v == name)
        if new == self.level:
            return
        if not self._collect():
            self.level_seg.set(LEVEL_NAMES[self.level])
            return
        self.level = new
        self.cfg["level"] = new
        self._build_tabs(keep=self.tabs.get())

    def _card(self, parent, title, subtitle=None):
        c = Card(parent, title, subtitle)
        c.grid(row=len(parent.grid_slaves()), column=0, sticky="ew", padx=4, pady=6)
        return c.body

    def _hint(self, parent, text, row=None):
        lbl = ctk.CTkLabel(parent, text=text, text_color=theme.MUTED, font=theme.font(12),
                           justify="left", anchor="w", wraplength=760)
        lbl.grid(row=row if row is not None else len(parent.grid_slaves()), column=0, columnspan=4,
                 sticky="w", pady=(4, 0))
        return lbl

    def _morning_card(self, f):
        """İlk dersin sabah zillerini (ör. 08:28 öğrenci, 08:30 öğretmen) açıp kapatma."""
        t = self.cfg["timing"]
        lessons = schedule.lessons_for_weekday(self.cfg, 0) or [(parse_hm(t["first_lesson"]), 0)]
        first = lessons[0][0]
        b = self._card(f, "Sabah Zilleri", "İlk dersten önce çalan zilleri buradan kapatabilirsiniz. "
                                           "Kapalı olan zil hiçbir gün çalmaz.")
        student = ctk.BooleanVar(value=t.get("morning_student_bell", True))
        teacher = ctk.BooleanVar(value=t.get("morning_teacher_bell", True))
        ctk.CTkSwitch(b, text=f"{fmt_hm(first - int(t['student_offset']))}  Öğrenci zili "
                              "(sabah öğrenciler sınıfa girer)",
                      variable=student, font=theme.font(14)).grid(row=0, column=0, columnspan=3, sticky="w", pady=4)
        ctk.CTkSwitch(b, text=f"{fmt_hm(first)}  Öğretmen zili (1. ders başlar)",
                      variable=teacher, font=theme.font(14)).grid(row=1, column=0, columnspan=3, sticky="w", pady=4)

        def collect():
            t["morning_student_bell"] = bool(student.get())
            t["morning_teacher_bell"] = bool(teacher.get())
        self._collectors.append(collect)

    # -- sekmeler -----------------------------------------------------------

    def _tab_easy(self, f):
        cfg = self.cfg
        b = self._card(f, "Ses Düzeyi")
        vol_lbl = ctk.CTkLabel(b, text=f"%{int(cfg['master_volume'])}", width=50)
        vol = ctk.CTkSlider(b, from_=0, to=100, number_of_steps=20, width=360,
                            command=lambda v: vol_lbl.configure(text=f"%{int(v)}"))
        vol.set(cfg["master_volume"])
        labeled_row(b, 0, "Zil ses düzeyi", vol)
        vol_lbl.grid(row=0, column=2, padx=8)
        initial_duration = ring_seconds(cfg["bells"]["ogretmen"].get("duration"))
        dur = duration_spin(b, initial_duration)
        labeled_row(b, 1, "Zil çalma süresi", dur, "Üç zil için de geçerlidir")

        def try_sound():
            try:
                d = dur.get()
            except ValueError:
                d = None
            self.app.player.preview_sound(cfg["bells"]["ogretmen"]["sound"], d)
        ctk.CTkButton(b, text="▶ Sesi dene", width=110, command=try_sound).grid(row=0, column=3, padx=8)

        self._morning_card(f)

        b = self._card(f, "Başlangıç")
        auto_var = ctk.BooleanVar(value=cfg.get("autostart", False))
        cb = ctk.CTkCheckBox(b, text="Bilgisayar açılınca program otomatik başlasın (önerilir)", variable=auto_var)
        cb.grid(row=0, column=0, columnspan=3, sticky="w", pady=4)
        if not autostart.supported():
            cb.configure(state="disabled", text=cb.cget("text") + " – yalnızca Windows'ta")

        self._hint(f, "Ders saatlerini veya zil seslerini değiştirmek için yukarıdan «Basit» düzeyini seçin.")

        def collect():
            cfg["master_volume"] = int(vol.get())
            cfg["autostart"] = bool(auto_var.get())
            try:
                seconds = dur.get()
            except ValueError as exc:
                raise ValueError(f"Zil çalma süresi: {exc}")
            if seconds != initial_duration:  # değiştirilmediyse zillere ayrı ayrı verilmiş süreler korunur
                for kind in BELL_TYPES:
                    cfg["bells"][kind]["duration"] = seconds
        self._collectors.append(collect)

    def _tab_general(self, f):
        cfg = self.cfg
        b = self._card(f, "Okul")
        name = ctk.CTkEntry(b, width=420)
        name.insert(0, cfg["school_name"])
        labeled_row(b, 0, "Okulun adı", name)

        b = self._card(f, "Görünüm")
        theme_menu = ctk.CTkOptionMenu(b, values=list(THEMES.values()), width=200)
        theme_menu.set(THEMES.get(cfg["theme"], THEMES["system"]))
        labeled_row(b, 0, "Tema", theme_menu)

        b = self._card(f, "Başlangıç ve Kapanış")
        auto_var = ctk.BooleanVar(value=cfg.get("autostart", False))
        cb = ctk.CTkCheckBox(b, text="Bilgisayar açılınca program otomatik başlasın (önerilir)", variable=auto_var)
        cb.grid(row=0, column=0, columnspan=3, sticky="w", pady=4)
        if not autostart.supported():
            cb.configure(state="disabled", text=cb.cget("text") + " – yalnızca Windows'ta")
        exit_var = ctk.BooleanVar(value=cfg.get("confirm_exit", True))
        if self._at_least("uzman"):
            ctk.CTkCheckBox(b, text="Program kapatılırken onay iste", variable=exit_var).grid(
                row=1, column=0, columnspan=3, sticky="w", pady=4)

        def collect():
            if not name.get().strip():
                raise ValueError("Okulun adı boş bırakılamaz.")
            cfg["school_name"] = name.get().strip()
            cfg["theme"] = next(k for k, v in THEMES.items() if v == theme_menu.get())
            cfg["autostart"] = bool(auto_var.get())
            cfg["confirm_exit"] = bool(exit_var.get())
        self._collectors.append(collect)

    def _tab_times(self, f):
        cfg, t = self.cfg, self.cfg["timing"]
        manual_active = cfg.get("schedule_mode") == "manual"
        overrides_active = bool(cfg.get("day_overrides"))

        if not self._at_least("gelismis") and (manual_active or overrides_active):
            b = self._card(f, "⚠ Ders saatleri elle ayarlanmış")
            self._hint(b, "Ders saatleri Gelişmiş veya Uzman düzeyde tek tek girilmiş. Aşağıdaki süreler şu anda "
                          "kullanılmıyor. Süreleri kullanmak için aşağıdaki düğmeye basın.", row=0)

            def back_to_auto():
                cfg["schedule_mode"] = "auto"
                cfg["day_overrides"] = {}
                self._rebuild()
            ctk.CTkButton(b, text="Süreleri kullan (otomatik hesaplama)", command=back_to_auto).grid(
                row=1, column=0, sticky="w", pady=(8, 0))

        if self._at_least("gelismis"):
            b = self._card(f, "Ders saatleri nasıl belirlensin?")
            modes = {"auto": "Süreleri gireyim, saatler hesaplansın", "manual": "Her dersin saatini tek tek gireyim"}
            seg = ctk.CTkSegmentedButton(b, values=list(modes.values()))
            seg.set(modes[cfg.get("schedule_mode", "auto")])
            seg.grid(row=0, column=0, sticky="w")

            def on_mode(value):
                old = cfg.get("schedule_mode", "auto")
                cfg["schedule_mode"] = next(k for k, v in modes.items() if v == value)
                if not self._rebuild():
                    cfg["schedule_mode"] = old
                    seg.set(modes[old])
            seg.configure(command=on_mode)

        if cfg.get("schedule_mode") == "manual" and self._at_least("gelismis"):
            b = self._card(f, "Ders Saatleri", "Her dersin başlangıç ve bitiş saatini yazın (ör. 08:30). "
                                               "Teneffüsler aradaki boşluklardan otomatik hesaplanır.")
            table = LessonTable(b, cfg["manual_lessons"],
                                fill_source=lambda: [[fmt_hm(a), fmt_hm(e)] for a, e in schedule.auto_lessons(t)])
            table.grid(row=0, column=0, sticky="w")
            self._collectors.append(lambda: cfg.__setitem__("manual_lessons", table.get()))
            auto_widgets = None
        else:
            b = self._card(f, "Ders ve Teneffüs Süreleri",
                           "İlk dersin saatini ve süreleri girin; tüm ders saatleri otomatik hesaplanır.")
            first = time_entry(b, t["first_lesson"])
            count = Spin(b, t["lesson_count"], 1, 12, suffix="ders")
            length = Spin(b, t["lesson_minutes"], 10, 90, suffix="dakika")
            brk = Spin(b, t["break_minutes"], 0, 60, suffix="dakika")
            lunch_after = Spin(b, t["lunch_after"], 0, 12, suffix="dersten sonra")
            lunch = Spin(b, t["lunch_minutes"], 0, 120, suffix="dakika")
            labeled_row(b, 0, "İlk ders başlangıcı", first)
            labeled_row(b, 1, "Günlük ders sayısı", count)
            labeled_row(b, 2, "Ders süresi", length)
            labeled_row(b, 3, "Teneffüs süresi", brk)
            labeled_row(b, 4, "Öğle arası kaçıncı", lunch_after, "0 = öğle arası yok")
            labeled_row(b, 5, "Öğle arası süresi", lunch)
            auto_widgets = (first, count, length, brk, lunch_after, lunch)

        b = self._card(f, "Öğrenci Zili", "Öğrenci zili, teneffüs bitmeden önce çalar; öğrenciler "
                                          "öğretmenlerden önce sınıfa girer.")
        offset = Spin(b, t["student_offset"], 0, 15, suffix="dakika önce")
        labeled_row(b, 0, "Öğrenci zili, dersten", offset, "0 = öğrenci zili çalmasın")

        self._morning_card(f)

        def lessons_now():
            return schedule.lessons_for_weekday(dict(cfg, day_overrides={}), 0)

        def collect():
            if auto_widgets:
                first, count, length, brk, lunch_after, lunch = auto_widgets
                try:
                    parse_hm(first.get())
                except ValueError:
                    raise ValueError("İlk ders başlangıcı SS:DD biçiminde olmalı (ör. 08:30).")
                try:
                    t.update(first_lesson=fmt_hm(parse_hm(first.get())), lesson_count=count.get(),
                             lesson_minutes=length.get(), break_minutes=brk.get(),
                             lunch_after=lunch_after.get(), lunch_minutes=lunch.get())
                except ValueError as exc:
                    raise ValueError(f"Ders süreleri: {exc}")
            try:
                t["student_offset"] = offset.get()
            except ValueError as exc:
                raise ValueError(f"Öğrenci zili: {exc}")
            shortest = min((b[0] - a[1] for a, b in zip(lessons_now(), lessons_now()[1:])), default=None)
            if t["student_offset"] and shortest is not None and t["student_offset"] >= shortest:
                raise ValueError(f"Öğrenci zili dersten {t['student_offset']} dakika önce çalacak şekilde ayarlı, "
                                 f"ancak en kısa teneffüs {shortest} dakika. Öğrenci zili teneffüsten önce "
                                 f"çalamayacağı için bazı öğrenci zilleri çalmaz. Lütfen "
                                 f"{max(0, shortest - 1)} dakika veya daha az girin.")
        self._collectors.append(collect)

        # Önizleme
        b = self._card(f, "Önizleme", "Ayarlarınıza göre bir okul gününün zil çizelgesi.")
        b.grid_columnconfigure(0, weight=1)
        b.grid_columnconfigure(9, weight=0)
        row = ctk.CTkFrame(b, fg_color="transparent")
        row.grid(row=0, column=0, sticky="w")
        box = ctk.CTkTextbox(b, height=260, font=ctk.CTkFont(family="Consolas", size=13))
        box.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        day_menu = ctk.CTkOptionMenu(row, values=DAYS, width=150)
        day_menu.set(DAYS[0])

        def preview(*_):
            if not self._collect():
                return
            wd = DAYS.index(day_menu.get())
            lessons = schedule.lessons_for_weekday(self.cfg, wd)
            events = schedule.events_for_lessons(self.cfg, lessons) + schedule.extra_events(self.cfg, wd)
            events.sort(key=lambda e: e.minute)
            box.configure(state="normal")
            box.delete("1.0", "end")
            if wd not in self.cfg["active_days"]:
                box.insert("end", f"Not: {DAYS[wd]} okul günü olarak işaretli değil; bu gün zil çalmaz.\n\n")
            for i, (a, e) in enumerate(lessons, start=1):
                box.insert("end", f"{i}. ders   {fmt_hm(a)} – {fmt_hm(e)}\n")
            box.insert("end", "\n")
            for e in events:
                box.insert("end", f"{e.time_str}   {e.label:<14} {e.note}\n")
            box.configure(state="disabled")
        day_menu.configure(command=preview)
        day_menu.pack(side="left")
        ctk.CTkButton(row, text="Önizlemeyi güncelle", command=preview).pack(side="left", padx=8)
        self.after(50, preview)

    def _tab_sounds(self, f):
        cfg = self.cfg
        b = self._card(f, "Genel Ses Düzeyi")
        vol_lbl = ctk.CTkLabel(b, text="", width=50)
        vol = ctk.CTkSlider(b, from_=0, to=100, number_of_steps=20, width=320,
                            command=lambda v: vol_lbl.configure(text=f"%{int(v)}"))
        vol.set(cfg["master_volume"])
        vol_lbl.configure(text=f"%{int(cfg['master_volume'])}")
        labeled_row(b, 0, "Ses düzeyi", vol)
        vol_lbl.grid(row=0, column=2, padx=8)
        ctk.CTkButton(b, text="■ Durdur", width=90, fg_color=theme.DANGER, hover_color=theme.DANGER_HOVER,
                      command=self.app.player.stop_preview).grid(row=0, column=3, padx=8)

        pickers = {}
        for kind in BELL_TYPES:
            bell = cfg["bells"][kind]
            sub = {"ogrenci": "Teneffüs bitmeden önce çalar; öğrenciler sınıfa girer.",
                   "ogretmen": "Ders başladığında çalar; öğretmenler sınıfa girer.",
                   "cikis": "Ders bittiğinde çalar."}[kind]
            b = self._card(f, BELL_NAMES[kind], sub)
            ctk.CTkFrame(b, width=6, height=30, corner_radius=3, fg_color=theme.BELL_COLORS[kind]).grid(
                row=0, column=0, rowspan=3, sticky="ns", padx=(0, 10))
            opt = ctk.CTkFrame(b, fg_color="transparent")
            opt.grid(row=1, column=1, sticky="w", pady=(8, 0))
            ctk.CTkLabel(opt, text="Çalma süresi:").pack(side="left")
            dur = duration_spin(opt, bell.get("duration"))
            dur.pack(side="left", padx=(6, 20))
            picker = SoundPicker(b, self.app.player, bell["sound"], open_library=self._open_library,
                                 duration_spin=dur)
            picker.grid(row=0, column=1, sticky="w")
            self._pickers.append(picker)
            rot = RotationPanel(b, self.app.player, bell, picker, self._open_library)
            rot.grid(row=2, column=1, columnspan=9, sticky="ew", pady=(10, 0))
            self._pickers.append(rot)
            widgets = {"picker": picker, "duration": dur, "rotation": rot}
            if self._at_least("uzman"):
                ctk.CTkLabel(opt, text="Bu zilin ses düzeyi:").pack(side="left")
                v = ctk.CTkSlider(opt, from_=10, to=100, number_of_steps=18, width=180)
                v.set(bell.get("volume", 100))
                v.pack(side="left", padx=6)
                widgets.update(volume=v)
            pickers[kind] = widgets
        self._hint(f, f"Çalma süresi {_sec(MIN_RING_SECONDS)}–{_sec(MAX_RING_SECONDS)} saniye arasında olabilir "
                      f"(varsayılan {_sec(DEFAULT_RING_SECONDS)}). Ses bu süreden kısaysa başa sarılarak tekrarlanır, "
                      "uzunsa süre dolunca yumuşakça kısılarak durur. Anons, zil bittikten sonra okunur.\n"
                      "İpucu: Öğrenci ve öğretmen zillerine farklı sesler seçerseniz kimin sınıfa "
                      "gireceği kolayca anlaşılır.")

        def collect():
            cfg["master_volume"] = int(vol.get())
            for kind, w in pickers.items():
                cfg["bells"][kind]["sound"] = w["picker"].get()
                cfg["bells"][kind]["rotation"] = w["rotation"].get(BELL_NAMES[kind])
                try:
                    cfg["bells"][kind]["duration"] = w["duration"].get()
                except ValueError as exc:
                    raise ValueError(f"{BELL_NAMES[kind]} çalma süresi: {exc}")
                cfg["bells"][kind].pop("repeat", None)
                if "volume" in w:
                    cfg["bells"][kind]["volume"] = int(w["volume"].get())
        self._collectors.append(collect)

    def _tab_days(self, f):
        cfg = self.cfg
        b = self._card(f, "Okul Günleri", "Zillerin çalacağı günleri seçin.")
        day_vars = []
        row = ctk.CTkFrame(b, fg_color="transparent")
        row.grid(row=0, column=0, columnspan=3, sticky="w")
        for i, d in enumerate(DAYS):
            v = ctk.BooleanVar(value=i in cfg["active_days"])
            ctk.CTkCheckBox(row, text=d, variable=v, width=110).pack(side="left", pady=4)
            day_vars.append(v)

        b = self._card(f, "Tatiller", "Bu tarihlerde zil çalmaz. Tek günlük tatil için bitiş tarihini boş "
                                      "bırakabilirsiniz. Tarihleri GG.AA.YYYY biçiminde yazın (ör. 29.10.2026).")
        holder = ctk.CTkFrame(b, fg_color="transparent")
        holder.grid(row=0, column=0, columnspan=3, sticky="ew")
        head = ctk.CTkFrame(holder, fg_color="transparent")
        head.pack(fill="x")
        for text, w in (("Tatilin adı", 260), ("Başlangıç", 120), ("Bitiş", 120)):
            ctk.CTkLabel(head, text=text, width=w, anchor="w", font=theme.font(12, "bold")).pack(side="left", padx=3)
        rows = []

        def to_tr(iso):
            try:
                return dt.date.fromisoformat(iso).strftime("%d.%m.%Y")
            except (TypeError, ValueError):
                return ""

        def add(name="", start="", end=""):
            r = ctk.CTkFrame(holder, fg_color="transparent")
            r.pack(fill="x", pady=2)
            n = ctk.CTkEntry(r, width=260, placeholder_text="ör. Yarıyıl Tatili")
            s = ctk.CTkEntry(r, width=120, placeholder_text="GG.AA.YYYY")
            e = ctk.CTkEntry(r, width=120, placeholder_text="GG.AA.YYYY")
            for w, val in ((n, name), (s, to_tr(start)), (e, to_tr(end) if end != start else "")):
                if val:
                    w.insert(0, val)
                w.pack(side="left", padx=3)
            item = (r, n, s, e)
            ctk.CTkButton(r, text="✕", width=30, fg_color="transparent", text_color=theme.DANGER,
                          hover_color=theme.ROW_ALT, command=lambda: (r.destroy(), rows.remove(item))).pack(
                side="left", padx=6)
            rows.append(item)

        empty = ctk.CTkLabel(holder, text="Henüz tatil eklenmedi.", text_color=theme.MUTED, anchor="w")

        def refresh_empty():
            if rows:
                head.pack(fill="x", before=rows[0][0])
                empty.pack_forget()
            else:
                head.pack_forget()
                empty.pack(fill="x", pady=4)

        _add = add

        def add(*args, **kw):  # noqa: F811 - boş liste yazısını da günceller
            _add(*args, **kw)
            item = rows[-1]
            item[0].winfo_children()[-1].configure(
                command=lambda: (item[0].destroy(), rows.remove(item), refresh_empty()))
            refresh_empty()

        for h in sorted(cfg["holidays"], key=lambda h: h.get("start", "")):
            add(h.get("name", ""), h.get("start", ""), h.get("end", ""))
        refresh_empty()

        def add_official():
            today = dt.date.today()
            y = today.year if today.month >= 8 else today.year - 1
            existing = {s.get() for _, _, s, _ in rows}
            for name, d in (("Cumhuriyet Bayramı", dt.date(y, 10, 29)), ("Yılbaşı", dt.date(y + 1, 1, 1)),
                            ("Ulusal Egemenlik ve Çocuk Bayramı", dt.date(y + 1, 4, 23)),
                            ("Emek ve Dayanışma Günü", dt.date(y + 1, 5, 1)),
                            ("Atatürk'ü Anma, Gençlik ve Spor Bayramı", dt.date(y + 1, 5, 19))):
                if d.strftime("%d.%m.%Y") not in existing:
                    add(name, d.isoformat(), d.isoformat())

        btns = ctk.CTkFrame(b, fg_color="transparent")
        btns.grid(row=1, column=0, columnspan=3, sticky="w", pady=(8, 0))
        ctk.CTkButton(btns, text="+ Tatil ekle", width=110, command=add).pack(side="left")
        ctk.CTkButton(btns, text="Resmî tatilleri ekle (bu eğitim yılı)", fg_color="transparent", border_width=1,
                      text_color=theme.TEXT, command=add_official).pack(side="left", padx=8)
        self._hint(b, "Dinî bayramların tarihleri her yıl değiştiği için onları elle eklemeniz gerekir.", row=2)

        def parse_date(text, label):
            try:
                return dt.datetime.strptime(text.strip(), "%d.%m.%Y").date()
            except ValueError:
                raise ValueError(f"Tatiller: «{label}» için girilen «{text}» geçerli bir tarih değil. "
                                 "GG.AA.YYYY biçiminde yazın (ör. 29.10.2026).")

        def collect():
            cfg["active_days"] = [i for i, v in enumerate(day_vars) if v.get()]
            out = []
            for _, n, s, e in rows:
                if not (n.get().strip() or s.get().strip() or e.get().strip()):
                    continue
                label = n.get().strip() or "Tatil"
                start = parse_date(s.get(), label)
                end = parse_date(e.get(), label) if e.get().strip() else start
                if end < start:
                    raise ValueError(f"Tatiller: «{label}» için bitiş tarihi başlangıçtan önce olamaz.")
                out.append({"name": label, "start": start.isoformat(), "end": end.isoformat()})
            cfg["holidays"] = out
        self._collectors.append(collect)

    def _tab_tts(self, f):
        cfg, tc = self.cfg, self.cfg["tts"]
        b = self._card(f, "Sesli Anons", "Açılırsa zil sesinden sonra Türkçe bir anons okunur "
                                         "(ör. «Sayın öğretmenlerimiz, üçüncü ders başlamıştır.»).")
        enabled = ctk.BooleanVar(value=tc.get("enabled", False))
        ctk.CTkSwitch(b, text="Sesli anonsları kullan", variable=enabled, font=theme.font(14, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=4)
        voice = ctk.CTkOptionMenu(b, values=list(tts.EDGE_VOICES.values()), width=200)
        voice.set(tts.EDGE_VOICES.get(tc.get("voice"), "Emel (Kadın)"))
        labeled_row(b, 1, "Ses", voice)
        self._hint(b, "Anonslar ilk kez internet ile hazırlanır ve bilgisayara kaydedilir; sonrasında internet "
                      "olmadan da çalar. Program açıkken günün anonsları önceden hazırlanır.", row=2)

        expert = {}
        if self._at_least("uzman"):
            b = self._card(f, "Anons Motoru (Uzman)")
            engine = ctk.CTkOptionMenu(b, values=list(tts.ENGINES.values()), width=380)
            engine.set(tts.ENGINES.get(tc.get("engine", "edge")))
            labeled_row(b, 0, "Motor", engine)
            rate_lbl = ctk.CTkLabel(b, text="")
            rate = ctk.CTkSlider(b, from_=-50, to=50, number_of_steps=20, width=260,
                                 command=lambda v: rate_lbl.configure(text=f"{int(v):+d}%"))
            rate.set(tc.get("rate", 0))
            rate_lbl.configure(text=f"{int(tc.get('rate', 0)):+d}%")
            labeled_row(b, 1, "Konuşma hızı", rate)
            rate_lbl.grid(row=1, column=2, padx=8)
            tvol = ctk.CTkSlider(b, from_=10, to=100, number_of_steps=18, width=260)
            tvol.set(tc.get("volume", 100))
            labeled_row(b, 2, "Anons ses düzeyi", tvol)
            pause = Spin(b, tc.get("pause_ms", 400), 0, 5000, suffix="milisaniye")
            labeled_row(b, 3, "Zil ile anons arası", pause)
            off_voices = [("", "Otomatik (Türkçe ses varsa)")]
            off_menu = ctk.CTkOptionMenu(b, values=[n for _, n in off_voices], width=380)
            off_menu.set(off_voices[0][1])
            labeled_row(b, 4, "Windows sesi", off_menu)

            def load_voices():
                found = tts.offline_voices()
                off_voices[1:] = found
                off_menu.configure(values=[n for _, n in off_voices])
                for vid, n in off_voices:
                    if vid == tc.get("offline_voice", ""):
                        off_menu.set(n)
                if not found:
                    messagebox.showinfo("Windows sesleri", "Bu bilgisayarda Windows sesi bulunamadı.", parent=self)
            ctk.CTkButton(b, text="Sesleri listele", width=120, command=load_voices).grid(row=4, column=2, padx=8)

            def clear():
                n = tts.clear_cache()
                messagebox.showinfo("Önbellek", f"{n} kayıtlı anons silindi. Gerektiğinde yeniden hazırlanacak.",
                                    parent=self)
            ctk.CTkButton(b, text="Kayıtlı anonsları sil", fg_color="transparent", border_width=1,
                          text_color=theme.TEXT, command=clear).grid(row=5, column=0, sticky="w", pady=(10, 0))
            expert = dict(engine=engine, rate=rate, volume=tvol, pause=pause, off_menu=off_menu,
                          off_voices=off_voices)

        b = self._card(f, "Anons Metinleri",
                       "Metinlerde şu kısaltmaları kullanabilirsiniz:  {ders_sira} → «üçüncü»,  "
                       "{ders} → «3»,  {saat} → «10:10».")
        texts = {}
        r = 0
        fields = [("ogrenci", "text", "Öğrenci zili"), ("ogretmen", "text", "Öğretmen zili"),
                  ("cikis", "text", "Çıkış zili (teneffüs)"), ("cikis", "text_lunch", "Çıkış zili (öğle arası)"),
                  ("cikis", "text_last", "Çıkış zili (son ders)")]
        tts_flags = {}
        for kind, key, label in fields:
            if kind not in tts_flags:
                v = ctk.BooleanVar(value=cfg["bells"][kind].get("tts", True))
                ctk.CTkCheckBox(b, text=f"{BELL_NAMES[kind]} çalınca anons yap", variable=v,
                                font=theme.font(13, "bold")).grid(row=r, column=0, columnspan=3, sticky="w",
                                                                  pady=(10 if r else 0, 2))
                tts_flags[kind] = v
                r += 1
            ctk.CTkLabel(b, text=label, anchor="w", width=170).grid(row=r, column=0, sticky="w")
            e = ctk.CTkEntry(b, width=520)
            e.insert(0, cfg["bells"][kind].get(key, ""))
            e.grid(row=r, column=1, sticky="w", pady=2)
            ctk.CTkButton(b, text="▶ Dene", width=70, command=lambda e=e: self._try_text(e.get())).grid(
                row=r, column=2, padx=8)
            texts[(kind, key)] = e
            r += 1

        def collect():
            tc["enabled"] = bool(enabled.get())
            tc["voice"] = next(k for k, v in tts.EDGE_VOICES.items() if v == voice.get())
            for (kind, key), e in texts.items():
                cfg["bells"][kind][key] = e.get().strip()
            for kind, v in tts_flags.items():
                cfg["bells"][kind]["tts"] = bool(v.get())
            if expert:
                tc["engine"] = next(k for k, v in tts.ENGINES.items() if v == expert["engine"].get())
                tc["rate"] = int(expert["rate"].get())
                tc["volume"] = int(expert["volume"].get())
                try:
                    tc["pause_ms"] = expert["pause"].get()
                except ValueError as exc:
                    raise ValueError(f"Zil ile anons arası: {exc}")
                chosen = expert["off_menu"].get()
                tc["offline_voice"] = next((vid for vid, n in expert["off_voices"] if n == chosen), "")
        self._collectors.append(collect)

    def _try_text(self, template):
        """Anons metnini, pencerede seçili (henüz kaydedilmemiş) ses ayarlarıyla okur."""
        if not self._collect():
            return
        try:
            text = template.format(ders=3, ders_sira=ordinal_word(3), saat="10:10")
        except (KeyError, IndexError, ValueError):
            text = template
        text = capitalize_first(text.strip())
        if text:
            self.app.player.say(text, tts_cfg=copy.deepcopy(self.cfg["tts"]), preview=True)

    def _tab_overrides(self, f):
        cfg = self.cfg
        self._hint(f, "Belirli bir günün ders saatleri farklıysa (ör. Cuma günü erken çıkış) o gün için özel "
                      "saatler girebilirsiniz. Özel saat girilmeyen günlerde «Ders Saatleri» sekmesindeki "
                      "ayarlar kullanılır.", row=0)
        seg = ctk.CTkSegmentedButton(f, values=DAYS)
        seg.grid(row=1, column=0, sticky="w", pady=8, padx=4)
        pages = {}
        for wd, day in enumerate(DAYS):
            current = cfg["day_overrides"].get(str(wd))
            card = Card(f, f"{day} günü ders saatleri")
            use = ctk.BooleanVar(value=bool(current))
            ctk.CTkCheckBox(card.body, text=f"{day} için özel ders saatleri kullan", variable=use).grid(
                row=0, column=0, sticky="w")
            base = current or [[fmt_hm(a), fmt_hm(b)] for a, b in schedule.lessons_for_weekday(
                dict(cfg, day_overrides={}), wd)]
            table = LessonTable(card.body, base, fill_source=lambda wd=wd: [
                [fmt_hm(a), fmt_hm(b)] for a, b in schedule.lessons_for_weekday(dict(self.cfg, day_overrides={}), wd)])
            table.grid(row=1, column=0, sticky="w", pady=(8, 0))
            pages[wd] = (card, use, table)

        def show(day):
            wd = DAYS.index(day)
            for i, (card, _, _) in pages.items():
                if i == wd:
                    card.grid(row=2, column=0, sticky="ew", padx=4, pady=6)
                else:
                    card.grid_remove()
        seg.configure(command=show)
        first = next((int(k) for k in sorted(cfg["day_overrides"])), 4)
        seg.set(DAYS[first])
        show(DAYS[first])

        def collect():
            out = {}
            for wd, (_, use, table) in pages.items():
                if use.get():
                    out[str(wd)] = table.get(f"{DAYS[wd]} özel saatleri")
            cfg["day_overrides"] = out
        self._collectors.append(collect)

    def _tab_extra(self, f):
        cfg = self.cfg
        self._hint(f, "Ders zilleri dışında belirli gün ve saatlerde çalacak ziller ekleyebilirsiniz "
                      "(ör. Pazartesi bayrak töreni, İstiklal Marşı, öğle namazı arası vb.).", row=0)
        holder = ctk.CTkFrame(f, fg_color="transparent", height=1)
        holder.grid(row=1, column=0, sticky="ew")
        holder.grid_columnconfigure(0, weight=1)
        items = []

        def add(e=None):
            e = e or {"enabled": True, "time": "08:20", "days": [0], "label": "Yeni zil",
                      "sound": "", "text": "", "duration": DEFAULT_RING_SECONDS}
            card = ctk.CTkFrame(holder, fg_color=theme.CARD_BG, corner_radius=12)
            card.grid(row=len(items) + 1, column=0, sticky="ew", pady=5, padx=4)
            line1 = ctk.CTkFrame(card, fg_color="transparent")
            line1.pack(fill="x", padx=12, pady=(10, 4))
            en = ctk.BooleanVar(value=e.get("enabled", True))
            ctk.CTkCheckBox(line1, text="Etkin", variable=en, width=70).pack(side="left")
            label = ctk.CTkEntry(line1, width=220, placeholder_text="Zilin adı")
            label.insert(0, e.get("label", ""))
            label.pack(side="left", padx=6)
            ctk.CTkLabel(line1, text="Saat").pack(side="left", padx=(10, 4))
            tm = time_entry(line1, e.get("time", ""))
            tm.pack(side="left")
            day_vars = []
            for i, d in enumerate(SHORT_DAYS):
                v = ctk.BooleanVar(value=i in e.get("days", []))
                ctk.CTkCheckBox(line1, text=d, variable=v, width=56, checkbox_width=18,
                                checkbox_height=18).pack(side="left", padx=(6 if i == 0 else 0, 0))
                day_vars.append(v)
            line2 = ctk.CTkFrame(card, fg_color="transparent")
            line2.pack(fill="x", padx=12, pady=(0, 10))
            dur = duration_spin(line2, e.get("duration"))
            picker = SoundPicker(line2, self.app.player, e.get("sound", ""), open_library=self._open_library,
                                 duration_spin=dur)
            picker.length_lbl.pack_forget()
            picker.pack(side="left")
            self._pickers.append(picker)
            ctk.CTkLabel(line2, text="Süre").pack(side="left", padx=(10, 4))
            dur.pack(side="left")
            text = ctk.CTkEntry(line2, width=230, placeholder_text="Anons metni (isteğe bağlı)")
            text.insert(0, e.get("text", ""))
            text.pack(side="left", padx=8)
            item = {"card": card, "en": en, "label": label, "time": tm, "days": day_vars, "picker": picker,
                    "text": text, "duration": dur, "orig": dict(e)}

            def remove():
                card.destroy()
                items.remove(item)
                refresh_empty()
            ctk.CTkButton(line2, text="Sil", width=60, fg_color=theme.DANGER, hover_color=theme.DANGER_HOVER,
                          command=remove).pack(side="right")
            items.append(item)
            refresh_empty()

        empty = ctk.CTkLabel(holder, text="Henüz ek zil yok. Aşağıdaki düğmelerle yeni zil ekleyebilir ya da "
                                          "hazır örneklerden birini seçebilirsiniz.",
                             text_color=theme.MUTED, anchor="w")

        def refresh_empty():
            if items:
                empty.grid_remove()
            else:
                empty.grid(row=0, column=0, sticky="w", padx=8, pady=10)

        for e in cfg.get("extra_bells", []):
            add(e)
        refresh_empty()

        btns = ctk.CTkFrame(f, fg_color="transparent")
        btns.grid(row=2, column=0, sticky="w", pady=8, padx=4)
        ctk.CTkButton(btns, text="+ Ek zil ekle", command=add).pack(side="left")
        ctk.CTkLabel(btns, text="Hazır örnekler:", text_color=theme.MUTED).pack(side="left", padx=(16, 0))
        ctk.CTkButton(btns, text="Pazartesi bayrak töreni", fg_color="transparent", border_width=1,
                      text_color=theme.TEXT, command=lambda: add({
                          "enabled": True, "time": "08:20", "days": [0], "label": "Bayrak Töreni",
                          "sound": "",
                          "text": "Sevgili öğrenciler, bayrak töreni için okul bahçesinde toplanınız."})).pack(
            side="left", padx=8)
        ctk.CTkButton(btns, text="Cuma haftayı kapatma", fg_color="transparent", border_width=1,
                      text_color=theme.TEXT, command=lambda: add({
                          "enabled": True, "time": "15:25", "days": [4], "label": "Bayrak Töreni (Cuma)",
                          "sound": "",
                          "text": "Sevgili öğrenciler, haftayı kapatma töreni için hazırlanınız."})).pack(side="left")

        def collect():
            out = []
            for it in items:
                name = it["label"].get().strip() or "Ek zil"
                try:
                    tm = fmt_hm(parse_hm(it["time"].get()))
                except ValueError:
                    raise ValueError(f"Ek Ziller: «{name}» için saat SS:DD biçiminde olmalı (ör. 08:20).")
                days = [i for i, v in enumerate(it["days"]) if v.get()]
                try:
                    seconds = it["duration"].get()
                except ValueError as exc:
                    raise ValueError(f"Ek Ziller: «{name}» çalma süresi: {exc}")
                if not days:
                    raise ValueError(f"Ek Ziller: «{name}» için en az bir gün seçin.")
                out.append({**it["orig"], "enabled": bool(it["en"].get()), "time": tm, "days": days, "label": name,
                            "sound": it["picker"].get(), "text": it["text"].get().strip(),
                            "duration": seconds})
            seen = set()
            for e in out:
                for d in e["days"]:
                    key = (e["label"], e["time"], d)
                    if key in seen:
                        raise ValueError(f"Ek Ziller: «{e['label']}» adında, {e['time']} saatinde ve aynı günde "
                                         "iki zil var. Lütfen birini silin ya da adını değiştirin.")
                    seen.add(key)
            cfg["extra_bells"] = out
        self._collectors.append(collect)

    def _tab_bell_list(self, f):
        """Profesyonel: günün her zilini tek tek açıp kapatma."""
        cfg = self.cfg
        state = {k: list(v) for k, v in cfg.get("disabled_bells", {}).items()}
        self._hint(f, "İşareti kaldırılan zil çalmaz. «Her gün» seçiliyken kapatılan zil bütün günlerde kapalıdır; "
                      "bir gün seçerek yalnızca o güne özel kapatabilirsiniz. Yalnızca bugün için kapatmak "
                      "isterseniz ana ekrandaki «Kapat» düğmesini kullanın.", row=0)
        choices = ["Her gün"] + DAYS
        seg = ctk.CTkSegmentedButton(f, values=choices)
        seg.grid(row=1, column=0, sticky="w", pady=8, padx=4)
        card = Card(f, "Zil listesi")
        card.grid(row=2, column=0, sticky="ew", padx=4, pady=6)
        holder = card.body

        def toggle(scope, bell_id, var):
            ids = state.setdefault(scope, [])
            if var.get() and bell_id in ids:
                ids.remove(bell_id)
            elif not var.get() and bell_id not in ids:
                ids.append(bell_id)

        def show(choice):
            for w in holder.winfo_children():
                w.destroy()
            scope = "all" if choice == "Her gün" else str(DAYS.index(choice))
            wd = 0 if scope == "all" else int(scope)
            tmp = dict(cfg, disabled_bells={})
            events = schedule.events_for_lessons(tmp, schedule.lessons_for_weekday(tmp, wd))
            if scope != "all":
                events += schedule.extra_events(tmp, wd)
            events.sort(key=lambda e: e.minute)
            if not events:
                ctk.CTkLabel(holder, text="Bu gün için zil yok.", text_color=theme.MUTED).grid(row=0, column=0)
            for r, e in enumerate(events):
                morning_off = bool(e.off)   # Sabah Zilleri ayarından kapatılmış
                every_day_off = morning_off or (scope != "all" and e.bell_id in state.get("all", []))
                var = ctk.BooleanVar(value=not every_day_off and e.bell_id not in state.get(scope, []))
                cb = ctk.CTkCheckBox(holder, text="", variable=var, width=28,
                                     command=lambda e=e, v=var: toggle(scope, e.bell_id, v))
                cb.grid(row=r, column=0, pady=2)
                if every_day_off:
                    cb.configure(state="disabled")
                ctk.CTkLabel(holder, text=e.time_str, font=theme.font(14, "bold"), width=56).grid(row=r, column=1)
                ctk.CTkLabel(holder, text=e.label, width=120, corner_radius=6, text_color="white",
                             fg_color=theme.BELL_COLORS[e.kind], font=theme.font(12, "bold")).grid(
                    row=r, column=2, padx=6)
                if morning_off:
                    note = e.note + "   (Ders Saatleri → Sabah Zilleri ayarından kapalı)"
                else:
                    note = e.note + ("   (her gün kapalı)" if every_day_off else "")
                ctk.CTkLabel(holder, text=note, anchor="w").grid(row=r, column=3, sticky="w", padx=6)
            if scope == "all":
                ctk.CTkLabel(holder, text="Liste Pazartesi gününün ders saatlerine göre gösterilir; zil kimliği "
                                          "ders numarasına bağlıdır (ör. «3. dersin çıkış zili»).",
                             text_color=theme.MUTED, font=theme.font(12)).grid(
                    row=len(events), column=0, columnspan=10, sticky="w", pady=(8, 0))
            card.title_label.configure(text=f"{choice} – zil listesi")
        seg.configure(command=show)
        seg.set("Her gün")
        show("Her gün")

        def collect():
            cfg["disabled_bells"] = {k: v for k, v in state.items() if v}
        self._collectors.append(collect)

    def _tab_profiles(self, f):
        """Profesyonel: adlandırılmış zil programları ve tarihlere atanmaları."""
        cfg = self.cfg
        self._hint(f, "Zil programı; ders saatleri, süreler, güne özel saatler ve kapatılan zillerden oluşur. "
                      "Örneğin «Kısaltılmış Ders» programını kaydedip belirli tarihlerde otomatik "
                      "kullanılmasını sağlayabilirsiniz. O tarihlerin dışında normal ayarlar geçerlidir.", row=0)

        def summary(p):
            t = p["timing"]
            if p.get("schedule_mode") == "manual":
                text = f"{len(p.get('manual_lessons', []))} ders, saatler elle girilmiş"
            else:
                text = f"{t['lesson_count']} ders · {t['lesson_minutes']} dk · ilk ders {t['first_lesson']}"
            if p.get("day_overrides"):
                text += " · güne özel saatler var"
            return text

        def act(fn):
            """Önce ekrandaki girişleri al, sonra işlemi yap ve sekmeleri yeniden çiz."""
            if not self._collect():
                return
            fn()
            self._build_tabs(keep="Programlar")

        b = self._card(f, "Kayıtlı Zil Programları")
        if not cfg["profiles"]:
            ctk.CTkLabel(b, text="Henüz kayıtlı program yok.", text_color=theme.MUTED).grid(row=0, column=0, sticky="w")
        for r, (name, p) in enumerate(sorted(cfg["profiles"].items())):
            ctk.CTkLabel(b, text=name, font=theme.font(14, "bold"), anchor="w").grid(row=r, column=0, sticky="w")
            ctk.CTkLabel(b, text=summary(p), text_color=theme.MUTED, anchor="w").grid(
                row=r, column=1, sticky="w", padx=12)
            row = ctk.CTkFrame(b, fg_color="transparent")
            row.grid(row=r, column=2, sticky="e", pady=3)

            def use(name=name):
                cfg.update(copy.deepcopy(cfg["profiles"][name]))
                messagebox.showinfo("Zil programı", f"«{name}» programı yüklendi. Her gün kullanılması için "
                                                    "«Kaydet»e basın.", parent=self)

            def overwrite(name=name):
                cfg["profiles"][name] = config.profile_snapshot(cfg)

            def delete(name=name):
                del cfg["profiles"][name]
                cfg["profile_dates"] = [d for d in cfg["profile_dates"] if d.get("profile") != name]
            ctk.CTkButton(row, text="Her gün kullan", width=110, command=lambda u=use: act(u)).pack(side="left")
            ctk.CTkButton(row, text="Şu anki ayarlarla güncelle", width=170, fg_color="transparent", border_width=1,
                          text_color=theme.TEXT, command=lambda o=overwrite: act(o)).pack(side="left", padx=6)
            ctk.CTkButton(row, text="Sil", width=50, fg_color=theme.DANGER, hover_color=theme.DANGER_HOVER,
                          command=lambda d=delete: act(d)).pack(side="left")

        b = self._card(f, "Yeni Program", "Şu anki ders saatleri ve ayarlar yeni bir program olarak kaydedilir.")
        name_e = ctk.CTkEntry(b, width=260, placeholder_text="Program adı (ör. Sınav Haftası)")
        name_e.grid(row=0, column=0, sticky="w")

        def save_new():
            name = name_e.get().strip()
            if not name:
                messagebox.showerror("Program adı", "Lütfen programa bir ad verin.", parent=self)
                return
            if name in cfg["profiles"] and not messagebox.askyesno(
                    "Program zaten var", f"«{name}» adında bir program zaten var. Üzerine yazılsın mı?", parent=self):
                return
            act(lambda: cfg["profiles"].__setitem__(name, config.profile_snapshot(cfg)))

        def add_short():
            snap = config.profile_snapshot(cfg)
            snap.update(schedule_mode="auto", day_overrides={})
            snap["timing"]["lesson_minutes"] = 30
            cfg["profiles"]["Kısaltılmış Ders (30 dk)"] = snap
        ctk.CTkButton(b, text="Kaydet", width=90, command=save_new).grid(row=0, column=1, padx=8, sticky="w")
        ctk.CTkButton(b, text="Hazır örnek ekle: Kısaltılmış Ders (30 dk)", fg_color="transparent", border_width=1,
                      text_color=theme.TEXT, command=lambda: act(add_short)).grid(row=0, column=2, sticky="w")

        b = self._card(f, "Tarihlere Atanmış Programlar",
                       "Seçilen tarihte normal ayarlar yerine o program kullanılır. Tarih: GG.AA.YYYY")
        names = sorted(cfg["profiles"])
        rows = []
        holder = ctk.CTkFrame(b, fg_color="transparent")
        holder.grid(row=0, column=0, columnspan=4, sticky="w")

        def add_row(date="", profile=None):
            if not names:
                messagebox.showinfo("Program yok", "Önce bir zil programı kaydedin.", parent=self)
                return
            r = ctk.CTkFrame(holder, fg_color="transparent")
            r.pack(fill="x", pady=2)
            d = ctk.CTkEntry(r, width=120, placeholder_text="GG.AA.YYYY")
            if date:
                try:
                    d.insert(0, dt.date.fromisoformat(date).strftime("%d.%m.%Y"))
                except ValueError:
                    d.insert(0, date)
            d.pack(side="left")
            m = ctk.CTkOptionMenu(r, values=names, width=240)
            m.set(profile if profile in names else names[0])
            m.pack(side="left", padx=8)
            item = (r, d, m)
            ctk.CTkButton(r, text="✕", width=30, fg_color="transparent", text_color=theme.DANGER,
                          hover_color=theme.ROW_ALT, command=lambda: (r.destroy(), rows.remove(item))).pack(side="left")
            rows.append(item)

        for item in sorted(cfg["profile_dates"], key=lambda x: x.get("date", "")):
            if item.get("profile") in names:
                add_row(item.get("date", ""), item.get("profile"))
        ctk.CTkButton(b, text="+ Tarih ekle", width=110, command=add_row).grid(row=1, column=0, sticky="w", pady=(8, 0))

        def collect():
            out = []
            for _, d, m in rows:
                if not d.get().strip():
                    continue
                try:
                    day = dt.datetime.strptime(d.get().strip(), "%d.%m.%Y").date()
                except ValueError:
                    raise ValueError(f"Programlar: «{d.get()}» geçerli bir tarih değil. GG.AA.YYYY biçiminde yazın.")
                if any(x["date"] == day.isoformat() for x in out):
                    raise ValueError(f"Programlar: {d.get().strip()} tarihine birden fazla program atanmış. "
                                     "Her tarihe yalnızca bir program atanabilir.")
                out.append({"date": day.isoformat(), "profile": m.get()})
            cfg["profile_dates"] = out
        self._collectors.append(collect)

    def _tab_system(self, f):
        if self._at_least("profesyonel"):
            b = self._card(f, "Teknik Ayarlar (Profesyonel)")
            grace = Spin(b, self.cfg.get("grace_seconds", 45), 5, 600, suffix="saniye")
            labeled_row(b, 0, "Geç kalan zil süresi", grace,
                        "Bilgisayar zil anında meşgulse, zil bu süre içinde yine çalar.")
            prep = ctk.BooleanVar(value=self.cfg.get("prepare_announcements", True))
            ctk.CTkCheckBox(b, text="Günün anonslarını önceden hazırla (önerilir)", variable=prep).grid(
                row=1, column=0, columnspan=3, sticky="w", pady=4)

            def collect():
                try:
                    self.cfg["grace_seconds"] = grace.get()
                except ValueError as exc:
                    raise ValueError(f"Geç kalan zil süresi: {exc}")
                self.cfg["prepare_announcements"] = bool(prep.get())
            self._collectors.append(collect)

        b = self._card(f, "Yedekleme", "Ayarları bir dosyaya kaydedip başka bir bilgisayara aktarabilirsiniz.")
        row = ctk.CTkFrame(b, fg_color="transparent")
        row.grid(row=0, column=0, sticky="w")
        ctk.CTkButton(row, text="Ayarları yedekle…", command=self._export).pack(side="left")
        ctk.CTkButton(row, text="Yedekten geri yükle…", command=self._import).pack(side="left", padx=8)

        b = self._card(f, "Tehlikeli İşlem", "Bütün ayarlar (ders saatleri, sesler, tatiller, programlar) "
                                             "silinir ve ilk kurulum değerlerine döner.")
        ctk.CTkButton(b, text="Varsayılan ayarlara dön", fg_color=theme.DANGER, hover_color=theme.DANGER_HOVER,
                      command=self._reset).grid(row=0, column=0, sticky="w")

        b = self._card(f, "Veri Klasörü")
        ctk.CTkLabel(b, text=str(paths.data_dir()), anchor="w").grid(row=0, column=0, sticky="w")
        ctk.CTkButton(b, text="Klasörü aç", width=110, command=lambda: _open_path(paths.data_dir())).grid(
            row=0, column=1, padx=10, sticky="w")

        b = self._card(f, "Kayıtlar", "Çalan ziller ve olası hatalar burada görünür.")
        b.grid_columnconfigure(0, weight=1)
        b.grid_columnconfigure(9, weight=0)
        box = ctk.CTkTextbox(b, height=300, font=ctk.CTkFont(family="Consolas", size=12))
        box.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))

        def load():
            box.configure(state="normal")
            box.delete("1.0", "end")
            try:
                with open(paths.log_file(), encoding="utf-8", errors="replace") as fh:
                    lines = fh.readlines()[-300:]
                box.insert("end", "".join(reversed(lines)))
            except OSError:
                box.insert("end", "Henüz kayıt yok.")
            box.configure(state="disabled")
        ctk.CTkButton(b, text="Yenile", width=90, command=load).grid(row=0, column=0, sticky="w")
        load()

    # -- yedekleme ----------------------------------------------------------

    def _export(self):
        if not self._collect():
            return
        path = filedialog.asksaveasfilename(parent=self, title="Ayarları kaydet", defaultextension=".json",
                                            initialfile="okul_zili_ayarlar.json",
                                            filetypes=[("Ayar dosyası", "*.json")])
        if path:
            config.export_to(self.cfg, path)
            messagebox.showinfo("Dışa aktarıldı", "Ayarlar kaydedildi.", parent=self)

    def _import(self):
        path = filedialog.askopenfilename(parent=self, title="Ayar dosyası seçin",
                                          filetypes=[("Ayar dosyası", "*.json")])
        if not path:
            return
        try:
            self.cfg = config.import_from(path)
        except Exception as exc:  # noqa: BLE001 - kullanıcı her türlü dosyayı seçebilir
            messagebox.showerror("İçe aktarılamadı", f"Dosya okunamadı:\n{exc}", parent=self)
            return
        self.cfg["level"] = self.level
        self._build_tabs(keep="Sistem")
        messagebox.showinfo("İçe aktarıldı", "Ayarlar yüklendi. Uygulamak için «Kaydet»e basın.", parent=self)

    def _reset(self):
        if not messagebox.askyesno("Varsayılan ayarlar", "Tüm ayarlar varsayılan değerlere dönecek. Emin misiniz?",
                                   icon="warning", parent=self):
            return
        self.cfg = config.default_config()
        self.cfg["level"] = self.level
        self._build_tabs(keep="Sistem")
        messagebox.showinfo("Varsayılan ayarlar", "Varsayılan ayarlar yüklendi. Uygulamak için «Kaydet»e basın.",
                            parent=self)

    # -- kaydet / vazgeç ----------------------------------------------------

    def _save(self):
        if not self._collect():
            return
        bells = self.cfg["bells"]
        same = bells["ogrenci"]["sound"] == bells["ogretmen"]["sound"]
        if same and bells["ogrenci"]["sound"] not in (sounds.NO_SOUND, "") and not sounds.is_missing(bells["ogrenci"]["sound"]):
            if not messagebox.askyesno(
                    "Aynı zil sesi", "Öğrenci zili ile öğretmen zili aynı sesi kullanıyor; ayırt etmek zor "
                                     "olabilir.\n\nYine de kaydedilsin mi?", parent=self):
                return
        self.cfg["level"] = self.level
        self.app.apply_config(self.cfg, keep_runtime=True)
        self.app.player.stop_preview()
        if self.app.window is not None:
            self.app.window.flash("✓  Ayarlar kaydedildi")
        self.destroy()

    def _cancel(self):
        if self._snapshot() != self._baseline and not messagebox.askyesno(
                "Kaydedilmemiş değişiklikler", "Yaptığınız değişiklikler kaydedilmedi.\n\n"
                                              "Kaydetmeden kapatılsın mı?", icon="warning", parent=self):
            return
        self.app.player.stop_preview()
        self.destroy()


def _sec(v) -> str:
    return f"{v:g}".replace(".", ",")


def duration_spin(master, value):
    """Zil çalma süresi kutusu (saniye, yarım saniyelik adımlarla)."""
    return Spin(master, ring_seconds(value if value is not None else DEFAULT_RING_SECONDS),
                MIN_RING_SECONDS, MAX_RING_SECONDS, suffix="saniye", step=0.5, decimals=1)


def _open_path(path):
    if os.name == "nt":
        os.startfile(path)  # noqa: S606
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(path)])
