"""MCP registration for respond_group_invitation."""
from local_chat.catalog import register_tool


def register(mcp, store):
    register_tool(mcp, store, "respond_group_invitation")
