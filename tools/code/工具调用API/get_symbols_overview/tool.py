from typing import Any
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    def get_symbols_overview(project_id: str, path: str, offset: int = 0, limit: int = 50):
        '用Tree-sitter返回函数、类、方法等定义的name_path和范围；name_path以/分隔，行号1起、字符列号0起。'
        return store.get_symbols_overview(project_id=project_id, path=path, offset=offset, limit=limit)
