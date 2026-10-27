"""Renkler ve yazı tipleri. Her renk (açık tema, koyu tema) çifti olarak verilir."""

import customtkinter as ctk

ACCENT = ("#1f5fae", "#3b82d6")
ACCENT_HOVER = ("#174b8a", "#2f6db5")
HEADER_BG = ("#1f3b63", "#16263d")
CARD_BG = ("#ffffff", "#1f2329")
WINDOW_BG = ("#eef2f7", "#14171c")
MUTED = ("#4b5563", "#a3adba")
TEXT = ("#1b2430", "#e7ebf0")
ROW_ALT = ("#f5f7fa", "#242930")
ROW_NEXT = ("#fff4d6", "#3a3220")
DANGER = ("#c0392b", "#d9534f")
DANGER_HOVER = ("#9e2f23", "#b8443f")
SUCCESS = ("#1e8449", "#1e8449")
SUCCESS_HOVER = ("#176b3a", "#176b3a")
WARNING_BG = ("#fdecea", "#4a1f1c")
WARNING = ("#fbbf24", "#f59e0b")          # sarı uyarı şeridi (ör. zil sesi seçilmedi)
WARNING_TEXT = ("#3b2600", "#2a1b00")
DONE_CHIP = ("#e1e5ea", "#353b43")      # çalmış/kapalı zil etiketi
DONE_CHIP_TEXT = ("#4b5563", "#a3adba")

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


def apply_overrides():
    """customtkinter'ın varsayılan renklerini okunaklı olacak şekilde değiştirir.
    set_default_color_theme() çağrısından sonra, pencereler oluşturulmadan önce çağrılmalıdır."""
    t = ctk.ThemeManager.theme
    seg = t["CTkSegmentedButton"]
    seg["fg_color"] = ("#5f6b7a", "#3a4048")
    seg["unselected_color"] = ("#5f6b7a", "#3a4048")      # beyaz yazı ile yeterli karşıtlık
    seg["unselected_hover_color"] = ("#4b5563", "#4a515a")
    seg["selected_color"] = ACCENT
    seg["selected_hover_color"] = ACCENT_HOVER
    seg["text_color"] = ("#ffffff", "#ffffff")
    sw = t["CTkSwitch"]
    sw["fg_color"] = ("#c3cad3", "#4a515a")
    sw["progress_color"] = ACCENT
    sw["button_color"] = ("#3d4652", "#e7ebf0")
    sw["button_hover_color"] = ("#1b2430", "#ffffff")
    t["CTkButton"]["fg_color"] = ACCENT
    t["CTkButton"]["hover_color"] = ACCENT_HOVER
    t["CTkCheckBox"]["fg_color"] = ACCENT
    t["CTkCheckBox"]["hover_color"] = ACCENT_HOVER
    t["CTkOptionMenu"]["fg_color"] = ACCENT
    t["CTkOptionMenu"]["button_color"] = ACCENT_HOVER
    t["CTkSlider"]["button_color"] = ACCENT
    t["CTkSlider"]["progress_color"] = ACCENT


def font(size=14, weight="normal"):
    return ctk.CTkFont(size=size, weight=weight)
