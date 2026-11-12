from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, destructiveHint=False, openWorldHint=False))
    def list_releases(repo_id: str, offset: int = 0, limit: int = 20) -> dict:
        """列出本地模拟Release，包括草稿和预发布。"""
        return store.list_releases(repo_id, offset, limit)
