from typing import Literal
from pydantic import StrictInt, StrictBool
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    def server_analyze_directory(path: str, limit: StrictInt = 20):
        '按Linux绝对路径分析真实场景文件的大小、数量和大文件。'
        return store.server_analyze_directory(path=path, limit=limit)
