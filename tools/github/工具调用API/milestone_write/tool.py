from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=False, destructiveHint=False, openWorldHint=False))
    def milestone_write(repo_id: str, title: str | None = None, number: int | None = None, description: str | None = None, state: str | None = None, due_on: str | None = None) -> dict:
        """创建或更新里程碑；省略number新建且须title；due_on需时区，空字符串清除日期。"""
        return store.milestone_write(repo_id, title, number, description, state, due_on)
