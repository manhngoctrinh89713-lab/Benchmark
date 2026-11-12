from typing import Any
from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, destructiveHint=False, openWorldHint=False))
    def search_schema(db_id: str, query: str = "", offset: int = 0, limit: int = 20) -> dict:
        """按名称或SQL定义子串搜索表、列定义、视图、索引和触发器。offset分页，limit为1..100。"""
        return store.search_schema(db_id, query, offset, limit)
