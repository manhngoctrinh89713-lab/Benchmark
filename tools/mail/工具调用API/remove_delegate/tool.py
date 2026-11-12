"""MCP registration for remove_delegate."""
from local_mail.catalog import register_tool


def register(mcp, store):
    register_tool(mcp, store, "remove_delegate")
