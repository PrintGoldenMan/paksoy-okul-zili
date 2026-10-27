"""Ortak arayüz parçaları."""

import customtkinter as ctk

from . import theme


class Card(ctk.CTkFrame):
    """Başlıklı, yuvarlak köşeli kutu."""

    def __init__(self, master, title=None, subtitle=None, **kw):
        kw.setdefault("fg_color", theme.CARD_BG)
        kw.setdefault("corner_radius", 14)
        super().__init__(master, **kw)
        self.grid_columnconfigure(0, weight=1)
        row = 0
        self.title_label = None
        if title:
            self.title_label = ctk.CTkLabel(self, text=title, font=theme.font(16, "bold"), anchor="w")
            self.title_label.grid(row=row, column=0, sticky="ew", padx=16, pady=(12, 0))
            row += 1
        if subtitle:
            ctk.CTkLabel(self, text=subtitle, font=theme.font(12), text_color=theme.MUTED,
                         anchor="w", justify="left", wraplength=640).grid(
                row=row, column=0, sticky="ew", padx=16, pady=(2, 0))
            row += 1
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.grid(row=row, column=0, sticky="nsew", padx=16, pady=(8, 14))
        self.body.grid_columnconfigure(9, weight=1)  # boş sütun: fazla genişliği alır
        self.grid_rowconfigure(row, weight=1)


def time_entry(master, value="", width=72):
    e = ctk.CTkEntry(master, width=width, justify="center", placeholder_text="SS:DD")
    if value:
        e.insert(0, value)
    return e


def labeled_row(parent, row, label, widget, hint=None):
    ctk.CTkLabel(parent, text=label, anchor="w").grid(row=row, column=0, sticky="w", pady=5, padx=(0, 12))
    widget.grid(row=row, column=1, sticky="w", pady=5)
    if hint:
        ctk.CTkLabel(parent, text=hint, text_color=theme.MUTED, font=theme.font(12), anchor="w").grid(
            row=row, column=2, sticky="w", padx=(10, 0))


class Spin(ctk.CTkFrame):
    """Artır/azalt düğmeli sayı kutusu. .get() tam sayı döndürür."""

    def __init__(self, master, value, minimum, maximum, suffix=""):
        super().__init__(master, fg_color="transparent")
        self.minimum, self.maximum, self.suffix = minimum, maximum, suffix
        self.var = ctk.StringVar(value=str(value))
        ctk.CTkButton(self, text="−", width=32, command=lambda: self._step(-1)).pack(side="left")
        ctk.CTkEntry(self, textvariable=self.var, width=56, justify="center").pack(side="left", padx=4)
        ctk.CTkButton(self, text="+", width=32, command=lambda: self._step(1)).pack(side="left")
        if suffix:
            ctk.CTkLabel(self, text=suffix).pack(side="left", padx=(6, 0))

    def _step(self, d):
        try:
            v = int(self.var.get())
        except ValueError:
            v = self.minimum
        self.var.set(str(max(self.minimum, min(self.maximum, v + d))))

    def get(self) -> int:
        v = int(self.var.get())
        if not self.minimum <= v <= self.maximum:
            raise ValueError(f"{self.minimum} ile {self.maximum} arasında olmalı")
        return v
