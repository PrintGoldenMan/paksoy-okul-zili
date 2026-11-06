#!/usr/bin/env bash
# Okul Zili – Linux kurulum / güncelleme / kaldırma betiği (Lubuntu, Ubuntu, Mint, Debian, Fedora…).
# Yönetici (sudo) izni gerekmez; program kullanıcının kendi klasörlerine kurulur.
#
#   bash kur.sh                    Kurar ya da eski sürümü günceller (ayarlar ve sesler korunur)
#   bash kur.sh --denetle          Yalnızca sistemi denetler, hiçbir şeyi değiştirmez
#   bash kur.sh --sifirla-ayarlar  Kurarken ayarları sıfırlar (sesler kalır; eski ayarlar yedeklenir)
#   bash kur.sh --sifirla-hepsi    Kurarken her şeyi sıfırlar (ayarlar + sesler; eski klasör yedeklenir)
#   bash kur.sh --kaldir           Programı kaldırır (ayarlar ve sesler kalır)
#   bash kur.sh --kaldir --verileri-de-sil   Programı ve bütün verilerini kaldırır
#   bash kur.sh --evet             Hiçbir şey sormaz, önerilen seçenekleri kullanır
#   bash kur.sh --yardim
#
# Program ~/.local/bin/okulzili olarak kurulur ve uygulama menüsüne eklenir. Ayarlar ve sesler
# ~/.local/share/OkulZili (eski sürümlerde ~/.okul_zili) klasöründedir.

# «sh kur.sh» ile çalıştırılırsa bash ile yeniden başlatılır.
if [ -z "${BASH_VERSION:-}" ]; then exec bash "$0" "$@"; fi
set -u

# -- ayarlar ve yollar ------------------------------------------------------------------------------
PAKET_DIZINI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERI_KOK="${XDG_DATA_HOME:-$HOME/.local/share}"
AYAR_KOK="${XDG_CONFIG_HOME:-$HOME/.config}"
BIN="$HOME/.local/bin"
PROGRAM="$BIN/okulzili"
UYGULAMALAR="$VERI_KOK/applications"
SIMGELER="$VERI_KOK/icons/hicolor/256x256/apps"
MASAUSTU="$UYGULAMALAR/okulzili.desktop"
OTOMATIK="$AYAR_KOK/autostart/okulzili.desktop"
SYSTEMD="$AYAR_KOK/systemd/user"
BEKCI="okulzili-bekci"
ESKI_VERI="$HOME/.okul_zili"
ARKA_PLAN="--oz-arka-plan"
GEREKEN_GLIBC="2.39"     # paket Ubuntu 24.04'te derlenir

# Programın kullandığı veri klasörü (okul_zili/paths.py ile aynı kural)
if [ -d "$ESKI_VERI" ]; then VERI="$ESKI_VERI"; else VERI="$VERI_KOK/OkulZili"; fi
AYARLAR="$VERI/ayarlar.json"

# -- seçenekler -------------------------------------------------------------------------------------
ISLEM="kur"; SIFIRLA=""; EVET=0; VERILERI_SIL=0
for arg in "$@"; do
    case "$arg" in
        --kaldir) ISLEM="kaldir" ;;
        --denetle) ISLEM="denetle" ;;
        --sifirla-ayarlar) SIFIRLA="ayarlar" ;;
        --sifirla-hepsi) SIFIRLA="hepsi" ;;
        --verileri-de-sil) VERILERI_SIL=1 ;;
        --evet|-y) EVET=1 ;;
        --yardim|-h|--help) sed -n '2,15p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Bilinmeyen seçenek: $arg (yardım için: bash kur.sh --yardim)" >&2; exit 2 ;;
    esac
done
[ -t 0 ] || EVET=1     # girdi yoksa (ör. borudan çalıştırıldıysa) soru sorulmaz

# -- görünüm ----------------------------------------------------------------------------------------
if [ -t 1 ]; then
    K=$'\e[1;31m'; S=$'\e[1;33m'; Y=$'\e[1;32m'; M=$'\e[1;34m'; B=$'\e[1m'; N=$'\e[0m'
else
    K=""; S=""; Y=""; M=""; B=""; N=""
