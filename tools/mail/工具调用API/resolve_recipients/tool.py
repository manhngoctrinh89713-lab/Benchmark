"""MCP registration for resolve_recipients."""
from local_mail.catalog import register_tool


def register(mcp, store):
    register_tool(mcp, store, "resolve_recipients")
