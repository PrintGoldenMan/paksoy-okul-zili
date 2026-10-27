"""Türkçe gün, ay ve sıra sayısı yardımcıları."""

DAYS = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
MONTHS = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz",
          "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
_ORDINALS = ["sıfırıncı", "birinci", "ikinci", "üçüncü", "dördüncü", "beşinci", "altıncı",
             "yedinci", "sekizinci", "dokuzuncu", "onuncu", "on birinci", "on ikinci"]


def ordinal_word(n: int) -> str:
    return _ORDINALS[n] if 0 <= n < len(_ORDINALS) else f"{n}."


def long_date(d) -> str:
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}, {DAYS[d.weekday()]}"


def capitalize_first(text: str) -> str:
    """Türkçe kurallarıyla ilk harfi büyütür (i -> İ, ı -> I)."""
    if not text:
        return text
    first = {"i": "İ", "ı": "I"}.get(text[0], text[0].upper())
    return first + text[1:]