fi
UYARILAR=0
baslik() { printf '\n%s== %s ==%s\n' "$M" "$1" "$N"; }
iyi()    { printf '  %s✓%s %s\n' "$Y" "$N" "$1"; }
uyari()  { printf '  %s!%s %s\n' "$S" "$N" "$1"; UYARILAR=$((UYARILAR + 1)); }
hata()   { printf '  %s✗%s %s\n' "$K" "$N" "$1"; }
bilgi()  { printf '    %s\n' "$1"; }
olumcul() { printf '\n%sHata:%s %s\n' "$K" "$N" "$1" >&2; exit 1; }
var() { command -v "$1" >/dev/null 2>&1; }

kayit() {
    mkdir -p "$VERI" 2>/dev/null || return 0
    printf '%s  %s\n' "$(date '+%d.%m.%Y %H:%M:%S')" "$1" >> "$VERI/kurulum.log" 2>/dev/null || true
}

# evet_mi "Soru" E|H   → önerilen yanıt büyük harfle gösterilir; --evet ile önerilen kullanılır
evet_mi() {
    local soru="$1" onerilen="${2:-E}" cevap
    if [ "$EVET" = 1 ]; then [ "$onerilen" = E ]; return; fi
    if [ "$onerilen" = E ]; then printf '%s [E/h] ' "$soru"; else printf '%s [e/H] ' "$soru"; fi
    read -r cevap || cevap=""
    cevap="${cevap,,}"
    case "$cevap" in
        "") [ "$onerilen" = E ] ;;
        e|evet|y|yes) return 0 ;;
        *) return 1 ;;
    esac
}

# surum_buyuk A B → A, B'den yeniyse doğru
surum_buyuk() { [ "$1" != "$2" ] && [ "$(printf '%s\n%s\n' "$1" "$2" | sort -V | tail -n1)" = "$1" ]; }

surum_oku() {   # $1: program dosyası → sürüm (okunamazsa boş)
    [ -x "$1" ] || return 0
    timeout 20 "$1" --version 2>/dev/null | tail -n1 | tr -d '[:space:]' | grep -E '^[0-9]+(\.[0-9]+)+$' || true
}

calisan_pidler() { pgrep -x -u "$(id -u)" okulzili 2>/dev/null || true; }

ayar_degeri() {   # ayarlar.json içinden basit bir metin değeri (python gerekmeden)
    [ -f "$AYARLAR" ] || return 0
    grep -o "\"$1\": *\"[^\"]*\"" "$AYARLAR" 2>/dev/null | head -n1 | sed 's/.*: *"//; s/"$//'
}

masaustu_exec() {   # Desktop Entry «Exec» değeri (okul_zili/autostart.py desktop_exec ile aynı kurallar)
    # Tırnak içinde \ " ` $ ters eğik çizgiyle kaçırılır; dize değeri olarak ters eğik çizgiler bir kez
    # daha ikilenir; % alan kodu sanılmasın diye %% yazılır.
    printf '"%s"' "$(printf '%s' "$1" | sed -e 's/\\/\\\\\\\\/g' -e 's/"/\\\\"/g' -e 's/`/\\\\`/g' \
                                         -e 's/\$/\\\\$/g' -e 's/%/%%/g')"
}

# -- sistem denetimi --------------------------------------------------------------------------------
EKSIK_PAKETLER=()

