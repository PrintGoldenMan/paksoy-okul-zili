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
    """Artır/azalt düğmeli sayı kutusu. .get() tam sayı (decimals=0) veya ondalıklı sayı döndürür.
    Ondalıklı değerler Türkçe biçimde virgülle gösterilir (ör. 3,5); nokta da kabul edilir."""

    def __init__(self, master, value, minimum, maximum, suffix="", step=1, decimals=0):
        super().__init__(master, fg_color="transparent")
        self.minimum, self.maximum, self.suffix = minimum, maximum, suffix
        self.step, self.decimals = step, decimals
        self.var = ctk.StringVar(value=self._fmt(value))
        ctk.CTkButton(self, text="−", width=32, command=lambda: self._step(-1)).pack(side="left")
        ctk.CTkEntry(self, textvariable=self.var, width=56, justify="center").pack(side="left", padx=4)
        ctk.CTkButton(self, text="+", width=32, command=lambda: self._step(1)).pack(side="left")
        if suffix:
            ctk.CTkLabel(self, text=suffix).pack(side="left", padx=(6, 0))

    def _fmt(self, v):
        if not self.decimals:
            return str(int(round(float(v))))
        return f"{float(v):.{self.decimals}f}".rstrip("0").rstrip(".").replace(".", ",")

    def _parse(self):
        text = self.var.get().strip().replace(",", ".")
        return float(text) if self.decimals else int(text)

    def _step(self, d):
        try:
            v = self._parse()
        except ValueError:
            v = self.minimum
        self.var.set(self._fmt(max(self.minimum, min(self.maximum, v + d * self.step))))

    def get(self):
        try:
            v = self._parse()
        except ValueError:
            raise ValueError(f"«{self.var.get()}» geçerli bir sayı değil")
        if not self.minimum <= v <= self.maximum:
            raise ValueError(f"{self._fmt(self.minimum)} ile {self._fmt(self.maximum)} arasında olmalı")
        return v
