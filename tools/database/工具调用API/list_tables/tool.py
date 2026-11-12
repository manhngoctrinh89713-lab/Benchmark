from typing import Any
from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, destructiveHint=False, openWorldHint=False))
    def list_tables(db_id: str, include_views: bool = True) -> dict:
        """列出用户表及可选视图，返回名称、类型与建表SQL。"""
        return store.list_tables(db_id, include_views)