sistemi_denetle() {
    baslik "Sistem"
    local ad="bilinmiyor"
    if [ -r /etc/os-release ]; then ad="$(. /etc/os-release && printf '%s' "${PRETTY_NAME:-$NAME}")"; fi
    iyi "Dağıtım: $ad"

    local mimari; mimari="$(uname -m)"
    if [ "$mimari" = x86_64 ]; then iyi "İşlemci: $mimari"
    else hata "İşlemci: $mimari – bu paket yalnızca x86_64 (64 bit Intel/AMD) içindir"; return 1; fi

    local glibc; glibc="$(ldd --version 2>/dev/null | head -n1 | grep -oE '[0-9]+\.[0-9]+$' || true)"
    if [ -z "$glibc" ]; then uyari "glibc sürümü okunamadı"
    elif surum_buyuk "$GEREKEN_GLIBC" "$glibc"; then
        hata "glibc $glibc – en az $GEREKEN_GLIBC gerekir (Ubuntu/Lubuntu 24.04 ya da daha yeni)"; return 1
    else iyi "glibc $glibc"; fi

    local masaustu="${XDG_CURRENT_DESKTOP:-${DESKTOP_SESSION:-bilinmiyor}}" oturum="${XDG_SESSION_TYPE:-?}"
    iyi "Masaüstü: $masaustu (oturum: $oturum)"
    if [ -z "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; then
        uyari "Ekran bulunamadı (uzaktan bağlantı?). Programı masaüstünden açın."
    fi

    # Tepsi simgesi: panelde StatusNotifier izleyicisi var mı?
    local tepsi=""
    if var busctl; then
        busctl --user call org.freedesktop.DBus /org/freedesktop/DBus org.freedesktop.DBus NameHasOwner s \
            org.kde.StatusNotifierWatcher 2>/dev/null | grep -q true && tepsi=1
    elif var gdbus; then
        gdbus call --session --dest org.freedesktop.DBus --object-path /org/freedesktop/DBus \
            --method org.freedesktop.DBus.NameHasOwner org.kde.StatusNotifierWatcher 2>/dev/null | grep -q true && tepsi=1
    fi
    if [ -n "$tepsi" ]; then iyi "Tepsi simgesi gösterilebiliyor (pencere kapatılınca saatin yanında durur)"
    else
        uyari "Panelde tepsi simgesi desteği bulunamadı: pencere kapatılınca görev çubuğuna küçülür"
        case "${XDG_CURRENT_DESKTOP:-}" in
            *GNOME*) bilgi "GNOME için «AppIndicator and KStatusNotifierItem Support» eklentisini kurun." ;;
            *LXQt*) bilgi "LXQt panelinde «Durum Bildirici» (Status Notifier) eklentisini ekleyin." ;;
        esac
    fi

    baslik "Ses"
    if var wpctl && wpctl get-volume @DEFAULT_AUDIO_SINK@ >/dev/null 2>&1; then
        local ses; ses="$(wpctl get-volume @DEFAULT_AUDIO_SINK@ 2>/dev/null)"
        iyi "PipeWire: $ses"
        case "$ses" in *MUTED*) uyari "Ses KAPALI (sessiz) – ziller duyulmaz!" ;; esac
    elif var pactl && pactl info >/dev/null 2>&1; then
        iyi "PulseAudio: $(pactl get-sink-volume @DEFAULT_SINK@ 2>/dev/null | head -n1 | grep -oE '[0-9]+%' | head -n1)"
        pactl get-sink-mute @DEFAULT_SINK@ 2>/dev/null | grep -qi yes && uyari "Ses KAPALI (sessiz) – ziller duyulmaz!"
    else
        uyari "Ses sunucusu (PipeWire/PulseAudio) bulunamadı; ses düzeyi uyarısı çalışmaz"
    fi
    if var pavucontrol-qt || var pavucontrol; then iyi "Ses ayarları programı var"
    else uyari "Ses ayarları programı yok («Ses ayarlarını aç» düğmesi için)"; EKSIK_PAKETLER+=("pavucontrol-qt"); fi
    if var espeak-ng || var espeak; then iyi "espeak-ng var (internetsiz Türkçe anons)"
    else uyari "espeak-ng yok: internet yokken sesli anons okunamaz"; EKSIK_PAKETLER+=("espeak-ng"); fi

    baslik "Sistem hizmetleri"
    if var systemd-inhibit; then iyi "Uyku engeli (systemd-inhibit) kullanılabilir"
    else uyari "systemd-inhibit yok: okul saatlerinde uykuyu güç ayarlarından kapatın"; fi
    if var systemctl && systemctl --user show-environment >/dev/null 2>&1; then
        iyi "systemd kullanıcı oturumu var («kapanırsa yeniden aç» çalışır)"
    else uyari "systemd kullanıcı oturumu yok: program kapanırsa kendiliğinden açılmaz"; fi
    if var fc-list && fc-list 2>/dev/null | grep -qi "emoji"; then iyi "Emoji yazı tipi var"
    else uyari "Emoji yazı tipi yok: bazı simgeler kare görünebilir"; EKSIK_PAKETLER+=("fonts-noto-color-emoji"); fi

    baslik "Disk ve yollar"
    local bos; bos="$(df -Pm "$HOME" 2>/dev/null | awk 'NR==2 {print $4}')"
    if [ -n "$bos" ] && [ "$bos" -lt 400 ]; then uyari "Ev klasöründe yalnızca $bos MB boş yer var (en az 400 MB önerilir)"
    else iyi "Boş yer: ${bos:-?} MB"; fi
    case ":$PATH:" in
        *":$BIN:"*) iyi "$BIN yolda (uçbirimde «okulzili» yazılabilir)" ;;
        *) bilgi "Not: $BIN PATH'te değil; program menüden açılır (uçbirim için oturumu yeniden açın)." ;;
    esac
    if var curl && curl -fsI --max-time 5 https://api.github.com >/dev/null 2>&1; then
        iyi "İnternet var (güncellemeler, MEB takvimi, internet saati)"
    elif var curl; then uyari "İnternete ulaşılamadı: güncelleme ve internet saati çalışmaz (ziller çalışır)"; fi
    return 0
}

