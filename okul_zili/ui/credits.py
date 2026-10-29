"""«Hakkında» penceresi: geliştirici, proje sayfası ve kullanılan açık kaynaklı yazılımlar."""

import logging
import tkinter
import warnings
import webbrowser

import customtkinter as ctk

from .. import APP_NAME, AUTHOR_LOGIN, AUTHOR_NAME, AUTHOR_URL, ISSUES_URL, PROJECT_URL, __version__, paths
from . import theme
from .widgets import center_over

log = logging.getLogger(__name__)

# Program içinde kullanılan açık kaynaklı yazılımlar (teşekkür listesi)
THIRD_PARTY = ("Python", "CustomTkinter", "pygame", "yt-dlp", "FFmpeg", "edge-tts", "pyttsx3", "pystray", "Pillow",
               "pycaw", "PyInstaller", "Inno Setup")


def _avatar(master, size):
    """Programla gelen geliştirici resmi (internet gerekmez); bulunamazsa None."""
    try:
        from PIL import Image   # CTkImage ayrıca PIL.ImageTk ister (derlemede --hidden-import ile eklenir)
        image = Image.open(paths.resource("assets/gelistirici.png"))
        return ctk.CTkImage(light_image=image, dark_image=image, size=(size, size))
    except Exception as exc:  # noqa: BLE001 - Pillow eksikse Tk'nin kendi PNG okuyucusu kullanılır
        log.debug("Geliştirici resmi Pillow ile yüklenemedi: %s", exc)
    try:
        return tkinter.PhotoImage(master=master, file=str(paths.resource("assets/gelistirici_kucuk.png")))
    except Exception as exc:  # noqa: BLE001 - resim yoksa pencere yine açılır
        log.debug("Geliştirici resmi yüklenemedi: %s", exc)
        return None


class CreditsDialog(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title(f"{APP_NAME} hakkında")
        self.resizable(False, False)
        self.configure(fg_color=theme.CARD_BG)
        self.transient(master)

        top = ctk.CTkFrame(self, fg_color=theme.HEADER_BG, corner_radius=0)
        top.pack(fill="x")
        ctk.CTkLabel(top, text=f"🔔  {APP_NAME}", font=theme.font(22, "bold"), text_color="white").pack(
            pady=(18, 0))
        ctk.CTkLabel(top, text=f"Sürüm {__version__} · ücretsiz ve açık kaynaklı (MIT lisansı)",
                     font=theme.font(12), text_color="#b9c7da").pack(pady=(0, 16))

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="x", padx=28, pady=(20, 6))
        ctk.CTkLabel(body, text="GELİŞTİRİCİ", font=theme.font(11, "bold"), text_color=theme.MUTED).pack()
        self._image = _avatar(self, 112)   # pencere açıkken resim silinmesin diye saklanır
        if self._image is not None:
            with warnings.catch_warnings():   # yedek PhotoImage için CustomTkinter'ın ölçek uyarısı
                warnings.simplefilter("ignore")
                pic = ctk.CTkLabel(body, text="", image=self._image, cursor="hand2")
            pic.pack(pady=(8, 6))
            pic.bind("<Button-1>", lambda e: webbrowser.open(AUTHOR_URL))
        ctk.CTkLabel(body, text=AUTHOR_NAME, font=theme.font(20, "bold")).pack()
        login = ctk.CTkLabel(body, text=f"@{AUTHOR_LOGIN}", font=theme.font(14), text_color=theme.ACCENT,
                             cursor="hand2")
        login.pack()
        login.bind("<Button-1>", lambda e: webbrowser.open(AUTHOR_URL))

        links = ctk.CTkFrame(body, fg_color="transparent")
        links.pack(pady=(14, 4))
        ctk.CTkButton(links, text="GitHub profili", width=150, font=theme.font(13, "bold"),
                      command=lambda: webbrowser.open(AUTHOR_URL)).pack(side="left", padx=4)
        ctk.CTkButton(links, text="Proje sayfası", width=150, fg_color="transparent", border_width=1,
                      text_color=theme.TEXT, command=lambda: webbrowser.open(PROJECT_URL)).pack(side="left", padx=4)
        ctk.CTkButton(links, text="Sorun bildir", width=120, fg_color="transparent", border_width=1,
                      text_color=theme.TEXT, command=lambda: webbrowser.open(ISSUES_URL)).pack(side="left", padx=4)

        ctk.CTkFrame(self, height=2, corner_radius=0, fg_color=theme.DONE_CHIP).pack(fill="x", padx=28,
                                                                                      pady=(14, 10))
        ctk.CTkLabel(self, text="Teşekkürler", font=theme.font(13, "bold")).pack(anchor="w", padx=28)
        ctk.CTkLabel(self, text="Okul Zili şu açık kaynaklı yazılımlarla yapıldı: " + ", ".join(THIRD_PARTY) + ".",
                     wraplength=420, justify="left", text_color=theme.MUTED, font=theme.font(12)).pack(
            anchor="w", padx=28, pady=(2, 0))

        ctk.CTkButton(self, text="Kapat", width=110, fg_color="transparent", border_width=1, text_color=theme.TEXT,
                      command=self.destroy).pack(pady=(16, 18))
        self.bind("<Escape>", lambda e: self.destroy())
        self.after(50, lambda: (center_over(self), self.lift(), self.focus_force()))
