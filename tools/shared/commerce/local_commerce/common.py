"""Bounded money, time and resource primitives for commerce."""
import calendar
import copy
from datetime import datetime, timedelta

def integer(value, minimum=0, maximum=10**12):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"Expected integer in {minimum}..{maximum}")
    return value


def text(value, maximum=2000):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or "\x00" in value:
        raise ValueError(f"Expected nonempty text up to {maximum} characters")
    return value


def moment(value):
    if not isinstance(value, str):
        raise ValueError("Time must be an ISO-8601 string with timezone")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Time must include timezone")
    return result


def page(items, offset=0, limit=20):
    integer(offset, 0, 100000); integer(limit, 1, 100)
    return {"items": copy.deepcopy(items[offset:offset+limit]), "total": len(items), "next_offset": offset+limit if offset+limit < len(items) else None}


def period_end(start, unit, count, anchor_day=None):
    dt = moment(start)
    integer(count, 1, 12)
    if unit in ("day", "week"):
        return (dt + timedelta(days=count*(7 if unit == "week" else 1))).isoformat()
    if unit not in ("month", "year"):
        raise ValueError("interval must be day/week/month/year")
    month = dt.year*12 + dt.month-1 + count*(12 if unit == "year" else 1)
    year, m = divmod(month, 12); m += 1
    return dt.replace(year=year, month=m, day=min(anchor_day or dt.day, calendar.monthrange(year,m)[1])).isoformat()


def version(obj, expected):
    if expected is not None and obj.get("version", 1) != expected:
        raise ValueError("Object changed; read its current version")


def touch(obj, now):
    obj["version"] = obj.get("version", 1) + 1
    obj["updated_at"] = now
