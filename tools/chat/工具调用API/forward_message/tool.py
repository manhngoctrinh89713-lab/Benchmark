"""MCP registration for forward_message."""
from local_chat.catalog import register_tool


def register(mcp, store):
    register_tool(mcp, store, "forward_message")
