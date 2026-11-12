"""MCP registration for update_contact."""
from local_chat.catalog import register_tool


def register(mcp, store):
    register_tool(mcp, store, "update_contact")
