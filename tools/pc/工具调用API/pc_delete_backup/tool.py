from typing import Literal
from pydantic import StrictInt, StrictBool
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))
    def pc_delete_backup(backup_id: str):
        '删除一个本地ZIP备份和记录，释放模拟备份磁盘空间。'
        return store.pc_delete_backup(backup_id=backup_id)
