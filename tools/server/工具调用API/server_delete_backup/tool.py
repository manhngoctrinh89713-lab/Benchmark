from typing import Literal
from pydantic import StrictInt, StrictBool
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))
    def server_delete_backup(backup_id: str):
        '删除本地备份归档及登记，释放模拟磁盘空间。'
        return store.server_delete_backup(backup_id=backup_id)
