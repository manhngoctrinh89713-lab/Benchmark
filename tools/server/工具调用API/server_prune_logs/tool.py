from typing import Literal
from pydantic import StrictInt, StrictBool
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))
    def server_prune_logs(service_id: str, keep_last: StrictInt = 100, dry_run: StrictBool = True):
        '预览或删除指定服务较早的日志，保留最新keep_last条；其他服务日志保持不变。'
        return store.server_prune_logs(service_id=service_id, keep_last=keep_last, dry_run=dry_run)
