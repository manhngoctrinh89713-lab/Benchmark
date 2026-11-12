from typing import Literal
from pydantic import StrictInt, StrictBool
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))
    def pc_delete_personal_file(path: str, expected_sha256: str):
        '按预期哈希删除一个个人文件；模拟进程使用中的文件不能删除。'
        return store.pc_delete_personal_file(path=path, expected_sha256=expected_sha256)
