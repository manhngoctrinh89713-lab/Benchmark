from typing import Any
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))
    def insert_relative_to_symbol(project_id: str, path: str, name_path: str, content: str, position: str = "after", expected_sha256: str | None = None, dry_run: bool = False, validate_syntax: bool = True):
        '在完整行定义的before/after插入代码，适配同层缩进，默认检查语法；行内声明使用精确文本编辑。'
        return store.insert_relative_to_symbol(project_id=project_id, path=path, name_path=name_path, content=content, position=position, expected_sha256=expected_sha256, dry_run=dry_run, validate_syntax=validate_syntax)
