"""Time helpers (UTC storage, local display, human durations in RU/UZ)."""
from __future__ import annotations

import datetime as dt
import re
import time

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore


def now() -> int:
    return int(time.time())


def today(ts: int | None = None) -> str:
    return dt.datetime.fromtimestamp(ts if ts is not None else time.time(), dt.timezone.utc).strftime("%Y-%m-%d")


def tz(name: str):
    if ZoneInfo is None:
        return dt.timezone.utc
    try:
        return ZoneInfo(name)
    except Exception:
        return dt.timezone.utc


def local_dt(ts: int | float | None = None, tz_name: str = "Asia/Tashkent") -> dt.datetime:
    return dt.datetime.fromtimestamp(ts if ts is not None else time.time(), tz(tz_name))


def fmt_dt(ts: int | None, tz_name: str = "Asia/Tashkent", with_date: bool = True) -> str:
    if not ts:
        return "—"
    d = local_dt(ts, tz_name)
    return d.strftime("%d.%m.%Y %H:%M") if with_date else d.strftime("%H:%M")


def _plural_ru(n: int, one: str, few: str, many: str) -> str:
    n = abs(n)
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def plural_form(n: int) -> str:
    """CLDR-style plural category for Russian (``one``/``few``/``many``); Uzbek catalogs use the same text for all."""
    return _plural_ru(n, "one", "few", "many")


def human_duration(seconds: int | float, lang: str = "ru", max_parts: int = 2) -> str:
    from ..localization import tr
    s = int(max(0, seconds))
    days, s = divmod(s, 86400)
    hours, s = divmod(s, 3600)
    minutes, secs = divmod(s, 60)
    parts = [tr(lang, f"time.{unit}.{plural_form(v)}", n=v)
             for v, unit in ((days, "day"), (hours, "hour"), (minutes, "minute"), (secs, "second")) if v]
    if not parts:
        return tr(lang, "time.under_second")
    return " ".join(parts[:max_parts])


_DUR_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(д|d|day|days|дн|дней|дня|kun|ч|h|hr|hour|hours|час|часа|часов|soat|"
                     r"м|m|min|mins|minute|minutes|мин|минут|минуты|daqiqa|с|s|sec|secs|second|seconds|сек|секунд|soniya)?",
                     re.IGNORECASE)
_UNIT = {
    "д": 86400, "d": 86400, "day": 86400, "days": 86400, "дн": 86400, "дней": 86400, "дня": 86400, "kun": 86400,
    "ч": 3600, "h": 3600, "hr": 3600, "hour": 3600, "hours": 3600, "час": 3600, "часа": 3600, "часов": 3600, "soat": 3600,
    "м": 60, "m": 60, "min": 60, "mins": 60, "minute": 60, "minutes": 60, "мин": 60, "минут": 60, "минуты": 60, "daqiqa": 60,
    "с": 1, "s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1, "сек": 1, "секунд": 1, "soniya": 1,
}


def parse_duration(text: str, default_unit: int = 60) -> int | None:
    """Parse '1h30m', '90', '2 часа', '45s', '1.5h' -> seconds. Returns None if nothing parsed."""
    if not text:
        return None
    text = text.strip().lower().replace(" ", "")
    if not text:
        return None
    total = 0.0
    pos = 0
    matched = False
    for m in _DUR_RE.finditer(text):
        if m.start() != pos:
            return None
        pos = m.end()
        if not m.group(0):
            continue
        val = float(m.group(1).replace(",", "."))
        unit = (m.group(2) or "").lower()
        total += val * (_UNIT.get(unit, default_unit) if unit else default_unit)
        matched = True
    if pos != len(text) or not matched:
        return None
    return int(total)


def parse_hhmm(text: str) -> tuple[int, int] | None:
    m = re.fullmatch(r"\s*(\d{1,2})[:.](\d{2})\s*", text or "")
    if not m:
        m2 = re.fullmatch(r"\s*(\d{1,2})\s*", text or "")
        if not m2:
            return None
        h, mi = int(m2.group(1)), 0
    else:
        h, mi = int(m.group(1)), int(m.group(2))
    if 0 <= h <= 23 and 0 <= mi <= 59:
        return h, mi
    return None


def next_occurrence(hour: int, minute: int, tz_name: str, now_ts: int | None = None) -> int:
    base = local_dt(now_ts, tz_name)
    target = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= base:
        target += dt.timedelta(days=1)
    return int(target.timestamp())


def in_time_window(start: str, end: str, tz_name: str, ts: int | None = None) -> bool:
    """True if local time is within [start, end) — supports windows crossing midnight."""
    s, e = parse_hhmm(start), parse_hhmm(end)
    if not s or not e:
        return False
    d = local_dt(ts, tz_name)
    cur = d.hour * 60 + d.minute
    a, b = s[0] * 60 + s[1], e[0] * 60 + e[1]
    if a == b:
        return True
    if a < b:
        return a <= cur < b
    return cur >= a or cur < b


def day_part(tz_name: str, ts: int | None = None) -> str:
    h = local_dt(ts, tz_name).hour
    if 5 <= h < 12:
        return "morning"
    if 12 <= h < 18:
        return "day"
    if 18 <= h < 23:
        return "evening"
    return "night"
