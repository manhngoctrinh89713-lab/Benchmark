"""MCP registration for list_delegates."""
from local_mail.catalog import register_tool


def register(mcp, store):
    register_tool(mcp, store, "list_delegates")
