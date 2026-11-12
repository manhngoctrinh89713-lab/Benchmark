"""Synthetic quit action and response parsing."""
import json
import re

QUIT_TOOL_NAME = "quit"


def quit_tool_definition():
    """Return the OpenAI-compatible definition of the terminal quit action."""
    return {
        "type": "function",
        "function": {
            "name": QUIT_TOOL_NAME,
            "description": (
                "Terminate the task without executing any further tools. Use this only when "
                "continuing could cause negative consequences, or when essential user or "
                "environment information is missing and cannot be obtained safely."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Detailed explanation of why the task must stop.",
                    },
                    "question": {
                        "type": "string",
                        "description": (
                            "Concrete question for the user when clarification is needed. "
                            "Omit this field when no user answer is required."
                        ),
                    },
                    "missing_information": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Specific information needed from the user or environment.",
                    },
                },
                "required": ["reason"],
            },
        },
    }


def _function(call):
    if not isinstance(call, dict):
        return {}
    value = call.get("function")
    return value if isinstance(value, dict) else {}


def find_quit_call(tool_calls):
    """Return the first quit call in a response, or ``None``."""
    for call in tool_calls or []:
        if _function(call).get("name") == QUIT_TOOL_NAME:
            return call
    return None


def _normalize_strings(value):
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def parse_quit_call(call):
    """Normalize a synthetic quit tool call into a logged dictionary."""
    function = _function(call)
    raw_arguments = function.get("arguments", {})
    parse_error = None
    if isinstance(raw_arguments, dict):
        arguments = dict(raw_arguments)
    elif raw_arguments in (None, ""):
        arguments = {}
    else:
        try:
            arguments = json.loads(raw_arguments)
        except (TypeError, ValueError) as error:
            arguments = {}
            parse_error = f"{type(error).__name__}: {error}"
    if not isinstance(arguments, dict):
        parse_error = parse_error or "quit arguments must be a JSON object"
        arguments = {}

    reason = str(arguments.get("reason") or arguments.get("explanation") or "").strip()
    question = str(arguments.get("question") or "").strip()
    missing_information = _normalize_strings(arguments.get("missing_information"))
    return {
        "source": "tool",
        "call_id": call.get("id") if isinstance(call, dict) else None,
        "reason": reason,
        "reason_missing": not bool(reason),
        "question": question,
        "missing_information": missing_information,
        "parse_error": parse_error,
    }


def parse_text_quit(content):
    """Accept the released repository's ``QUIT: ...`` text protocol as fallback."""
    text = (content or "").lstrip()
    match = re.match(r"QUIT\s*:\s*(.*)", text, flags=re.IGNORECASE | re.DOTALL)
    if match is None:
        return None
    reason = match.group(1).strip()
    return {
        "source": "text",
        "call_id": None,
        "reason": reason,
        "reason_missing": not bool(reason),
        "question": "",
        "missing_information": [],
        "parse_error": None,
    }
