"""MCP registration for write_contact."""
from local_mail.catalog import register_tool


def register(mcp, store):
    register_tool(mcp, store, "write_contact")
