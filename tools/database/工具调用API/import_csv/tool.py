from typing import Any
from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=False, destructiveHint=False, openWorldHint=False))
    def import_csv(db_id: str, table: str, file_path: str, null_value: str | None = None) -> dict:
        """将运行files内UTF-8 CSV导入已有表，首行是唯一非空列名，最多10000数据行。所有行同一事务；默认空字段仍为空字符串，可指定null_value映射NULL，SQLite按表亲和性转换类型。"""
        return store.import_csv(db_id, table, file_path, null_value)
