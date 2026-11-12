"""MCP registration for delete_rule."""
from local_mail.catalog import register_tool


def register(mcp, store):
    register_tool(mcp, store, "delete_rule")
