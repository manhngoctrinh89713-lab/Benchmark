"""MCP registration for download_media."""
from local_chat.catalog import register_tool


def register(mcp, store):
    register_tool(mcp, store, "download_media")
