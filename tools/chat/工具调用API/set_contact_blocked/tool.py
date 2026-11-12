"""MCP registration for set_contact_blocked."""
from local_chat.catalog import register_tool


def register(mcp, store):
    register_tool(mcp, store, "set_contact_blocked")
