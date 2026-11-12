from typing import Any
from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, destructiveHint=False, openWorldHint=False))
    def list_databases() -> dict:
        """查询可操作的本地数据库ID和实际SQLite文件路径。"""
        return store.list_databases()
