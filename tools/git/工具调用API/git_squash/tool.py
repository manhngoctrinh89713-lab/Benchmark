from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))
    def git_squash(repo_id: str, base: str, message: str) -> dict:
        """把当前本地分支在base之后的全部提交压缩为一个提交，新提交以base为父提交，完整保留当前最终文件树（含删除、二进制及权限）。base须为HEAD的严格祖先，开始前须工作区干净且无merge/rebase进行中。改写本地历史，不自动获取、保留远程新增修改或推送。"""
        return store.git_squash(repo_id, base, message)
