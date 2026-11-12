from typing import Any
from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=False, destructiveHint=True, openWorldHint=False))
    def execute_transaction(db_id: str, statements: list[dict[str, Any]]) -> dict:
        """以一个真实SQLite事务执行1..100条SQL。每项含sql和可选parameters，允许读写及DDL；任一失败整体不落盘。不可自行BEGIN/COMMIT或跨库ATTACH。"""
        return store.execute_transaction(db_id, statements)
