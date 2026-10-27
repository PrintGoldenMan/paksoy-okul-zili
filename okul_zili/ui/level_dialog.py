"""Ayar düzeyi seçimi: Çok Kolay -> Basit -> Gelişmiş -> Uzman -> Profesyonel."""

import customtkinter as ctk

from ..config import LEVEL_DESCRIPTIONS, LEVEL_NAMES, LEVELS
from . import theme

LEVEL_FOR = {"kolay": "Hiç ayarla uğraşmak istemeyenler için",
             "basit": "Okul müdürleri ve günlük kullanım için",
             "gelismis": "Ders saatlerini, tatilleri ve anonsları yönetmek için",
             "uzman": "Her ayarı kendisi yapmak isteyenler için",
             "profesyonel": "Birden çok zil programı yönetenler için"}


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
                     text_color=theme.MUTED, wraplength=1000).pack(padx=30, pady=(0, 18))

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(padx=24, pady=(0, 10))
        for i, level in enumerate(LEVELS):
            if i:
                ctk.CTkLabel(row, text="→", font=theme.font(22, "bold"), text_color=theme.MUTED).pack(
                    side="left", padx=2)
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
        card = ctk.CTkFrame(master, fg_color=theme.CARD_BG, corner_radius=16, width=200,
                            border_width=3 if selected else 1,
                            border_color=theme.ACCENT if selected else ("#d5dbe3", "#2f353d"))
        rank = LEVELS.index(level) + 1
        ctk.CTkLabel(card, text="●" * rank + "○" * (len(LEVELS) - rank), font=theme.font(16, "bold"),
                     text_color=theme.ACCENT).pack(pady=(16, 0))
        ctk.CTkLabel(card, text=LEVEL_NAMES[level], font=theme.font(20, "bold")).pack()
        ctk.CTkLabel(card, text=LEVEL_FOR[level], font=theme.font(12, "bold"), height=34,
                     text_color=theme.MUTED, wraplength=170).pack(padx=12, pady=(2, 6))
        ctk.CTkLabel(card, text=LEVEL_DESCRIPTIONS[level], wraplength=172, justify="left",
                     font=theme.font(12), height=150, anchor="nw").pack(padx=12, fill="x")
        ctk.CTkButton(card, text="Seçili ✓" if selected else "Bunu Seç", height=36,
                      font=theme.font(14, "bold"),
                      command=lambda: self._choose(level)).pack(padx=12, pady=14, fill="x")
        return card

    def _choose(self, level):
        try:
            self.grab_release()
        except Exception:  # noqa: BLE001
            pass
        self.destroy()
        if self.on_select:
            self.on_select(level)
