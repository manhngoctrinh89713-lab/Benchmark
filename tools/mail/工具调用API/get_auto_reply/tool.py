"""MCP registration for get_auto_reply."""
from local_mail.catalog import register_tool


def register(mcp, store):
    register_tool(mcp, store, "get_auto_reply")
