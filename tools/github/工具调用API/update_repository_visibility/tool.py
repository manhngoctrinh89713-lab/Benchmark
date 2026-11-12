from typing import Literal
from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False))
    def update_repository_visibility(repo_id: str, visibility: Literal['public', 'private']) -> dict:
        """设置仓库可见性；public 公开、private 私有。"""
        return store.update_repository_visibility(repo_id, visibility)
