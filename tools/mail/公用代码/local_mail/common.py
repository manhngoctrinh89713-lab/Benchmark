"""Shared validation and query primitives for mail resources."""
from datetime import datetime
import re
from uuid import uuid4


def date(value):
    if not isinstance(value, str):
        raise ValueError("Dates must be ISO8601 strings")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Dates must include a timezone")
    return result


def text(value, name="value", empty=False):
    if not isinstance(value, str) or (not empty and not value.strip()):
        raise ValueError(f"{name} must be a string" + ("" if empty else " and nonempty"))
    return value


def addresses(values):
    if not isinstance(values, list):
        raise ValueError("Addresses must be a list")
    for value in values:
        if not isinstance(value, str) or not re.fullmatch(r"[^\s@<>;,]+@[^\s@<>;,]+\.[^\s@<>;,]+", value):
            raise ValueError(f"Invalid bare email address: {value}")
    return values


def unique(values):
    seen = set()
    result = []
    for value in values:
        key = value.casefold()
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result


def identifier(prefix):
    return prefix + "-" + uuid4().hex


def page(items, offset=0, limit=20):
    if type(offset) is not int or type(limit) is not int or offset < 0 or not 1 <= limit <= 100:
        raise ValueError("offset >= 0; 1 <= limit <= 100")
    end = offset + limit
    return {"items": items[offset:end], "total": len(items),
            "next_offset": end if end < len(items) else None}


def check_version(obj, expected):
    if expected is not None and obj.get("version", 1) != expected:
        raise ValueError("Object changed; read its current version")


def touch(obj, now):
    obj["version"] = obj.get("version", 1) + 1
    obj["updated_at"] = now


FILTER_FIELDS = {"subject", "body", "from", "to", "cc", "bcc", "timestamp", "is_read",
                 "starred", "mailbox", "categories", "has_attachment", "attachment_name",
                 "size", "thread_id", "importance"}
FILTER_OPS = {"eq", "contains", "in", "lt", "lte", "gt", "gte", "exists"}


def validate_filters(conditions):
    if not isinstance(conditions, list) or len(conditions) > 30:
        raise ValueError("Use at most 30 conditions")
    for condition in conditions:
        if not isinstance(condition, dict) or set(condition) - {"field", "op", "value"}:
            raise ValueError("Condition requires field, op and value")
        if condition.get("field") not in FILTER_FIELDS or condition.get("op") not in FILTER_OPS:
            raise ValueError("Unsupported condition field or operator")
        if "value" not in condition:
            raise ValueError("Condition requires a value")
        op, value = condition["op"], condition["value"]
        if op == "in" and not isinstance(value, list):
            raise ValueError("in requires a list")
        if op == "exists" and type(value) is not bool:
            raise ValueError("exists requires a boolean")
        if op == "contains" and not isinstance(value, str):
            raise ValueError("contains requires a string")
        if op == "eq" and isinstance(value, (list, dict)):
            raise ValueError("eq requires one scalar value")
        if op in {"eq", "in"}:
            values = value if op == "in" else [value]
            field = condition["field"]
            if field in {"is_read", "starred", "has_attachment"} and any(type(v) is not bool for v in values):
                raise ValueError("Boolean fields require boolean values")
            if field == "size" and any(type(v) is not int or v < 0 for v in values):
                raise ValueError("size requires nonnegative integers")
            if field == "timestamp":
                for v in values:
                    date(v)
        if op in {"lt", "lte", "gt", "gte"}:
            if condition["field"] not in {"size", "timestamp"}:
                raise ValueError("Ordering conditions support size or timestamp")
            if condition["field"] == "timestamp":
                date(value)
            elif type(value) is not int or value < 0:
                raise ValueError("size requires a nonnegative integer")


def field_value(message, field):
    if field == "has_attachment":
        return bool(message.get("attachments"))
    if field == "attachment_name":
        return [a["name"] for a in message.get("attachments", [])]
    if field == "size":
        return len(message.get("body", "").encode()) + sum(a["size"] for a in message.get("attachments", []))
    return message.get(field)


def matches(message, conditions, match="all"):
    if match not in {"all", "any"}:
        raise ValueError("match must be all or any")
    if not conditions:
        return True
    def compare(condition):
        actual, expected, op = field_value(message, condition["field"]), condition["value"], condition["op"]
        if op == "exists":
            return (actual is not None and actual != [] and actual != "") == expected
        if op in {"lt", "lte", "gt", "gte"}:
            if actual is None:
                return False
            if condition["field"] == "timestamp":
                actual, expected = date(actual), date(expected)
            return {"lt": actual < expected, "lte": actual <= expected,
                    "gt": actual > expected, "gte": actual >= expected}[op]
        values = actual if isinstance(actual, list) else [actual]
        normalize = lambda v: v.casefold() if isinstance(v, str) else v
        if op == "eq":
            if condition["field"] == "timestamp":
                return date(actual) == date(expected)
            return any(normalize(v) == normalize(expected) for v in values)
        if op == "contains":
            return any(isinstance(v, str) and str(expected).casefold() in v.casefold() for v in values)
        if condition["field"] == "timestamp":
            return any(date(actual) == date(v) for v in expected)
        return any(normalize(v) in [normalize(e) for e in expected] for v in values)
    return (all if match == "all" else any)(compare(c) for c in conditions)
