from typing import Any
from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, destructiveHint=False, openWorldHint=False))
    def get_database_info(db_id: str) -> dict:
        """查询SQLite版本、文件大小、页数、页大小及数据库SHA-256。"""
        return store.get_database_info(db_id)
