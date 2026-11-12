from typing import Any
from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, destructiveHint=False, openWorldHint=False))
    def read_query(db_id: str, sql: str, parameters: list[Any] | dict[str, Any] | None = None, limit: int = 100, offset: int = 0) -> dict:
        """执行单条只读SQL，支持SELECT、WITH、JOIN、聚合、窗口函数。参数支持?列表或命名字典。返回columns与rows数组，保留重复列名；limit为1..1000，offset为0..10000。"""
        return store.read_query(db_id, sql, parameters, limit, offset)
