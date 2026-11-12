from typing import Any
from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, destructiveHint=False, openWorldHint=False))
    def describe_table(db_id: str, table: str) -> dict:
        """读取表或视图的列、生成列、外键、索引及建表SQL。"""
        return store.describe_table(db_id, table)
