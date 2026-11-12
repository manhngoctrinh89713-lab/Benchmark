from typing import Any
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    def get_changes(project_id: str, include_diff: bool = False, offset: int = 0, limit: int = 20):
        '比较实际运行代码与初始模板，分页返回新增、修改、删除及哈希，可附unified diff，不依赖Git。'
        return store.get_changes(project_id=project_id, include_diff=include_diff, offset=offset, limit=limit)
