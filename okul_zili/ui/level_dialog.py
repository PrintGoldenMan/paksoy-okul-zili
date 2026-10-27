"""Ayar düzeyi seçimi: Basit -> Gelişmiş -> Uzman."""

import customtkinter as ctk

from ..config import LEVEL_DESCRIPTIONS, LEVEL_NAMES, LEVELS
from . import theme

LEVEL_ICONS = {"basit": "●", "gelismis": "●●", "uzman": "●●●"}
LEVEL_FOR = {"basit": "Okul müdürleri ve günlük kullanım için",
             "gelismis": "Ders saatlerini, tatilleri ve anonsları yönetmek için",
             "uzman": "Her ayarı kendisi yapmak isteyenler için"}


class LevelDialog(ctk.CTkToplevel):
    def __init__(self, master, current=None, on_select=None):
        super().__init__(master)
        self.title("Ayar Düzeyi Seçimi")
        self.on_select = on_select
        self.resizable(False, False)
        self.configure(fg_color=theme.WINDOW_BG)
        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", lambda: self._choose(current or "basit"))

        ctk.CTkLabel(self, text="Programı nasıl kullanmak istersiniz?",
                     font=theme.font(22, "bold")).pack(padx=30, pady=(26, 4))
        ctk.CTkLabel(self, text="Düzey, ayarlar ekranında ne kadar seçenek görüneceğini belirler. "
                                "Daha sonra Ayarlar'dan istediğiniz zaman değiştirebilirsiniz.",
                     text_color=theme.MUTED, wraplength=760).pack(padx=30, pady=(0, 18))

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(padx=24, pady=(0, 10))
        for i, level in enumerate(LEVELS):
            if i:
                ctk.CTkLabel(row, text="→", font=theme.font(26, "bold"), text_color=theme.MUTED).pack(
                    side="left", padx=4)
            self._card(row, level, level == current).pack(side="left", padx=6, fill="y")

        ctk.CTkLabel(self, text="Emin değilseniz «Basit» ile başlayın.",
                     text_color=theme.MUTED).pack(pady=(4, 22))
        self.after(50, self._focus)

    def _focus(self):
        self.lift()
        self.focus_force()
        try:
            self.grab_set()
        except Exception:  # noqa: BLE001 - pencere henüz görünür değilse
            pass

    def _card(self, master, level, selected):
        card = ctk.CTkFrame(master, fg_color=theme.CARD_BG, corner_radius=16, width=230,
                            border_width=3 if selected else 1,
                            border_color=theme.ACCENT if selected else ("#d5dbe3", "#2f353d"))
        ctk.CTkLabel(card, text=LEVEL_ICONS[level], font=theme.font(20, "bold"),
                     text_color=theme.ACCENT).pack(pady=(18, 0))
        ctk.CTkLabel(card, text=LEVEL_NAMES[level], font=theme.font(22, "bold")).pack()
        ctk.CTkLabel(card, text=LEVEL_FOR[level], font=theme.font(12, "bold"),
                     text_color=theme.MUTED, wraplength=200).pack(padx=14, pady=(2, 8))
        ctk.CTkLabel(card, text=LEVEL_DESCRIPTIONS[level], wraplength=200, justify="left",
                     font=theme.font(13), height=120, anchor="nw").pack(padx=16, fill="x")
        ctk.CTkButton(card, text="Seçili ✓" if selected else "Bunu Seç", height=38,
                      font=theme.font(14, "bold"),
                      command=lambda: self._choose(level)).pack(padx=16, pady=16, fill="x")
        return card

    def _choose(self, level):
        try:
            self.grab_release()
        except Exception:  # noqa: BLE001
            pass
        self.destroy()
        if self.on_select:
            self.on_select(level)
