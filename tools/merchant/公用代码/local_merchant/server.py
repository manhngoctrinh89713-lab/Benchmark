from mcp.server.fastmcp import FastMCP
from .catalog import register_tools


def create_server(store):
    server = FastMCP("Local Merchant")
    register_tools(server, store)
    return server
