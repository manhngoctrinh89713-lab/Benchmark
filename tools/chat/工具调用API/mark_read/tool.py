"""MCP registration for mark_read."""
from local_chat.catalog import register_tool


def register(mcp, store):
    register_tool(mcp, store, "mark_read")
