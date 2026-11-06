## Okul Zili – okullar için otomatik zil programı

### İndirme
| Dosya | Ne için? |
|---|---|
| **OkulZili-Kurulum-….exe** | **Önerilen.** Programı bilgisayara kurar, Başlat menüsüne ve isteğe bağlı masaüstüne kısayol ekler, bilgisayar açılınca otomatik başlatabilir. Denetim Masası'ndan kaldırılabilir. |
| OkulZili-Tasinabilir-….exe | Kurulum gerektirmez; çift tıklayınca çalışır (USB bellekten kullanım için). |

### Kurulum
1. **OkulZili-Kurulum-….exe** dosyasını indirip çift tıklayın.
2. Windows «Bilinmeyen yayımcı / Windows bilgisayarınızı korudu» uyarısı gösterirse **«Ek bilgi» → «Yine de çalıştır»** seçin.
   (Program dijital olarak imzalanmadığı için bu uyarı normaldir.)
3. Kurulumda **«Bilgisayar açılınca Okul Zili otomatik başlasın»** seçeneğini işaretli bırakın.
4. Program ilk açılışta okulun adını, türünü ve ders saatlerini sorar; ardından ayar düzeyini seçersiniz
   (emin değilseniz **«Basit»**).

### Zil seslerini ekleyin (ilk kurulumda)
Program kendi zil sesiyle gelmez; sesleri siz seçersiniz:
1. Ana ekrandaki **«🎵 Kütüphane»** düğmesine basın.
2. YouTube'daki şarkının / zil sesinin bağlantısını yapıştırıp **«İndir»**e basın
   (ya da **«Bilgisayardan ekle…»** ile USB bellekteki bir dosyayı seçin).
3. İndirme bitince çıkan **Öğrenci Zili / Öğretmen Zili / Çıkış Zili** düğmelerinden birine basın.

Şarkının yalnızca bir kısmını istiyorsanız «Yalnızca bir bölümünü indir» kutusunu işaretleyip başlangıç ve
bitişi yazın (ör. 5:30 – 5:35).

Her hafta (ya da her gün / her ay) farklı bir şarkı çalması için Ayarlar → Zil Sesleri'nde
**«🔀 Ses düzenli olarak değişsin»** seçeneğini açıp kütüphaneden birden fazla ses işaretleyin.

Ses seçilmemiş zil sessiz kalmaz, Windows uyarı sesi çalar; ana ekranda sarı uyarı görünür.
Oynatma listesi bağlantısı yapıştırılırsa program iki kez uyarır.

### Bu sürümde yeni (1.4.0)
- **Tören düğmeleri:** Ana ekranda **«İstiklal Marşı»** ve **«Saygı Duruşu + İstiklal Marşı»**. İlk basışta ses
  internetten bir kez indirilir; sonra internet gerekmez.
- Tören sürerken ziller çalmaz; zamanı gelen zil tören bitince birkaç saniye sonra çalar. Başlatmadan önce sorulur,
  çalarken düğme kalan süreyi gösterir ve «Durdur» olur. Elle zil ya da anons törenin üstüne binmez (önce sorulur).
- Tören sesleri olduğu gibi kaydedilir: saygı duruşunun sessiz dakikası kırpılmaz.
- Ayarlar → Zil Sesleri → **Tören Sesleri**: ses seçimi, ses düzeyi, yeniden indirme.
- Uyarı şeridi varken 1080p ekranda «Sustur» düğmesinin yarısı görünmüyordu; düzeltildi.

### 1.3.0
- **Her okul için:** İlk açılışta kurulum sihirbazı (okul adı, okul türü, tekli/ikili öğretim, ders saatleri).
- **İkili öğretim:** Sabahçı ve öğlenci gruplarının kendi ders saatleri; iki grubun zilleri art arda çalar.
- **Bugün kısaltılmış ders** düğmesi: yalnızca bugün için ders süreleri kısalır, yarın normale döner.
- **MEB takvimi internetten:** Yeni eğitim yılının takvimi açıklanınca tatiller kendiliğinden güncellenir.
- **Ders saatlerini paylaşma:** Ders saatleri dosyaya kaydedilip başka okula verilebilir; kurulumda yüklenebilir.
- «Hakkında» penceresi (geliştirici: GoldenMan0_0 · @PrintGoldenMan), «Sorun bildir» bağlantısı, MIT lisansı.

### 1.2.0
- Pencere kapatılınca program saatin yanındaki simgede çalışmaya devam eder; beklenmedik kapanmada kendiliğinden açılır.
- Okul saatlerinde bilgisayar uykuya geçmez. Windows sesi kapalıysa ya da saat yanlışsa uyarı verilir.
- «Güncelleme var» düğmesiyle program kendini günceller.
- Tam yedek (ayarlar + sesler), MEB 2026-2027 çalışma takvimi, yarım günlük tatiller.
- Kütüphanede her ses için zilde çalınacak bölüm; ek zillerde «sonuna kadar çal» (İstiklal Marşı için).

### Önemli
- Zil bilgisayarında **uyku modunu kapatın**. Program yalnızca açıkken zil çalar.
- Hoparlörün bağlı ve sesin açık olduğundan emin olun; Ayarlar → Zil Sesleri → «Dinle» ile deneyin.
- YouTube'dan indirme durursa Kütüphane penceresindeki **«yt-dlp'yi güncelle»** düğmesine basıp programı yeniden açın.
