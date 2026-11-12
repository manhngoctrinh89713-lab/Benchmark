from typing import Literal
from pydantic import StrictInt, StrictBool
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    def pc_verify_backup(backup_id: str):
        '校验ZIP整体哈希、清单、逐文件内容和恢复路径范围。'
        return store.pc_verify_backup(backup_id=backup_id)
