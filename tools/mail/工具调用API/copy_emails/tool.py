"""MCP registration for copy_emails."""
from local_mail.catalog import register_tool


def register(mcp, store):
    register_tool(mcp, store, "copy_emails")
