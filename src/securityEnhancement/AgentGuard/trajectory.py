"""Bounded recent-event projection for the LLM reviewer.

The benchmark runner writes an append-only JSONL event feed for each run:

* ``llm_input``   – the messages sent to the model for a step
* ``llm_output``  – the assistant message (content and tool calls)
* ``tool_invoke`` – a tool call with its classified capabilities
* ``tool_result`` – the observed tool result

The MCP worker reads the feed before each Guard decision and sends the last
``AGENTGUARD_REVIEW_TRACE_MAX_STEPS`` events to the Guard server, mirroring the
``Recent Events`` block of the upstream reviewer prompt.  If no feed is
available (for example when the Guard client is used outside the runner), a
synthetic ``llm_input`` event carrying ``AGENTGUARD_USER_INSTRUCTION`` is used
instead.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from . import config
from .audit import sanitize
from .metadata import classify

EVENT_CONTENT_MAX_CHARS = 400
EVENT_SANITIZE_MAX_ITEMS = 10_000


def _truncate(value: Any, limit: int = EVENT_CONTENT_MAX_CHARS) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        try:
            value = json.dumps(value, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            value = str(value)
    if len(value) <= limit:
        return value
    return value[: max(limit - 3, 0)] + "..."


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") in {"text", "input_text", "output_text"}:
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)
    if content is None:
        return ""
    return _truncate(content, EVENT_CONTENT_MAX_CHARS * 4)


def _tool_calls(value: Any) -> list[dict[str, Any]]:
    projected: list[dict[str, Any]] = []
    if not isinstance(value, list):
        return projected
    for item in value:
        if not isinstance(item, dict):
            continue
        function = item.get("function") if isinstance(item.get("function"), dict) else {}
        name = function.get("name") or item.get("name")
        arguments = function.get("arguments")
        if arguments is None:
            arguments = item.get("args")
        projected.append(
            {
                "name": str(name or ""),
                "args": _truncate(arguments, EVENT_CONTENT_MAX_CHARS),
            }
        )
    return projected


def project_message(message: Any) -> dict[str, Any]:
    if not isinstance(message, dict):
        return {"role": "unknown", "content": _truncate(message)}
    role = str(message.get("role") or message.get("type") or "unknown").strip().lower()
    # Keep the task instruction readable; other message types use the upstream
    # 400-character projection.
    limit = config.MAX_USER_INSTRUCTION_CHARS if role == "user" else EVENT_CONTENT_MAX_CHARS
    projected: dict[str, Any] = {
        "role": role,
        "content": _truncate(_content_text(message.get("content")), limit),
    }
    calls = _tool_calls(message.get("tool_calls"))
    if calls:
        projected["tool_calls"] = calls
    return projected


def llm_input_event(messages: list[Any]) -> dict[str, Any]:
    # The model request always carries the full conversation, so the original
    # user message is naturally present in every llm_input event.
    return {
        "event_type": "llm_input",
        "messages": [project_message(message) for message in messages],
    }


def llm_output_event(message: Any) -> dict[str, Any]:
    if not isinstance(message, dict):
        return {"event_type": "llm_output", "content": _truncate(message)}
    event: dict[str, Any] = {"event_type": "llm_output"}
    content = _truncate(_content_text(message.get("content")))
    if content:
        event["content"] = content
    calls = _tool_calls(message.get("tool_calls"))
    if calls:
        event["tool_calls"] = calls
    return event


def tool_invoke_event(
    tool_name: str,
    arguments: dict[str, Any],
    *,
    description: str = "",
    input_schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    group = tool_name.split("__", 1)[0] if "__" in tool_name else ""
    metadata = classify(group, tool_name, description, input_schema or {})
    return {
        "event_type": "tool_invoke",
        "tool_name": tool_name,
        "arguments": sanitize(arguments, max_depth=4, max_str=EVENT_CONTENT_MAX_CHARS, max_items=20),
        "capabilities": list(metadata.capabilities),
        "side_effect": metadata.side_effect,
        "risk_level": metadata.risk_level,
    }


def _result_text(output: Any) -> str:
    if isinstance(output, dict):
        content = output.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict) and isinstance(block.get("text"), str):
                    parts.append(block["text"])
            if parts:
                return "\n".join(parts)
        structured = output.get("structuredContent")
        if structured is not None:
            return _truncate(structured, EVENT_CONTENT_MAX_CHARS * 4)
        try:
            return json.dumps(output, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            return str(output)
    return str(output or "")


def tool_result_event(tool_name: str, output: Any) -> dict[str, Any]:
    event: dict[str, Any] = {
        "event_type": "tool_result",
        "tool_name": tool_name,
        "result": _truncate(_result_text(output)),
    }
    if isinstance(output, dict) and output.get("isError"):
        event["is_error"] = True
    return event


def append_event(path: str | Path, event: dict[str, Any]) -> bool:
    """Append one event; never let reviewer telemetry break the benchmark."""
    try:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp": datetime.now().astimezone().isoformat(),
            **sanitize(
                event,
                max_depth=8,
                max_str=config.MAX_USER_INSTRUCTION_CHARS,
                max_items=EVENT_SANITIZE_MAX_ITEMS,
            ),
        }
        with target.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        return True
    except Exception:  # noqa: BLE001 - telemetry must not affect the run
        return False


def append_llm_input(path: str | Path, messages: list[Any]) -> bool:
    return append_event(path, llm_input_event(messages))


def append_llm_output(path: str | Path, message: Any) -> bool:
    return append_event(path, llm_output_event(message))


def append_tool_events(
    path: str | Path,
    tool_name: str,
    arguments: dict[str, Any],
    output: Any,
    *,
    description: str = "",
    input_schema: dict[str, Any] | None = None,
) -> bool:
    invoke = append_event(path, tool_invoke_event(tool_name, arguments, description=description,
                                                  input_schema=input_schema))
    result = append_event(path, tool_result_event(tool_name, output))
    return bool(invoke or result)


def load_events(path: str | Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    events: list[dict[str, Any]] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue  # a partially written trailing line is expected
        if isinstance(event, dict) and event.get("event_type"):
            events.append(event)
    return events


def recent_events(max_events: int | None = None) -> list[dict[str, Any]]:
    """Return the bounded Recent Events list sent to the reviewer."""
    limit = max_events if max_events is not None else config.review_trace_max_steps()
    events = load_events(config.event_feed_path())
    if events:
        selected = events[-max(limit, 1):]
        return sanitize(
            selected,
            max_depth=8,
            max_str=config.MAX_USER_INSTRUCTION_CHARS,
            max_items=EVENT_SANITIZE_MAX_ITEMS,
        )
    instruction = config.user_instruction()
    if instruction:
        return [
            {
                "event_type": "llm_input",
                "messages": [{"role": "user", "content": instruction}],
            }
        ]
    return []
