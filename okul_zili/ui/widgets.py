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


def fit_to_screen(win, width, height, margin_w=24, margin_h=90):
    """Pencereyi ekrana sığacak şekilde boyutlandırıp ortalar.

    customtkinter boyutları ekran ölçeklemesiyle (ör. %125, %150) çarptığı için ekran boyutu
    ölçek oranına bölünerek hesaplanır. margin_h görev çubuğu ve başlık çubuğu içindir.
    Döndürülen değer: (genişlik, yükseklik) – ölçeklenmemiş birimlerle.
    """
    try:
        scale = ctk.ScalingTracker.get_window_scaling(win)
    except Exception:  # noqa: BLE001
        scale = 1.0
    screen_w = win.winfo_screenwidth() / scale
    screen_h = win.winfo_screenheight() / scale
    w = int(min(width, screen_w - margin_w))
    h = int(min(height, screen_h - margin_h))
    x = int(max(0, (screen_w - w) / 2))
    y = int(max(0, (screen_h - margin_h - h) / 2))
    win.geometry(f"{w}x{h}+{x}+{y}")
    return w, h


class SafeConfirm(ctk.CTkToplevel):
    """Dikkatle okunması gereken onaylar için pencere.

    «Vazgeç» büyük ve dikkat çekici; kabul düğmesi bilerek sade (gri, çerçeveli) tutulur ki
    alışkanlıkla basılmasın. countdown > 0 ise kabul düğmesi o kadar saniye kilitli kalır.
    accept_side="left"/"right" ile düğmelerin yeri değiştirilebilir (art arda iki onayda farklı
    yerde olması, ikinci pencerede aynı yere hızlıca tıklamayı önler). Enter ve Esc her zaman vazgeçer.
    """

    def __init__(self, master, title, heading, message, accept_text, countdown=0, accept_side="left"):
        super().__init__(master)
        self.title(title)
        self.result = False
        self.resizable(False, False)
        self.configure(fg_color=theme.CARD_BG)
        self.transient(master.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.bind("<Escape>", lambda e: self._cancel())
        self.bind("<Return>", lambda e: self._cancel())

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=26, pady=(22, 6))
        ctk.CTkLabel(head, text="⚠", font=theme.font(30, "bold"), text_color=("#b45309", "#f59e0b")).pack(
            side="left", padx=(0, 12))
        ctk.CTkLabel(head, text=heading, font=theme.font(19, "bold"), justify="left", anchor="w",
                     wraplength=440).pack(side="left", fill="x")
        ctk.CTkLabel(self, text=message, font=theme.font(14), justify="left", anchor="w",
                     wraplength=500).pack(fill="x", padx=26, pady=(4, 18))

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=26, pady=(0, 22))
        self._accept_text = accept_text
        self.accept_btn = ctk.CTkButton(
            row, text=accept_text, height=36, font=theme.font(13), fg_color="transparent",
            border_width=1, border_color=("#9aa3ae", "#5b636d"), text_color=theme.MUTED,
            hover_color=theme.ROW_ALT, command=self._accept)
        self.cancel_btn = ctk.CTkButton(row, text="Vazgeç", width=170, height=44, font=theme.font(16, "bold"),
                                        command=self._cancel)
        if accept_side == "left":
            self.accept_btn.pack(side="left")
            self.cancel_btn.pack(side="right")
        else:
            self.cancel_btn.pack(side="left")
            self.accept_btn.pack(side="right")

        self._left = int(countdown)
        if self._left > 0:
            self.accept_btn.configure(state="disabled")
            self._tick()
        self.after(50, self._focus)

    def _focus(self):
        # Pencereyi sahibinin ortasına yerleştir.
        try:
            self.update_idletasks()
            owner = self.master.winfo_toplevel()
            x = owner.winfo_rootx() + (owner.winfo_width() - self.winfo_width()) // 2
            y = owner.winfo_rooty() + (owner.winfo_height() - self.winfo_height()) // 3
            self.geometry(f"+{max(0, x)}+{max(0, y)}")
        except Exception:  # noqa: BLE001
            pass
        self.lift()
        self.cancel_btn.focus_set()
        try:
            self.grab_set()
        except Exception:  # noqa: BLE001
            pass

    def _tick(self):
        if not self.winfo_exists():
            return
        if self._left > 0:
            self.accept_btn.configure(text=f"{self._accept_text} ({self._left})", state="disabled")
            self._left -= 1
            self.after(1000, self._tick)
        else:
            self.accept_btn.configure(text=self._accept_text, state="normal")

    def _accept(self):
        if self._left > 0:
            return
        self.result = True
        self.destroy()

    def _cancel(self):
        self.result = False
        self.destroy()


def ask_safely(master, title, heading, message, accept_text, countdown=0, accept_side="left") -> bool:
    dlg = SafeConfirm(master, title, heading, message, accept_text, countdown, accept_side)
    master.wait_window(dlg)
    return dlg.result
