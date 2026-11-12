from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, destructiveHint=False, openWorldHint=False))
    def list_labels(repo_id: str, offset: int = 0, limit: int = 20) -> dict:
        """列出仓库本地标签目录。"""
        return store.list_labels(repo_id, offset, limit)
