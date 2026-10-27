"""MEB çalışma takvimi: eğitim yılının tatilleri (tek tıkla «Tatiller» listesine eklenir).

Kaynak: Millî Eğitim Bakanlığı, «2026-2027 Eğitim Öğretim Yılı Takvimi Açıklandı»
(https://www.meb.gov.tr/2026-2027-egitim-ogretim-yili-takvimi-aciklandi/haber/41057/tr) ve
Diyanet takvimine göre dinî bayramlar. Yeni eğitim yılının takvimi açıklandığında buraya eklenir
ve programın güncellemesiyle okullara ulaşır.

"from": yarım günlük tatillerde zillerin susacağı saat (ör. 28 Ekim öğleden sonra).
"""

import datetime as dt

CALENDARS = {
    "2026-2027": {
        "first_day": "2026-09-14",
        "last_day": "2027-06-25",
        "holidays": [
            {"name": "Cumhuriyet Bayramı arifesi (öğleden sonra)", "start": "2026-10-28", "end": "2026-10-28",
             "from": "13:00"},
            {"name": "Cumhuriyet Bayramı", "start": "2026-10-29", "end": "2026-10-29"},
            {"name": "Birinci dönem ara tatili", "start": "2026-11-16", "end": "2026-11-20"},
            {"name": "Yılbaşı", "start": "2027-01-01", "end": "2027-01-01"},
            {"name": "Yarıyıl tatili", "start": "2027-01-25", "end": "2027-02-05"},
            {"name": "İkinci dönem ara tatili ve Ramazan Bayramı", "start": "2027-03-08", "end": "2027-03-12"},
            {"name": "Ulusal Egemenlik ve Çocuk Bayramı", "start": "2027-04-23", "end": "2027-04-23"},
            {"name": "Kurban Bayramı ve 19 Mayıs", "start": "2027-05-17", "end": "2027-05-19"},
            # Bir sonraki yılın açılış tarihi henüz belli değil; yeni takvim eklenince güncellenir.
            {"name": "Yaz tatili", "start": "2027-06-26", "end": "2027-08-31"},
        ],
    },
}


def school_year(date: dt.date) -> str:
    """Tarihin içinde bulunduğu eğitim yılı, ör. 2026-10-27 → «2026-2027» (yaz ayları bir sonrakine sayılır)."""
    start = date.year if date.month >= 7 else date.year - 1
    return f"{start}-{start + 1}"


def calendar_for(date: dt.date):
    return CALENDARS.get(school_year(date))