paket_oner() {
    [ "${#EKSIK_PAKETLER[@]}" -gt 0 ] || return 0
    baslik "Önerilen paketler"
    bilgi "Eksik: ${EKSIK_PAKETLER[*]}"
    if var apt-get && [ "$EVET" = 0 ] && evet_mi "  Şimdi kurulsun mu? (yönetici parolası sorulur)" H; then
        sudo apt-get install -y "${EKSIK_PAKETLER[@]}" || uyari "Paketler kurulamadı; sonra elle kurabilirsiniz."
    else
        if var apt-get; then bilgi "Kurmak için: sudo apt install ${EKSIK_PAKETLER[*]}"
        elif var dnf; then bilgi "Kurmak için (Fedora): sudo dnf install espeak-ng pavucontrol-qt google-noto-color-emoji-fonts"
        elif var pacman; then bilgi "Kurmak için (Arch): sudo pacman -S espeak-ng pavucontrol-qt noto-fonts-emoji"
        fi
    fi
}

# -- mevcut kurulumu bul ----------------------------------------------------------------------------
ESKI_SURUM=""; DIGER_KOPYALAR=()

mevcut_kurulum() {
    baslik "Mevcut kurulum"
    ESKI_SURUM="$(surum_oku "$PROGRAM")"
    if [ -n "$ESKI_SURUM" ]; then iyi "Kurulu sürüm: $ESKI_SURUM ($PROGRAM)"
    elif [ -e "$PROGRAM" ]; then uyari "$PROGRAM var ama sürümü okunamadı (çok eski ya da bozuk); yerine yenisi yazılacak"
    else bilgi "Program daha önce bu kullanıcıya kurulmamış."; fi

    # Başka yerlerdeki kopyalar: PATH, otomatik başlatma ve bekçinin gösterdiği yollar
    local yol aday
    for aday in "$(command -v okulzili 2>/dev/null || true)" \
                "$(grep -m1 '^Exec=' "$OTOMATIK" 2>/dev/null | sed 's/^Exec=//; s/^"//; s/".*//; s/ .*//')" \
                "$(grep -m1 '^ExecStart=' "$SYSTEMD/$BEKCI.service" 2>/dev/null | sed 's/^ExecStart=//; s/^"//; s/".*//')"; do
        yol="$aday"
        [ -n "$yol" ] && [ "$yol" != "$PROGRAM" ] || continue
        case " ${DIGER_KOPYALAR[*]:-} " in *" $yol "*) continue ;; esac
        DIGER_KOPYALAR+=("$yol")
        if [ -e "$yol" ]; then uyari "Başka bir kopya kullanılıyor: $yol ($(surum_oku "$yol"))"
        else uyari "Eski bir kayıt artık olmayan bir dosyayı gösteriyor: $yol"; fi
    done
    [ "${#DIGER_KOPYALAR[@]}" -gt 0 ] && bilgi "Otomatik başlatma ve bekçi yeni kuruluma yönlendirilecek."

    if [ -f "$AYARLAR" ]; then
        local okul; okul="$(ayar_degeri school_name)"
        iyi "Ayarlar: $AYARLAR${okul:+ (okul: $okul)}"
        local n=0
        [ -d "$VERI/kutuphane" ] && n="$(find "$VERI/kutuphane" -maxdepth 1 -name '*.opus' 2>/dev/null | wc -l)"
        bilgi "Kütüphanede $n ses · veri klasörü $(du -sh "$VERI" 2>/dev/null | cut -f1)"
        [ "$VERI" = "$ESKI_VERI" ] && bilgi "Eski sürümlerin veri klasörü kullanılıyor ($ESKI_VERI); olduğu gibi korunur."
    else
        bilgi "Kayıtlı ayar yok (ilk açılışta kurulum sihirbazı açılır)."
    fi

    local pidler; pidler="$(calisan_pidler)"
    [ -n "$pidler" ] && bilgi "Program şu an açık (süreç: $(echo $pidler))."
    return 0
}

