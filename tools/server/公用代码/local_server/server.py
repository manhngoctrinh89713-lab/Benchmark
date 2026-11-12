"""Build a catalog without starting transports or selecting runs."""
import importlib.util
from pathlib import Path
from mcp.server.fastmcp import FastMCP


def create_server(store):
    root = Path(__file__).resolve().parents[2]/"工具调用API"
    if not root.is_dir():
        from importlib.resources import files
        root = Path(str(files("local_server.api")))
    server = FastMCP("Local Server")
    for entry in sorted(root.glob("*/tool.py")):
        spec = importlib.util.spec_from_file_location("local_server_tool_"+entry.parent.name,entry)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.register(server,store)
    return server
