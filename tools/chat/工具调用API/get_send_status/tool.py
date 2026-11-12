"""MCP registration for get_send_status."""
from local_chat.catalog import register_tool


def register(mcp, store):
    register_tool(mcp, store, "get_send_status")
