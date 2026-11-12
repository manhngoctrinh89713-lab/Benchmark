"""Build the catalog without starting a transport or choosing a case."""
import importlib.util
from pathlib import Path
from mcp.server.fastmcp import FastMCP


def create_server(store):
    root = Path(__file__).resolve().parents[2] / "工具调用API"
    if not root.is_dir():
        from importlib.resources import files
        root = Path(str(files("local_sqlite.api")))
    server = FastMCP("Local SQLite Data")
    for entry in sorted(root.glob("*/tool.py")):
        spec = importlib.util.spec_from_file_location(f"local_sqlite_tool_{entry.parent.name}", entry)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.register(server, store)
    return server
