"""MCP registration for list_scheduled_emails."""
from local_mail.catalog import register_tool


def register(mcp, store):
    register_tool(mcp, store, "list_scheduled_emails")
