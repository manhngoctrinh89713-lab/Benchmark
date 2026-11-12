"""MCP registration for schedule_email."""
from local_mail.catalog import register_tool


def register(mcp, store):
    register_tool(mcp, store, "schedule_email")
