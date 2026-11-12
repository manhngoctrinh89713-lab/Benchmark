from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    def git_operation_status(repo_id: str) -> dict:
        """查询当前merge/rebase操作、未解决冲突文件、当前分支、HEAD及工作区状态；operation=null表示没有进行中的操作。冲突路径相对于所选仓库。"""
        return store.git_operation_status(repo_id)
