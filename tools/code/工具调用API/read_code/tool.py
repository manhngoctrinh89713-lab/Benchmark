from typing import Any
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    def read_code(project_id: str, path: str, start_line: int = 1, end_line: int | None = None):
        '读取真实UTF-8代码/配置文件，可指定从1开始的闭区间行号，返回原字节sha256。'
        return store.read_code(project_id=project_id, path=path, start_line=start_line, end_line=end_line)
