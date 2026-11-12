from typing import Any
from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, destructiveHint=False, openWorldHint=False))
    def explain_query(db_id: str, sql: str, parameters: list[Any] | dict[str, Any] | None = None) -> dict:
        """使用EXPLAIN QUERY PLAN读取只读查询的执行计划，不执行该查询的数据扫描。"""
        return store.explain_query(db_id, sql, parameters)
