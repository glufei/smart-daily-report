from datetime import date


def is_workday(day: date, holidays: set[date]) -> bool:
    return day.weekday() < 5 and day not in holidays
