"""MCP registration for respond_friend_request."""
from local_chat.catalog import register_tool


def register(mcp, store):
    register_tool(mcp, store, "respond_friend_request")
