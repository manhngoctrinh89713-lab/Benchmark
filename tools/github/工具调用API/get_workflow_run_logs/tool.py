from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, destructiveHint=False, openWorldHint=False))
    def get_workflow_run_logs(repo_id: str, run_id: int, offset: int = 0, limit: int = 100) -> dict:
        """按行分页读取预置Actions日志；offset从0开始，limit为1..1000。"""
        return store.get_workflow_run_logs(repo_id, run_id, offset, limit)
