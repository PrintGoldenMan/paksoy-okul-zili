"""Ayar düzeyi seçimi: Çok Kolay -> Basit -> Gelişmiş -> Uzman -> Profesyonel."""

import customtkinter as ctk

from ..config import LEVEL_DESCRIPTIONS, LEVEL_NAMES, LEVELS
from . import theme

RECOMMENDED = "basit"
CARD_WIDTH = 214
LEVEL_FOR = {"kolay": "Ayarlarla hiç uğraşmak istemeyenler için",
             "basit": "Okul müdürleri ve günlük kullanım için",
             "gelismis": "Ders saatlerini, tatilleri ve anonsları yönetmek için",
             "uzman": "Her ayarı kendisi yapmak isteyenler için",
             "profesyonel": "Birden çok zil programı yönetenler için"}


class LevelDialog(ctk.CTkToplevel):
    def __init__(self, master, current=None, on_select=None):
        super().__init__(master)
        self.title("Okul Zili – Düzey Seçimi")
        self.on_select = on_select
        self._has_current = current in LEVELS
        self.resizable(False, False)
        self.configure(fg_color=theme.WINDOW_BG)
        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", lambda: self._choose(current or "basit"))

        ctk.CTkLabel(self, text="Programı nasıl kullanmak istersiniz?",
                     font=theme.font(22, "bold")).pack(padx=30, pady=(26, 4))
        ctk.CTkLabel(self, text="Düzey, ayarlar ekranında ne kadar seçenek görüneceğini belirler. "
                                "Zillerin çalışması her düzeyde aynıdır.",
                     text_color=theme.MUTED, font=theme.font(14), wraplength=900).pack(padx=30, pady=(0, 14))

        # Ekran darsa (ör. 1366x768 ve %125 ölçek) kartlar iki satıra dizilir.
        try:
            scale = ctk.ScalingTracker.get_window_scaling(self)
        except Exception:  # noqa: BLE001
            scale = 1.0
        screen_w = self.winfo_screenwidth() / scale
        screen_h = self.winfo_screenheight() / scale
        self.card_width = CARD_WIDTH
        if len(LEVELS) * (CARD_WIDTH + 12) > screen_w - 60:
            self.card_width = 176   # dar ekran: beş kart tek satırda daha dar
        per_row = max(2, min(len(LEVELS), int((screen_w - 60) // (self.card_width + 12))))
        rows = -(-len(LEVELS) // per_row)
        per_row = -(-len(LEVELS) // rows)   # satırları dengele: 4+1 yerine 3+2
        needed_h = rows * (330 if self.card_width == CARD_WIDTH else 360)
        avail_h = screen_h - 210   # başlıklar, alt yazı, görev çubuğu
        if needed_h > avail_h:
            grid = ctk.CTkScrollableFrame(self, fg_color="transparent", height=max(260, avail_h),
                                          width=per_row * (self.card_width + 12) + 10)
        else:
            grid = ctk.CTkFrame(self, fg_color="transparent")
        grid.pack(padx=24, pady=(0, 10))
        for i, level in enumerate(LEVELS):
            self._card(grid, level, level == current).grid(row=i // per_row, column=i % per_row,
                                                          padx=6, pady=6, sticky="ns")

        ctk.CTkLabel(self, text="Emin değilseniz «Basit» ile başlayın. Düzeyi Ayarlar penceresinin üstünden "
                                "istediğiniz zaman değiştirebilirsiniz.",
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
        recommended = level == RECOMMENDED
        highlight = selected or (recommended and selected is False and not self._has_current)
        narrow = self.card_width < CARD_WIDTH
        wrap = self.card_width - 26
        card = ctk.CTkFrame(master, fg_color=theme.CARD_BG, corner_radius=16, width=self.card_width,
                            border_width=3 if highlight else 1,
                            border_color=theme.ACCENT if highlight else ("#d5dbe3", "#2f353d"))
        badge = "ŞU ANKİ DÜZEY" if selected else ("ÖNERİLEN" if recommended else "")
        ctk.CTkLabel(card, text=badge, height=22, corner_radius=6, font=theme.font(11, "bold"),
                     fg_color=theme.ACCENT if badge else "transparent", text_color="white").pack(
            pady=(12, 0), padx=12, anchor="e" if badge else "center")
        rank = LEVELS.index(level) + 1
        ctk.CTkLabel(card, text="●" * rank + "○" * (len(LEVELS) - rank), font=theme.font(16, "bold"),
                     text_color=theme.ACCENT).pack(pady=(2, 0))
        ctk.CTkLabel(card, text=LEVEL_NAMES[level], font=theme.font(19 if narrow else 21, "bold")).pack()
        ctk.CTkLabel(card, text=LEVEL_FOR[level], font=theme.font(12 if narrow else 13, "bold"), height=36,
                     text_color=theme.MUTED, wraplength=wrap).pack(padx=12, pady=(2, 6))
        ctk.CTkLabel(card, text=LEVEL_DESCRIPTIONS[level], wraplength=wrap, justify="left",
                     font=theme.font(12 if narrow else 13), anchor="nw").pack(padx=12, fill="x")
        filled = highlight
        ctk.CTkButton(card, text="Seçili ✓" if selected else "Bunu Seç", height=38, font=theme.font(14, "bold"),
                      fg_color=theme.ACCENT if filled else "transparent", border_width=0 if filled else 2,
                      border_color=theme.ACCENT, text_color="white" if filled else theme.ACCENT,
                      hover_color=theme.ACCENT_HOVER if filled else theme.ROW_ALT,
                      command=lambda: self._choose(level)).pack(side="bottom", padx=12, pady=14, fill="x")
        return card

    def _choose(self, level):
        try:
            self.grab_release()
        except Exception:  # noqa: BLE001
            pass
        self.destroy()
        if self.on_select:
            self.on_select(level)
