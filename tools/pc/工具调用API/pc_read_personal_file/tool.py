from typing import Literal
from pydantic import StrictInt, StrictBool
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    def pc_read_personal_file(path: str):
        '读取登记个人文件中的UTF-8文本及原始字节SHA-256。'
        return store.pc_read_personal_file(path=path)
