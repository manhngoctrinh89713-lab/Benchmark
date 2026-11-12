from typing import Any
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))
    def apply_workspace_edit(project_id: str, changes: list[dict[str, Any]], dry_run: bool = False, validate_syntax: bool = False):
        '一次整体修改1..100个文件；每项path、content和可选expected_sha256。content字符串创建/覆盖，null删除。目标不得重复或嵌套；全部检查通过才发布。'
        return store.apply_workspace_edit(project_id=project_id, changes=changes, dry_run=dry_run, validate_syntax=validate_syntax)
