from typing import Any
from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=False, destructiveHint=True, openWorldHint=False))
    def execute_schema(db_id: str, sql: str) -> dict:
        """执行单条结构修改SQL，如建表、索引、视图、触发器、ALTER或DROP；不允许ATTACH、VACUUM INTO或用户PRAGMA。"""
        return store.execute_schema(db_id, sql)
