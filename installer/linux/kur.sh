#!/bin/sh
# Okul Zili – Linux kurulumu (Lubuntu, Ubuntu, Debian, Mint, Fedora…). Yönetici (sudo) izni gerekmez.
#   Kurmak için:     sh kur.sh
#   Kaldırmak için:  sh kur.sh --kaldir
# Program ~/.local/bin/okulzili olarak kurulur ve uygulama menüsüne eklenir. Ayarlar ve sesler
# ~/.local/share/OkulZili klasöründe durur (kaldırınca silinmez).
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
CONF="${XDG_CONFIG_HOME:-$HOME/.config}"
BIN="$HOME/.local/bin"
APPS="$DATA/applications"
ICONS="$DATA/icons/hicolor/256x256/apps"

if [ "$1" = "--kaldir" ]; then
    systemctl --user disable --now okulzili-bekci.timer >/dev/null 2>&1 || true
    rm -f "$BIN/okulzili" "$APPS/okulzili.desktop" "$ICONS/okulzili.png" "$CONF/autostart/okulzili.desktop" \
          "$CONF/systemd/user/okulzili-bekci.service" "$CONF/systemd/user/okulzili-bekci.timer"
    systemctl --user daemon-reload >/dev/null 2>&1 || true
    echo "Okul Zili kaldırıldı. Ayarlar ve sesler $DATA/OkulZili klasöründe duruyor (isterseniz silebilirsiniz)."
    echo "Program şu an açıksa «Programı kapat» ile kapatın."
    exit 0
fi

if [ ! -f "$DIR/okulzili" ]; then
    echo "Hata: «okulzili» dosyası bu klasörde bulunamadı. Paketi açtığınız klasörde çalıştırın." >&2
    exit 1
fi
mkdir -p "$BIN" "$APPS" "$ICONS"
install -m 755 "$DIR/okulzili" "$BIN/okulzili"
install -m 644 "$DIR/okulzili.png" "$ICONS/okulzili.png"
cat > "$APPS/okulzili.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Okul Zili
Comment=Okullar için otomatik zil programı
Exec="$BIN/okulzili"
Icon=okulzili
Terminal=false
Categories=Education;AudioVideo;Audio;
Keywords=zil;okul;bell;school;
StartupWMClass=OkulZili
DESKTOP
update-desktop-database "$APPS" >/dev/null 2>&1 || true
gtk-update-icon-cache -q "$DATA/icons/hicolor" >/dev/null 2>&1 || true

echo "Okul Zili kuruldu: uygulama menüsünde «Okul Zili» (Eğitim / Ses ve Video)."
if ! command -v systemd-inhibit >/dev/null 2>&1; then
    echo "Not: systemd-inhibit bulunamadı; okul saatlerinde uyku engellenemez. Güç ayarlarından uykuyu kapatın."
fi
if ! command -v wpctl >/dev/null 2>&1 && ! command -v pactl >/dev/null 2>&1; then
    echo "Not: Ses düzeyi denetimi için wpctl (PipeWire) ya da pactl (PulseAudio) gerekir."
fi
printf "Program şimdi açılsın mı? [E/h] "
read -r cevap || cevap=h
case "$cevap" in
    h|H|hayır|Hayır) ;;
    *) nohup "$BIN/okulzili" >/dev/null 2>&1 & ;;
esac
