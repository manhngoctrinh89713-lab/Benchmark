from typing import Any
from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, destructiveHint=False, openWorldHint=False))
    def check_integrity(db_id: str) -> dict:
        """执行数据库完整性及外键检查，返回ok、integrity和foreign_key_violations。"""
        return store.check_integrity(db_id)
