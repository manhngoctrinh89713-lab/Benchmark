"""MCP registration for save_draft."""
from local_chat.catalog import register_tool


def register(mcp, store):
    register_tool(mcp, store, "save_draft")