# -- program durdurma / başlatma ---------------------------------------------------------------------
BEKCI_ACIKTI=0; CALISIYORDU=0

durdur() {
    if var systemctl && systemctl --user is-active --quiet "$BEKCI.timer" 2>/dev/null; then
        BEKCI_ACIKTI=1
        systemctl --user stop "$BEKCI.timer" 2>/dev/null || true   # kurulum sırasında eski programı açmasın
    fi
    local pidler; pidler="$(calisan_pidler)"
    [ -n "$pidler" ] || return 0
    CALISIYORDU=1
    bilgi "Açık olan program kapatılıyor…"
    kill -TERM $pidler 2>/dev/null || true

    for _ in $(seq 1 20); do
        [ -z "$(calisan_pidler)" ] && break
        sleep 0.5
    done
    pidler="$(calisan_pidler)"
    if [ -n "$pidler" ]; then kill -KILL $pidler 2>/dev/null || true; sleep 1; fi
    iyi "Program kapatıldı"
}

baslat() {
    nohup "$PROGRAM" "$@" >/dev/null 2>&1 &
    disown 2>/dev/null || true
}

# -- verileri sıfırlama ------------------------------------------------------------------------------
verileri_yedekle() {   # güncellemeden önce ayarların bir kopyası
    [ -f "$AYARLAR" ] || return 0
    mkdir -p "$VERI/yedekler"
    local hedef; hedef="$VERI/yedekler/ayarlar-${ESKI_SURUM:-eski}-$(date +%Y%m%d-%H%M%S).json"
    cp -p "$AYARLAR" "$hedef" && iyi "Ayarlar yedeklendi: $hedef"
    # en fazla 10 yedek tutulur
    ls -1t "$VERI/yedekler"/ayarlar-*.json 2>/dev/null | tail -n +11 | xargs -r rm -f
}

sifirlama_sor() {
    [ -d "$VERI" ] && [ -n "$(ls -A "$VERI" 2>/dev/null)" ] || return 0
    [ -n "$SIFIRLA" ] && return 0
    [ "$EVET" = 1 ] && { SIFIRLA="koru"; return 0; }
    baslik "Ayarlar ve sesler"
    echo "  1) Koru – ayarlar, ders saatleri ve sesler olduğu gibi kalsın (önerilen)"
    echo "  2) Yalnızca ayarları sıfırla – sesler/kütüphane kalır (eski ayarlar yedeklenir)"
    echo "  3) Her şeyi sıfırla – ayarlar, sesler, anons önbelleği (eski klasör yedek olarak saklanır)"
    local secim
    printf '  Seçiminiz [1]: '
    read -r secim || secim=1
    case "$secim" in
        2) SIFIRLA="ayarlar" ;;
        3) SIFIRLA="hepsi" ;;
        *) SIFIRLA="koru" ;;
    esac
}

