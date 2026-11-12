from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, destructiveHint=False, openWorldHint=False))
    def list_workflow_runs(repo_id: str, workflow_id: int | None = None, status: str | None = None, branch: str | None = None, offset: int = 0, limit: int = 20) -> dict:
        """筛选预置Actions运行记录，status为queued/in_progress/completed；不执行CI。"""
        return store.list_workflow_runs(repo_id, workflow_id, status, branch, offset, limit)
