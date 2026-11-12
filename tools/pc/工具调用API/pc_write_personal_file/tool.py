from typing import Literal
from pydantic import StrictInt, StrictBool
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))
    def pc_write_personal_file(path: str, content: str, expected_sha256: str | None = None):
        '创建或更新个人文本文件；更新必须提供原字节哈希以防覆盖其他修改。'
        return store.pc_write_personal_file(path=path, content=content, expected_sha256=expected_sha256)
