"""MCP registration for set_message_pinned."""
from local_chat.catalog import register_tool


def register(mcp, store):
    register_tool(mcp, store, "set_message_pinned")
