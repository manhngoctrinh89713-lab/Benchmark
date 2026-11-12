"""MCP registration for update_scheduled_email."""
from local_mail.catalog import register_tool


def register(mcp, store):
    register_tool(mcp, store, "update_scheduled_email")
