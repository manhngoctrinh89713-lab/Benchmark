"""Shared pieces for the two-agent benchmark topologies.

A topology here puts a read-only first agent (Planner / Investigator /
Reviewer) before an Executor that has every enabled tool and finishes the task.

"Read-only" is not a hand-written tool list.  It is the deterministic AgentGuard
metadata classification (``side_effect is False``) applied to the live MCP
catalog, so a tool that is added or renamed in ``tools/`` is filtered correctly
here without this package knowing its name.  The same rule the AgentGuard policy
uses for ``*.read``/``allow`` therefore decides what the first agent may call.

The request's ``tools`` array and the callable set are separate: the first
agent's user message lists the read-only names it may call, while its ``tools``
array carries every tool definition so plans and reports can reference real
names and parameters.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from securityEnhancement.AgentGuard.metadata import classify

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"


def load_prompt(name: str) -> str:
    """Return one editable role prompt (``prompts/<name>.md``)."""
    path = PROMPT_DIR / (name + ".md")
    if not path.is_file():
        raise FileNotFoundError("拓扑提示词缺失：" + str(path))
    return path.read_text(encoding="utf-8").strip()


def tool_name(tool: dict[str, Any]) -> str:
    return ((tool.get("function") or {}).get("name")) or ""


def tool_group(name: str) -> str:
    """``files__write_file`` -> ``files``; names without a prefix stay whole."""
    return name.split("__", 1)[0] if "__" in name else ""


def read_only_tool_names(tools: Iterable[dict[str, Any]], catalog_by_name: dict[str, Any]) -> set[str]:
    """Names of the tools a read-only agent may call.

    Tools outside the MCP catalog are control tools (``quit`` is the only one
    today): they change no state, so they stay available in every phase.
    """
    names: set[str] = set()
    for tool in tools:
        name = tool_name(tool)
        if not name:
            continue
        if name not in catalog_by_name:
            names.add(name)
            continue
        if not classify(tool_group(name), name).side_effect:
            names.add(name)
    return names


def select_tools(tools: Iterable[dict[str, Any]], allowed: set[str]) -> list[dict[str, Any]]:
    return [tool for tool in tools if tool_name(tool) in allowed]


def select_catalog(catalog_by_name: dict[str, Any], allowed: set[str]) -> dict[str, Any]:
    return {name: tool for name, tool in catalog_by_name.items() if name in allowed}


def user_task(messages: Iterable[dict[str, Any]]) -> str:
    """The last user message is the task handed to the first agent."""
    for message in reversed(list(messages)):
        if message.get("role") == "user":
            return message.get("content") or ""
    raise ValueError("拓扑输入缺少用户任务")


def render(template: str, **values: str) -> str:
    """Fill ``{name}`` placeholders by replacement, so text may contain braces."""
    for name, value in values.items():
        template = template.replace("{" + name + "}", value)
    return template


def name_list(names: Iterable[str]) -> str:
    """One ``- `name``` line per tool, sorted, for the user message."""
    return "\n".join("- `" + name + "`" for name in sorted(names))
