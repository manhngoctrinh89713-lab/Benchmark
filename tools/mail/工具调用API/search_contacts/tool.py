"""MCP registration for search_contacts."""
from local_mail.catalog import register_tool


def register(mcp, store):
    register_tool(mcp, store, "search_contacts")
