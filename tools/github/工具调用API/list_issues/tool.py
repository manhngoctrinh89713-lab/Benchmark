from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, destructiveHint=False, openWorldHint=False))
    def list_issues(repo_id: str, state: str = "open", query: str = "", offset: int = 0, limit: int = 20, labels: list[str] | None = None, assignee: str | None = None, milestone: int | None = None) -> dict:
        """查询本地模拟Issue；state为open/closed/all，query为标题正文子串，offset分页。"""
        return store.list_issues(repo_id, state, query, offset, limit, labels, assignee, milestone)