sifirla() {
    case "$SIFIRLA" in
        ayarlar)
            [ -f "$AYARLAR" ] || return 0
            verileri_yedekle
            rm -f "$AYARLAR" "$AYARLAR.bak" "$VERI/kullanici_kapatti"
            iyi "Ayarlar sıfırlandı (program açılınca kurulum sihirbazı başlar); sesler korundu"
            kayit "Ayarlar sıfırlandı" ;;
        hepsi)
            [ -d "$VERI" ] || return 0
            local yedek; yedek="$VERI.yedek-$(date +%Y%m%d-%H%M%S)"
            mv "$VERI" "$yedek" && iyi "Bütün veriler sıfırlandı; eskisi saklandı: $yedek"
            kayit "Her şey sıfırlandı (eski veriler: $yedek)" ;;
    esac
}

# -- kurulum -----------------------------------------------------------------------------------------
dosyalari_kur() {
    local yeni="$PAKET_DIZINI/okulzili"
    [ -f "$yeni" ] || olumcul "«okulzili» dosyası bu klasörde yok. Betiği paketi açtığınız klasörde çalıştırın."
    if [ -f "$PAKET_DIZINI/SHA256SUMS" ] && var sha256sum; then
        (cd "$PAKET_DIZINI" && sha256sum --quiet -c SHA256SUMS) \
            || olumcul "Paket dosyaları bozuk (SHA256 tutmuyor). Paketi yeniden indirin."
        iyi "Paket bütünlüğü doğrulandı (SHA256)"
    fi
    mkdir -p "$BIN" "$UYGULAMALAR" "$SIMGELER"
    # Önce geçici ada kopyalanır, sonra tek adımda yerine konur (yarım kalmış dosya olmaz).
    install -m 755 "$yeni" "$BIN/.okulzili.yeni" || olumcul "$BIN içine yazılamadı."
    mv -f "$BIN/.okulzili.yeni" "$PROGRAM"
    [ -f "$PAKET_DIZINI/okulzili.png" ] && install -m 644 "$PAKET_DIZINI/okulzili.png" "$SIMGELER/okulzili.png"
    cat > "$MASAUSTU" <<MASAUSTU
[Desktop Entry]
Type=Application
Name=Okul Zili
Comment=Okullar için otomatik zil programı
Exec=$(masaustu_exec "$PROGRAM")
Icon=okulzili
Terminal=false
Categories=Education;AudioVideo;Audio;
Keywords=zil;okul;bell;school;
StartupWMClass=OkulZili
MASAUSTU
    var update-desktop-database && update-desktop-database "$UYGULAMALAR" >/dev/null 2>&1
    var gtk-update-icon-cache && gtk-update-icon-cache -q "$VERI_KOK/icons/hicolor" >/dev/null 2>&1
    iyi "Program kuruldu: $PROGRAM (menü: Eğitim → Okul Zili)"
}

otomatik_baslatma() {
    local acik=0
    if [ -f "$OTOMATIK" ] && ! grep -q '^Hidden=true' "$OTOMATIK"; then acik=1; fi
    if [ "$acik" = 1 ] || evet_mi "  Bilgisayar açılınca Okul Zili kendiliğinden başlasın mı? (önerilir)" E; then
        mkdir -p "$(dirname "$OTOMATIK")"
        cat > "$OTOMATIK" <<OTO
[Desktop Entry]
Type=Application
Name=Okul Zili
Comment=Okullar için otomatik zil programı
Exec=$(masaustu_exec "$PROGRAM") $ARKA_PLAN
Icon=okulzili
Terminal=false
X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Delay=5
OTO
        iyi "Bilgisayar açılınca başlar (pencere açılmadan, simge olarak)"
    else
        bilgi "Otomatik başlatma kapalı (sonra Ayarlar → Genel'den açılabilir)."
    fi
}

bekci_yonlendir() {
    # Bekçi birimi başka bir kopyayı gösteriyorsa yeni programa çevrilir (program da açılışta yeniler).
    local birim="$SYSTEMD/$BEKCI.service"
    [ -f "$birim" ] || return 0
    if ! grep -q "ExecStart=.*$(printf '%s' "$PROGRAM" | sed 's/[.[\*^$/]/\\&/g')" "$birim"; then
        sed -i "s|^ExecStart=.*|ExecStart=\"$PROGRAM\" \"--oz-watchdog\"|" "$birim"
        systemctl --user daemon-reload 2>/dev/null || true
        iyi "Bekçi yeni programa yönlendirildi"
    fi
}

