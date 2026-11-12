from typing import Any
from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=False, destructiveHint=True, openWorldHint=False))
    def write_query(db_id: str, sql: str, parameters: list[Any] | dict[str, Any] | None = None) -> dict:
        """执行单条DML，支持INSERT/UPDATE/DELETE/REPLACE及WITH。事务成功后保存真实数据库和修改记录。外键/约束失败则不修改运行库。"""
        return store.write_query(db_id, sql, parameters)
