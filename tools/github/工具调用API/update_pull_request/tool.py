from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=False, destructiveHint=False, openWorldHint=False))
    def update_pull_request(repo_id: str, number: int, title: str | None = None, body: str | None = None, draft: bool | None = None, state: str | None = None, linked_issues: list[int] | None = None) -> dict:
        """修改PR标题正文、草稿状态或open/closed；已合并PR不可修改；linked_issues关联的Issue在合入默认分支时关闭。"""
        return store.update_pull_request(repo_id, number, title, body, draft, state, linked_issues)
