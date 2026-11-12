from typing import Literal
from pydantic import StrictInt, StrictBool
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    def pc_analyze_directory(path: str, limit: StrictInt = 20):
        '分析登记磁盘内目录的真实场景文件大小、数量和大文件。'
        return store.pc_analyze_directory(path=path, limit=limit)
