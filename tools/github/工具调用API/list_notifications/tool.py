from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, destructiveHint=False, openWorldHint=False))
    def list_notifications(repo_id: str | None = None, unread_only: bool = True, offset: int = 0, limit: int = 20) -> dict:
        """列出当前用户的本地预置通知，可筛选仓库及未读状态。"""
        return store.list_notifications(repo_id, unread_only, offset, limit)
