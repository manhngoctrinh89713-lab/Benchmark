from typing import Literal
from pydantic import StrictInt, StrictBool
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))
    def pc_clean_cache(cache_id: str, older_than_days: StrictInt = 0, dry_run: StrictBool = True):
        '预览或清理登记缓存中的过期文件，跳过模拟进程正在使用的文件。'
        return store.pc_clean_cache(cache_id=cache_id, older_than_days=older_than_days, dry_run=dry_run)
