"""Sistem tepsisi (saatin yanındaki simgeler) simgesi.

Pencere kapatılınca program kapanmaz, tepsiye küçülür; ziller çalmaya devam eder. Program yalnızca
tepsi simgesinin menüsündeki «Programı kapat» ile tamamen kapanır. pystray kullanılamıyorsa
(ör. desteklenmeyen sistem) available False olur ve pencere eskisi gibi kapanır.
"""

import logging
import queue
import threading

from . import paths

log = logging.getLogger(__name__)

# Linux'taki X11 tepsi altyapısı (pystray _xorg) başlığı Latin-1 olarak yazar: Latin-1'de olmayan
# harfler (ı, ş, ğ, «–») hataya yol açar, en yakın harfle değiştirilir.
_LATIN1 = str.maketrans({"–": "-", "—": "-", "ı": "i", "İ": "I", "ş": "s", "Ş": "S", "ğ": "g", "Ğ": "G"})


def _safe_title(text, backend):
    if backend.endswith("_xorg"):
        return text.translate(_LATIN1).encode("latin-1", "replace").decode("latin-1")
    return text


class Tray:
    def __init__(self):
        self.commands = queue.Queue()   # tepsi iş parçacığından ana pencereye: "show", "silence", "about", "quit"
        self.icon = None
        self.available = False
        try:
            import pystray
            from PIL import Image
            image = Image.open(paths.resource("assets/okul_zili.png"))
            menu = pystray.Menu(
                pystray.MenuItem("Okul Zili'ni göster", lambda: self.commands.put("show"), default=True),
                pystray.MenuItem("Çalan zili sustur", lambda: self.commands.put("silence")),
                pystray.MenuItem("Hakkında", lambda: self.commands.put("about")),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Programı kapat (ziller çalmaz)", lambda: self.commands.put("quit")),
            )
            self._backend = pystray.Icon.__module__
            self.icon = pystray.Icon("OkulZili", image, _safe_title("Okul Zili – ziller çalışıyor", self._backend),
                                     menu)
            if hasattr(self.icon, "run_detached"):
                self.icon.run_detached()
            else:
                threading.Thread(target=self.icon.run, name="tepsi", daemon=True).start()
            self.available = True
        except Exception as exc:  # noqa: BLE001 - tepsi olmadan da program çalışır
            log.info("Sistem tepsisi kullanılamıyor: %s", exc)

    def notify(self, message, title="Okul Zili"):
        if self.icon is not None:
            try:
                self.icon.notify(message, title)
            except Exception:  # noqa: BLE001 - bildirim desteklenmiyorsa önemli değil
                pass

    def set_tooltip(self, text):
        if self.icon is not None:
            try:
                self.icon.title = _safe_title(text, self._backend)
            except Exception:  # noqa: BLE001
                pass

    def stop(self):
        if self.icon is not None:
            try:
                self.icon.stop()
            except Exception:  # noqa: BLE001
                pass
