from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=False, destructiveHint=False, openWorldHint=False))
    def issue_write(repo_id: str, title: str | None = None, body: str | None = None, number: int | None = None, state: str | None = None, labels: list[str] | None = None, assignees: list[str] | None = None, milestone: int | None = None) -> dict:
        """创建或更新Issue；省略number新建且须title。state为open/closed；None字段不修改，空列表清空。标签须先创建；milestone=0清除里程碑。"""
        return store.issue_write(repo_id, title, body, number, state, labels, assignees, milestone)
