from typing import Any
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))
    def replace_text(project_id: str, path: str, edits: list[dict[str, Any]], expected_sha256: str | None = None, dry_run: bool = False, validate_syntax: bool = False):
        '依次应用old_text/new_text精确替换；可选expected_count默认1，必须命中该次数。全部检查成功才写入，支持预览与哈希校验。'
        return store.replace_text(project_id=project_id, path=path, edits=edits, expected_sha256=expected_sha256, dry_run=dry_run, validate_syntax=validate_syntax)
