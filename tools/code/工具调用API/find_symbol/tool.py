from typing import Any
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    def find_symbol(project_id: str, name: str, path: str | None = None, include_body: bool = False, offset: int = 0, limit: int = 20):
        '在文件或项目内按name_path的子串查找定义，可返回源码；解析失败文件在skipped中报告。'
        return store.find_symbol(project_id=project_id, name=name, path=path, include_body=include_body, offset=offset, limit=limit)
