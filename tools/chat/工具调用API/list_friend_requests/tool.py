"""MCP registration for list_friend_requests."""
from local_chat.catalog import register_tool


def register(mcp, store):
    register_tool(mcp, store, "list_friend_requests")
