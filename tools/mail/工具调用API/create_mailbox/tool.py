"""MCP registration for create_mailbox."""
from local_mail.catalog import register_tool


def register(mcp, store):
    register_tool(mcp, store, "create_mailbox")
