"""One stdio MCP process per run; no API key or recorder access."""
import argparse
import asyncio
import os
import tempfile
import logging
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server

from .catalog import SUITES, load_servers
from .sandbox import validate_tree
from .interface import ToolInterface


async def serve(run_root, groups):
    run_root = Path(run_root).resolve()
    validate_tree(run_root)
    os.chdir(run_root)
    temp = run_root / "services/runtime/tmp"
    temp.mkdir(parents=True, exist_ok=True)
    tempfile.tempdir = str(temp)
    os.environ.update(TEMP=str(temp), TMP=str(temp))
    servers = load_servers(run_root, groups)
    interface = await ToolInterface(run_root, servers).initialize()
    mcp = Server("benchmark-local")

    @mcp.list_tools()
    async def list_tools():
        return interface.tools

    @mcp.call_tool(validate_input=False)
    async def call_tool(name, arguments):
        return await interface.call(name, arguments)

    async with stdio_server() as (reader, writer):
        await mcp.run(reader, writer, mcp.create_initialization_options())


def main():
    logging.basicConfig(level=logging.ERROR)
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--groups", nargs="+", choices=SUITES, required=True)
    args = parser.parse_args()
    asyncio.run(serve(args.run_root, args.groups))


if __name__ == "__main__":
    main()
