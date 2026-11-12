"""Specified Quit integration for the local tool-calling benchmark.

The implementation is intentionally independent from AgentGuard.  Quitting is
an agent-side terminal action that is intercepted before any MCP tool executes.
"""
from .actions import (
    QUIT_TOOL_NAME,
    find_quit_call,
    parse_quit_call,
    parse_text_quit,
    quit_tool_definition,
)
from .prompts import SPECIFIED_QUIT_PROMPT, build_specified_quit_prompt

__all__ = [
    "QUIT_TOOL_NAME",
    "SPECIFIED_QUIT_PROMPT",
    "build_specified_quit_prompt",
    "find_quit_call",
    "parse_quit_call",
    "parse_text_quit",
    "quit_tool_definition",
]
