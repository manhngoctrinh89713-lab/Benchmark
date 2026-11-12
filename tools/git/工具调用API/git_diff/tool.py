from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, destructiveHint=False, openWorldHint=False))
    def git_diff(repo_id: str, mode: str = "unstaged", base: str | None = None, head: str | None = None) -> dict:
        """查看真实Git差异，mode为unstaged/staged/refs；refs需base和head。禁用external diff和textconv。"""
        return store.git_diff(repo_id, mode, base, head)
