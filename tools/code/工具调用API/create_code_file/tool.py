from typing import Any
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False))
    def create_code_file(project_id: str, path: str, content: str, validate_syntax: bool = False):
        '创建真实代码、配置或文本文件，自动创建父目录且不覆盖；可选语法校验。'
        return store.create_code_file(project_id=project_id, path=path, content=content, validate_syntax=validate_syntax)
