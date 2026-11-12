"""Register the public chat operations on a FastMCP server."""
from mcp.server.fastmcp import FastMCP
from .catalog import register_tools


def create_server(store):
    server = FastMCP("Local Chat")
    register_tools(server, store)
    return server
