"""Register the public mailbox operations on a FastMCP server."""

from mcp.server.fastmcp import FastMCP

def create_server(store):
    from .catalog import register_tools

    mcp = FastMCP("Local Mail")
    register_tools(mcp, store)
    return mcp
