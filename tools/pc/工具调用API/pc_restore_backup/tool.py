from typing import Literal
from pydantic import StrictInt, StrictBool
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False))
    def pc_restore_backup(backup_id: str, idempotency_key: str, overwrite: StrictBool = False):
        '从已校验ZIP恢复原个人文件；默认拒绝覆盖，可幂等重试。'
        return store.pc_restore_backup(backup_id=backup_id, idempotency_key=idempotency_key, overwrite=overwrite)
