from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, destructiveHint=False, openWorldHint=False))
    def list_pull_requests(repo_id: str, state: str = "open", offset: int = 0, limit: int = 20, query: str = "", author: str | None = None, reviewer: str | None = None) -> dict:
        """查询模拟PR，state为open/closed/merged/all，可按标题正文子串、作者及待评审人筛选。"""
        return store.list_pull_requests(repo_id, state, offset, limit, query, author, reviewer)
