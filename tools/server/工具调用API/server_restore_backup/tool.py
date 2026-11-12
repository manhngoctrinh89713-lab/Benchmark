from typing import Literal
from pydantic import StrictInt, StrictBool
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False))
    def server_restore_backup(backup_id: str, idempotency_key: str, overwrite: StrictBool = False):
        '从校验后的ZIP恢复原路径；覆盖需显式指定，配置恢复后仍须重新加载服务。'
        return store.server_restore_backup(backup_id=backup_id, idempotency_key=idempotency_key, overwrite=overwrite)
