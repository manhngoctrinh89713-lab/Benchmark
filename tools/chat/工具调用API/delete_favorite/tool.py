"""MCP registration for delete_favorite."""
from local_chat.catalog import register_tool


def register(mcp, store):
    register_tool(mcp, store, "delete_favorite")
