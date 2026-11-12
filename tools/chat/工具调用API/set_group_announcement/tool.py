"""MCP registration for set_group_announcement."""
from local_chat.catalog import register_tool


def register(mcp, store):
    register_tool(mcp, store, "set_group_announcement")
