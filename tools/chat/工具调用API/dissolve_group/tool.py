"""MCP registration for dissolve_group."""
from local_chat.catalog import register_tool


def register(mcp, store):
    register_tool(mcp, store, "dissolve_group")
