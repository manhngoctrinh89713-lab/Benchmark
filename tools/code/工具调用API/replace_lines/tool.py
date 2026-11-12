from typing import Any
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))
    def replace_lines(project_id: str, path: str, start_line: int, end_line: int, content: str, expected_sha256: str | None = None, dry_run: bool = False, validate_syntax: bool = False):
        '替换从1起的闭区间行；end_line=start_line-1表示插入，空content可删除。支持差异预览、哈希校验和语法校验。'
        return store.replace_lines(project_id=project_id, path=path, start_line=start_line, end_line=end_line, content=content, expected_sha256=expected_sha256, dry_run=dry_run, validate_syntax=validate_syntax)
