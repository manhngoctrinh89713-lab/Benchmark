"""MCP registration for list_rules."""
from local_mail.catalog import register_tool


def register(mcp, store):
    register_tool(mcp, store, "list_rules")
