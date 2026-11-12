"""MCP registration for delete_mailbox."""
from local_mail.catalog import register_tool


def register(mcp, store):
    register_tool(mcp, store, "delete_mailbox")
