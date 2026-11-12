from typing import Any
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    def search_code(project_id: str, query: str, pattern: str = "*", case_sensitive: bool = True, offset: int = 0, limit: int = 20):
        '按文本精确搜索项目文件，返回路径、行号和命中行；不是语义引用查找。'
        return store.search_code(project_id=project_id, query=query, pattern=pattern, case_sensitive=case_sensitive, offset=offset, limit=limit)
