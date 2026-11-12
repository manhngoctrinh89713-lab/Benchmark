from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, destructiveHint=False, openWorldHint=False))
    def get_workflow_run(repo_id: str, run_id: int) -> dict:
        """读取预置Actions运行状态、结论、提交SHA及任务信息，不执行CI。"""
        return store.get_workflow_run(repo_id, run_id)
