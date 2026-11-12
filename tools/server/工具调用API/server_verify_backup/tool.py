from typing import Literal
from pydantic import StrictInt, StrictBool
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    def server_verify_backup(backup_id: str):
        '验证ZIP整体及逐文件哈希、机器身份和恢复路径。'
        return store.server_verify_backup(backup_id=backup_id)
