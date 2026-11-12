"""MCP registration for download_favorite_attachment."""
from local_chat.catalog import register_tool


def register(mcp, store):
    register_tool(mcp, store, "download_favorite_attachment")
