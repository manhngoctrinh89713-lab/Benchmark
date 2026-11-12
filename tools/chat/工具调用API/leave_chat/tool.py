"""MCP registration for leave_chat."""
from local_chat.catalog import register_tool


def register(mcp, store):
    register_tool(mcp, store, "leave_chat")
