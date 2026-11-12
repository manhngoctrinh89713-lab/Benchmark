from typing import Any
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    def find_references(project_id: str, path: str, line: int, column: int, offset: int = 0, limit: int = 50):
        '仅Python：用Jedi静态分析查找光标符号在项目内的引用和定义，排除文本中的字符串与注释。line从1、column按字符从0开始。'
        return store.find_references(project_id=project_id, path=path, line=line, column=column, offset=offset, limit=limit)
