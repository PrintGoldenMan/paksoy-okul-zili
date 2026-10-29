"""Kurulum sihirbazındaki okul türü şablonları (başlangıç değerleridir; okul kendi saatlerine göre değiştirir)."""

SCHOOL_TYPES = {
    "ilkokul": "İlkokul",
    "ortaokul": "Ortaokul",
    "lise": "Lise",
    "anaokulu": "Anaokulu",
}

# Tekli öğretim: tek grup, öğle arası var
SINGLE = {
    "ilkokul": {"first_lesson": "08:30", "lesson_count": 6, "lesson_minutes": 40, "break_minutes": 10,
                "lunch_after": 4, "lunch_minutes": 40},
    "ortaokul": {"first_lesson": "08:30", "lesson_count": 7, "lesson_minutes": 40, "break_minutes": 10,
                 "lunch_after": 4, "lunch_minutes": 40},
    "lise": {"first_lesson": "08:30", "lesson_count": 8, "lesson_minutes": 40, "break_minutes": 10,
             "lunch_after": 5, "lunch_minutes": 40},
    "anaokulu": {"first_lesson": "09:00", "lesson_count": 5, "lesson_minutes": 30, "break_minutes": 10,
                 "lunch_after": 3, "lunch_minutes": 30},
}

# İkili öğretim: sabahçı ve öğlenci, genellikle öğle arası yok
DOUBLE_MORNING = {"first_lesson": "07:40", "lesson_count": 6, "lesson_minutes": 40, "break_minutes": 10,
                  "lunch_after": 0, "lunch_minutes": 0}
DOUBLE_AFTERNOON = {"first_lesson": "12:50", "lesson_count": 6, "lesson_minutes": 40, "break_minutes": 10,
                    "lunch_after": 0, "lunch_minutes": 0}


def timing_for(school_type: str, double: bool):
    """(sabahçı / tek grup zamanlaması, öğlenci zamanlaması ya da None)"""
    if double:
        return dict(DOUBLE_MORNING), dict(DOUBLE_AFTERNOON)
    return dict(SINGLE.get(school_type, SINGLE["lise"])), None
