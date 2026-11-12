"""MCP registration for read_message."""
from local_chat.catalog import register_tool


def register(mcp, store):
    register_tool(mcp, store, "read_message")
