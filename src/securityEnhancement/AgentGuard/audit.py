"""Append-only audit records for the local Guard server.

Records never contain API keys, benchmark model credentials or a dump of the
process environment.  Tool arguments are redacted and truncated before they are
written to disk.
"""
from __future__ import annotations

import json
import re
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from . import config

_SENSITIVE_KEY = re.compile(
    r"(api[_-]?key|apikey|token|secret|password|passwd|authorization|cookie|credential|private[_-]?key)",
    re.IGNORECASE,
)


def sanitize(
    value: Any,
    depth: int = 0,
    max_depth: int = 6,
    max_str: int | None = 500,
    max_items: int | None = 40,
) -> Any:
    """Return a JSON-safe copy with secrets redacted and values optionally truncated.

    ``max_str=None`` / ``max_items=None`` disable the corresponding truncation
    (the reviewer uses this to keep the complete public tool arguments).
    """
    if depth > max_depth:
        return "[truncated]"
    if isinstance(value, dict):
        result = {}
        for index, (key, item) in enumerate(value.items()):
            if max_items is not None and index >= max_items:
                result["..."] = "[truncated]"
                break
            key_text = str(key)
            if _SENSITIVE_KEY.search(key_text):
                result[key_text] = "[redacted]"
            else:
                result[key_text] = sanitize(item, depth + 1, max_depth, max_str, max_items)
        return result
    if isinstance(value, (list, tuple)):
        items = list(value)
        selected = items if max_items is None else items[:max_items]
        result = [sanitize(item, depth + 1, max_depth, max_str, max_items) for item in selected]
        if max_items is not None and len(items) > max_items:
            result.append("[truncated]")
        return result
    if isinstance(value, str):
        if max_str is not None and len(value) > max_str:
            return value[:max_str] + "...[truncated]"
        return value
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)


def sanitize_arguments(
    arguments: Any,
    *,
    max_depth: int = 4,
    max_str: int | None = 300,
    max_items: int | None = 20,
) -> Any:
    return sanitize(arguments, max_depth=max_depth, max_str=max_str, max_items=max_items)


class AuditLog:
    """One directory per server start with JSONL files per event kind."""

    FILES = {
        "server": "server.jsonl",
        "decisions": "decisions.jsonl",
        "reviews": "reviews.jsonl",
        "errors": "errors.jsonl",
    }

    def __init__(self, directory: str | Path | None = None) -> None:
        base = Path(directory) if directory is not None else config.audit_dir()
        stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
        self.run_dir: Path | None = base / f"{stamp}-{uuid4().hex[:8]}"
        self._lock = threading.Lock()
        try:
            self.run_dir.mkdir(parents=True, exist_ok=True)
        except (OSError, ValueError) as error:  # audit must never break the decision path
            print(f"AgentGuard 审计目录不可用，已跳过审计：{error}", file=sys.stderr)
            self.run_dir = None

    @property
    def enabled(self) -> bool:
        return self.run_dir is not None

    def write(self, kind: str, event: dict[str, Any]) -> None:
        if self.run_dir is None:
            return
        filename = self.FILES.get(kind)
        if filename is None:
            raise ValueError(f"unknown audit kind: {kind}")
        record = {"timestamp": datetime.now().astimezone().isoformat(), **sanitize(event)}
        line = json.dumps(record, ensure_ascii=False, default=str)
        with self._lock:
            try:
                with (self.run_dir / filename).open("a", encoding="utf-8") as stream:
                    stream.write(line + "\n")
            except OSError as error:
                print(f"AgentGuard 审计写入失败：{error}", file=sys.stderr)

    def server(self, event: dict[str, Any]) -> None:
        self.write("server", event)

    def decision(self, event: dict[str, Any]) -> None:
        self.write("decisions", event)

    def review(self, event: dict[str, Any]) -> None:
        self.write("reviews", event)

    def error(self, event: dict[str, Any]) -> None:
        self.write("errors", event)
