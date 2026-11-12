"""MCP registration for restore_emails."""
from local_mail.catalog import register_tool


def register(mcp, store):
    register_tool(mcp, store, "restore_emails")
