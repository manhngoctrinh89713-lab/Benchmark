"""MCP registration for update_draft_attachments."""
from local_mail.catalog import register_tool


def register(mcp, store):
    register_tool(mcp, store, "update_draft_attachments")
