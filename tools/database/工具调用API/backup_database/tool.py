from typing import Any
from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=False, destructiveHint=False, openWorldHint=False))
    def backup_database(db_id: str, save_path: str) -> dict:
        """使用SQLite Backup API生成运行files内的新数据库备份，不覆盖；备份可由sqlite3直接打开。"""
        return store.backup_database(db_id, save_path)
