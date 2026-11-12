"""MCP registration for transfer_group_owner."""
from local_chat.catalog import register_tool


def register(mcp, store):
    register_tool(mcp, store, "transfer_group_owner")
