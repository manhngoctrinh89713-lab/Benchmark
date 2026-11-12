from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, destructiveHint=False, openWorldHint=False))
    def list_milestones(repo_id: str, state: str = "open", offset: int = 0, limit: int = 20) -> dict:
        """列出里程碑并统计其未关闭及已关闭Issue；state为open/closed/all。"""
        return store.list_milestones(repo_id, state, offset, limit)
