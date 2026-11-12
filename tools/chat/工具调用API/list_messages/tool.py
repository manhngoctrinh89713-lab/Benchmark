"""MCP registration for list_messages."""
from local_chat.catalog import register_tool


def register(mcp, store):
    register_tool(mcp, store, "list_messages")
