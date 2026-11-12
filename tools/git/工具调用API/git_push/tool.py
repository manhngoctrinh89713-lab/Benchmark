from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))
    def git_push(repo_id: str, remote: str, branch: str, remote_branch: str | None = None, force: bool = False) -> dict:
        """把本地分支推送到本地模拟远程；force=false 拒绝非快进，force=true 覆盖。"""
        return store.git_push(repo_id, remote, branch, remote_branch, force)
