"""MCP registration for delete_contact_group."""
from local_mail.catalog import register_tool


def register(mcp, store):
    register_tool(mcp, store, "delete_contact_group")
