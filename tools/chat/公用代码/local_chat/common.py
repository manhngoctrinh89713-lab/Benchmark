"""Validation and stable resource helpers for local chat."""
from datetime import datetime
from uuid import uuid4


def date(value):
    if not isinstance(value, str):
        raise ValueError("Time must be an ISO8601 string")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Time must include a timezone")
    return result


def text(value, field="text", empty=False):
    if not isinstance(value, str) or (not empty and not value.strip()):
        raise ValueError(field + " must be a " + ("nonempty " if not empty else "") + "string")
    if len(value.encode()) > 1024 * 1024:
        raise ValueError(field + " exceeds 1 MiB")
    return value


def ident(prefix):
    return prefix + "_" + uuid4().hex


def page(items, offset=0, limit=20):
    if type(offset) is not int or type(limit) is not int or offset < 0 or not 1 <= limit <= 100:
        raise ValueError("offset >= 0; limit 1..100")
    end = offset + limit
    return {"items": items[offset:end], "total": len(items), "next_offset": end if end < len(items) else None}


def version(obj, expected):
    if expected is not None and obj.get("version", 1) != expected:
        raise ValueError("Object changed; read its current version")


def touch(obj, now):
    obj["version"] = obj.get("version", 1) + 1
    obj["updated_at"] = now


def ids(values, maximum=100):
    if not values or len(values) > maximum or len(set(values)) != len(values):
        raise ValueError(f"Provide 1..{maximum} unique IDs")
    return values
