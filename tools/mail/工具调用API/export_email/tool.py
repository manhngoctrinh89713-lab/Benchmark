"""MCP registration for export_email."""
from local_mail.catalog import register_tool


def register(mcp, store):
    register_tool(mcp, store, "export_email")
