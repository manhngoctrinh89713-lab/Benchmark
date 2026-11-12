"""MCP registration for delete_messages."""
from local_chat.catalog import register_tool


def register(mcp, store):
    register_tool(mcp, store, "delete_messages")
