from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))
    def git_rebase(repo_id: str, operation: str = "start", upstream: str | None = None,
                   onto: str | None = None, rebase_merges: bool = False) -> dict:
        """变基当前本地分支。operation=start/continue/skip/abort；start需upstream，可用onto指定新基线，rebase_merges=true重建合并拓扑，默认线性重放。开始前须工作区干净且无进行中操作。冲突返回conflicts，编辑文件并git_add后continue；skip会丢弃当前重放提交，abort恢复变基前状态。不会自动fetch或push。"""
        return store.git_rebase(repo_id, operation, upstream, onto, rebase_merges)
