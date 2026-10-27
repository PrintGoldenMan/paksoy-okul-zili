"""Türkçe gün, ay ve sıra sayısı yardımcıları."""

DAYS = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
MONTHS = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz",
          "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
_ONES = ["", "bir", "iki", "üç", "dört", "beş", "altı", "yedi", "sekiz", "dokuz"]
_TENS = ["", "on", "yirmi", "otuz", "kırk", "elli", "altmış", "yetmiş", "seksen", "doksan"]
# Sıra sayısı eki, sayının son sözcüğüne göre (ünlü uyumu ve ünsüz yumuşaması dahil)
_ORDINAL_OF = {"bir": "birinci", "iki": "ikinci", "üç": "üçüncü", "dört": "dördüncü", "beş": "beşinci",
               "altı": "altıncı", "yedi": "yedinci", "sekiz": "sekizinci", "dokuz": "dokuzuncu",
               "on": "onuncu", "yirmi": "yirminci", "otuz": "otuzuncu", "kırk": "kırkıncı", "elli": "ellinci",
               "altmış": "altmışıncı", "yetmiş": "yetmişinci", "seksen": "sekseninci", "doksan": "doksanıncı"}


def ordinal_word(n: int) -> str:
    """1 → «birinci», 13 → «on üçüncü», 40 → «kırkıncı». 1–99 dışında «n.» döner."""
    if not 1 <= n <= 99:
        return f"{n}."
    words = [w for w in (_TENS[n // 10], _ONES[n % 10]) if w]
    words[-1] = _ORDINAL_OF[words[-1]]
    return " ".join(words)


def long_date(d) -> str:
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}, {DAYS[d.weekday()]}"


def capitalize_first(text: str) -> str:
    """Türkçe kurallarıyla ilk harfi büyütür (i -> İ, ı -> I)."""
    if not text:
        return text
    first = {"i": "İ", "ı": "I"}.get(text[0], text[0].upper())
    return first + text[1:]
