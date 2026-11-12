"""MCP registration for set_auto_reply."""
from local_mail.catalog import register_tool


def register(mcp, store):
    register_tool(mcp, store, "set_auto_reply")
