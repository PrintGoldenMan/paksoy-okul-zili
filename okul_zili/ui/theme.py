"""Renkler ve yazı tipleri. Her renk (açık tema, koyu tema) çifti olarak verilir."""

import customtkinter as ctk

ACCENT = ("#1f5fae", "#3b82d6")
ACCENT_HOVER = ("#174b8a", "#2f6db5")
HEADER_BG = ("#1f3b63", "#16263d")
CARD_BG = ("#ffffff", "#1f2329")
WINDOW_BG = ("#eef2f7", "#14171c")
MUTED = ("#6b7480", "#8b95a3")
TEXT = ("#1b2430", "#e7ebf0")
ROW_ALT = ("#f5f7fa", "#242930")
ROW_NEXT = ("#fff4d6", "#3a3220")
DANGER = ("#c0392b", "#d9534f")
DANGER_HOVER = ("#9e2f23", "#b8443f")
SUCCESS = ("#1e8449", "#2ecc71")

BELL_COLORS = {
    "ogrenci": ("#2e9d5b", "#2fae66"),
    "ogretmen": ("#d9822b", "#e0913f"),
    "cikis": ("#7b4bc4", "#9166d6"),
    "ek": ("#2b8fb5", "#3aa3cc"),
}
BELL_HOVER = {
    "ogrenci": ("#247d49", "#268f53"),
    "ogretmen": ("#b86d22", "#c47c32"),
    "cikis": ("#633ba1", "#7752b8"),
    "ek": ("#22738f", "#2f86a6"),
}


def font(size=14, weight="normal"):
    return ctk.CTkFont(size=size, weight=weight)
