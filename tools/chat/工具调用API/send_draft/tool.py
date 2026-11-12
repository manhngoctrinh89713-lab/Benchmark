"""MCP registration for send_draft."""
from local_chat.catalog import register_tool


def register(mcp, store):
    register_tool(mcp, store, "send_draft")