kur() {
    printf '%sOkul Zili – Linux kurulumu%s\n' "$B" "$N"
    sistemi_denetle || olumcul "Bu bilgisayar desteklenmiyor."
    mevcut_kurulum
    local yeni_surum; yeni_surum="$(surum_oku "$PAKET_DIZINI/okulzili")"
    [ -n "$yeni_surum" ] || olumcul "Paketteki program çalıştırılamadı (dosya bozuk olabilir)."

    baslik "Kurulacak sürüm: $yeni_surum"
    if [ -n "$ESKI_SURUM" ]; then
        if surum_buyuk "$yeni_surum" "$ESKI_SURUM"; then
            iyi "Güncelleme: $ESKI_SURUM → $yeni_surum (ayarlar ve sesler korunur)"
        elif [ "$yeni_surum" = "$ESKI_SURUM" ]; then
            evet_mi "  Bu sürüm zaten kurulu. Yeniden kurulsun mu?" E || { bilgi "Değişiklik yapılmadı."; exit 0; }
        else
            uyari "Kurulu sürüm ($ESKI_SURUM) bu paketten ($yeni_surum) daha yeni."
            evet_mi "  Yine de eski sürüme dönülsün mü?" H || { bilgi "Değişiklik yapılmadı."; exit 0; }
        fi
    fi

    sifirlama_sor
    durdur
    [ "$SIFIRLA" = koru ] || [ -z "$SIFIRLA" ] && verileri_yedekle
    sifirla
    baslik "Kuruluyor"
    dosyalari_kur
    otomatik_baslatma
    bekci_yonlendir
    if [ "$BEKCI_ACIKTI" = 1 ]; then systemctl --user start "$BEKCI.timer" 2>/dev/null || true; fi
    paket_oner
    kayit "Kuruldu: ${ESKI_SURUM:-yok} → $yeni_surum (veriler: ${SIFIRLA:-koru})"

    baslik "Tamam"
    if [ "$CALISIYORDU" = 1 ]; then
        baslat --oz-restart
        iyi "Program yeni sürümle yeniden açıldı."
    elif { [ -n "${DISPLAY:-}" ] || [ -n "${WAYLAND_DISPLAY:-}" ]; } && evet_mi "  Program şimdi açılsın mı?" E; then
        baslat
        iyi "Program açılıyor."
    fi
    [ "$UYARILAR" -gt 0 ] && bilgi "Yukarıda $UYARILAR uyarı var; ziller yine de çalışır."
    bilgi "Kaldırmak için: bash kur.sh --kaldir"
}

# -- kaldırma ----------------------------------------------------------------------------------------
kaldir() {
    printf '%sOkul Zili – kaldırma%s\n' "$B" "$N"
    mevcut_kurulum
    evet_mi "  Okul Zili kaldırılsın mı?" E || { bilgi "Vazgeçildi."; exit 0; }
    durdur
    if var systemctl; then systemctl --user disable --now "$BEKCI.timer" >/dev/null 2>&1 || true; fi
    rm -f "$PROGRAM" "$MASAUSTU" "$SIMGELER/okulzili.png" "$OTOMATIK" "$SYSTEMD/$BEKCI.service" "$SYSTEMD/$BEKCI.timer"
    var systemctl && systemctl --user daemon-reload >/dev/null 2>&1
    var update-desktop-database && update-desktop-database "$UYGULAMALAR" >/dev/null 2>&1
    iyi "Program kaldırıldı."
    if [ -d "$VERI" ]; then
        if [ "$VERILERI_SIL" = 1 ] || { [ "$EVET" = 0 ] && evet_mi "  Ayarlar ve sesler de silinsin mi? (geri alınamaz)" H; }; then
            rm -rf "$VERI" && iyi "Ayarlar ve sesler silindi."
        else
            bilgi "Ayarlar ve sesler duruyor: $VERI (yeniden kurulursa kaldığı yerden devam eder)."
        fi
    fi
}

case "$ISLEM" in
    kur) kur ;;
    kaldir) kaldir ;;
    denetle) sistemi_denetle; mevcut_kurulum; paket_oner ;;
esac
