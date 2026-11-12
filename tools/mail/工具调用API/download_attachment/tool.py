"""MCP registration for download_attachment."""
from local_mail.catalog import register_tool


def register(mcp, store):
    register_tool(mcp, store, "download_attachment")
