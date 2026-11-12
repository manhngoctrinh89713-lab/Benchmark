from typing import Literal
from pydantic import StrictInt, StrictBool
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    def pc_list_personal_files(path: str | None = None, offset: StrictInt = 0, limit: StrictInt = 20):
        '在登记个人文件根内分页列出真实文件、大小和哈希。'
        return store.pc_list_personal_files(path=path, offset=offset, limit=limit)
