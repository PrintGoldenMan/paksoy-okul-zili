# Hazır Zil Sesleri

Okul Zili programının içinde gelen 8 hazır zil sesi. Program bu sesleri kendisi üretir;
buradaki dosyalar başka bir zil sisteminde, telefonda ya da bilgisayarda kullanmak içindir.
Hepsi WAV (16 bit, mono, 22050 Hz) biçimindedir; çoğu oynatıcı ve zil cihazı açabilir.

| Dosya | Ses | Süre | Programdaki varsayılan kullanımı |
|---|---|---|---|
| [01_klasik_okul_zili.wav](01_klasik_okul_zili.wav) | Klasik Okul Zili (elektrikli zil) | 4,8 sn | **Öğretmen zili** |
| [02_ding_dong.wav](02_ding_dong.wav) | Ding-Dong | 5,0 sn | |
| [03_westminster_can_melodisi.wav](03_westminster_can_melodisi.wav) | Westminster Çan Melodisi | 7,3 sn | |
| [04_neseli_melodi.wav](04_neseli_melodi.wav) | Neşeli Melodi | 3,2 sn | **Öğrenci zili** |
| [05_elektronik_zil.wav](05_elektronik_zil.wav) | Elektronik Zil | 3,0 sn | |
| [06_gong.wav](06_gong.wav) | Gong | 6,5 sn | Ek ziller |
| [07_kampana_3_vurus.wav](07_kampana_3_vurus.wav) | Kampana (3 vuruş) | 5,0 sn | **Çıkış zili** |
| [08_kisa_bip.wav](08_kisa_bip.wav) | Kısa Bip | 1,3 sn | |

Programda zil, ayarlanan çalma süresi boyunca çalar (varsayılan 3,5 sn): ses daha kısaysa
tekrarlanır, daha uzunsa süre dolunca yumuşakça kısılır.

Sesler `okul_zili/sounds.py` dosyasında değiştirilirse bu klasör şu komutla yenilenebilir:

```
python tools/sesleri_disari_aktar.py
```
