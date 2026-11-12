from typing import Any
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))
    def replace_symbol_body(project_id: str, path: str, name_path: str, body: str, expected_sha256: str | None = None, dry_run: bool = False, validate_syntax: bool = True):
        '替换唯一name_path对应的完整定义，包括签名、函数体及所含装饰器/导出包装；body提供完整定义。自动适配嵌套缩进，默认检查语法。'
        return store.replace_symbol_body(project_id=project_id, path=path, name_path=name_path, body=body, expected_sha256=expected_sha256, dry_run=dry_run, validate_syntax=validate_syntax)
